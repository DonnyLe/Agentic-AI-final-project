"""Local review and labeling tool for the FP2 corpus.

Two modes. Nothing is sent anywhere; the server only listens on 127.0.0.1.

review  Shows one case at a time with its seeded label and the generator's
        note, and writes keep/correct/discard into working/review_sheet.csv.
        Golden-set cases are left out unless you pass --include-golden,
        because seeing their seeded labels would unblind a labeler.

label   Blind labeling of the golden set. Shows only id and content from
        labeling_packet_for_labelers.jsonl, and writes your label into one
        column of golden.csv. It never shows the other labeler's column.

Usage:
  python3 scripts/review_ui.py review [--include-golden]
  python3 scripts/review_ui.py label --column labeler_a|labeler_b
  (both take --port 8765 and --no-browser)

Review keys: K keep, C correct, D discard, N notes, left/right previous/next,
P policy panel, Esc leave a text field.
Label mode has a rules panel on the right: pick the tier, tick the broken
rules, Enter saves and moves on. Keys: 0 no rule broken, 1-4 tier,
left/right previous/next.
"""
import argparse
import csv
import json
import os
import re
import subprocess
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(ROOT, "corpus.jsonl")
SHEET = os.path.join(ROOT, "working", "review_sheet.csv")
GOLDEN = os.path.join(ROOT, "golden.csv")
PACKET = os.path.join(ROOT, "labeling_packet_for_labelers.jsonl")
POLICY = os.path.join(ROOT, "policy.md")

DECISION = "decision(keep/correct/discard)"
EDITABLE = ["reviewer", DECISION, "corrected_label", "review_notes"]
DECISIONS = {"keep", "correct", "discard"}
LABEL_RE = re.compile(r"^(none|T[1-4]( R\d\.\d)+)$")
RULE_RE = re.compile(r"^\*\*(R\d\.\d) · (.+?)\.\*\* (.+)$")
TIER_RE = re.compile(r"^\| (T[1-4]) \| (.+?) \| (.+?) \| (.+?) \| (.+?) \|$")

lock = threading.Lock()
settings = {"mode": "review", "column": None, "include_golden": False}


def read_csv(path):
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def write_csv(path, fields, rows):
    """Write to a temp file and rename, so a crash never leaves half a CSV."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".csv")
    with os.fdopen(fd, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, path)


def read_jsonl(path):
    with open(path) as f:
        return {c["id"]: c for c in map(json.loads, filter(str.strip, f))}


def load_rules():
    rules = []
    with open(POLICY) as f:
        for line in f:
            m = RULE_RE.match(line.strip())
            if m:
                rules.append({"id": m[1], "title": m[2], "text": m[3]})
    return rules


def git_user():
    try:
        out = subprocess.run(["git", "config", "user.name"], cwd=ROOT,
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip()
    except OSError:
        return ""


def load_review_data():
    cases = read_jsonl(CORPUS)
    _, rows = read_csv(SHEET)
    items = [{"row": row, "case": cases[row["case_id"]]} for row in rows
             if row["case_id"] in cases
             and (settings["include_golden"] or row["in_golden"] != "True")]
    return {"items": items, "rules": load_rules(), "user": git_user()}


def load_label_data():
    """Only id and content leave this function, and only the chosen column."""
    packet = read_jsonl(PACKET)
    _, rows = read_csv(GOLDEN)
    col = settings["column"]
    items = [{"row": {"case_id": r["case_id"], "label": r[col]},
              "case": {"id": r["case_id"], "content": packet[r["case_id"]]["content"]}}
             for r in rows if r["case_id"] in packet]
    return {"items": items, "rules": load_rules(), "tiers": load_tiers(), "column": col}


def load_tiers():
    tiers = []
    with open(POLICY) as f:
        for line in f:
            m = TIER_RE.match(line.strip())
            if m:
                tiers.append({"id": m[1], "name": m[2], "evidence": m[3],
                              "action": m[4], "approval": m[5]})
    return tiers


def save_label(update):
    case_id = update.get("case_id")
    label = " ".join((update.get("label") or "").split())
    if label and not LABEL_RE.match(label):
        return 400, {"error": "label must be 'none' or 'T<n> R<x.y>[ R<x.y>]'"}
    col = settings["column"]
    with lock:
        fields, rows = read_csv(GOLDEN)
        row = next((r for r in rows if r["case_id"] == case_id), None)
        if row is None:
            return 404, {"error": f"no golden row for {case_id}"}
        row[col] = label
        write_csv(GOLDEN, fields, rows)
    return 200, {"row": {"case_id": case_id, "label": label}}


def save_review(update):
    case_id = update.get("case_id")
    decision = update.get(DECISION, "")
    label = (update.get("corrected_label") or "").strip()
    if decision and decision not in DECISIONS:
        return 400, {"error": f"bad decision {decision!r}"}
    if decision == "correct" and not LABEL_RE.match(label):
        return 400, {"error": "corrected label must be 'none' or 'T<n> R<x.y>[ R<x.y>]'"}
    if decision != "correct":
        label = ""
    with lock:
        fields, rows = read_csv(SHEET)
        row = next((r for r in rows if r["case_id"] == case_id), None)
        if row is None:
            return 404, {"error": f"no row for {case_id}"}
        if row["in_golden"] == "True" and not settings["include_golden"]:
            return 403, {"error": "golden cases are hidden in this session"}
        row["reviewer"] = (update.get("reviewer") or "").strip()
        row[DECISION] = decision
        row["corrected_label"] = label
        row["review_notes"] = (update.get("review_notes") or "").strip()
        write_csv(SHEET, fields, rows)
    return 200, {"row": row}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        label_mode = settings["mode"] == "label"
        if self.path == "/":
            config = json.dumps({"mode": settings["mode"], "column": settings["column"]})
            return self._send(200, PAGE.replace("__CONFIG__", config), "text/html")
        if self.path == "/api/data":
            return self._send(200, load_label_data() if label_mode else load_review_data())
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/save":
            return self._send(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length", 0))
        try:
            update = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            return self._send(400, {"error": "invalid JSON"})
        self._send(*(save_label(update) if settings["mode"] == "label" else save_review(update)))

    def log_message(self, *args):
        pass


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Corpus Review</title>
<style>
:root {
  --bg: #f6f6f4; --panel: #ffffff; --ink: #1d1d1b; --muted: #6b6b66; --line: #e2e1dc;
  --accent: #2f5bd3; --keep: #1f8a4c; --correct: #b26a00; --discard: #c0392b;
  --chip: #eef0f6; --hl: #fff6d6;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #161615; --panel: #1f1f1d; --ink: #ecebe6; --muted: #9a9a93; --line: #34342f;
    --accent: #7c9cff; --keep: #4cc27d; --correct: #f0a640; --discard: #ff6b5b;
    --chip: #2a2c33; --hl: #3a3420;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
header { display: flex; gap: 12px; align-items: center; padding: 8px 16px;
  border-bottom: 1px solid var(--line); background: var(--panel); position: sticky; top: 0; z-index: 2; }
header h1 { font-size: 15px; margin: 0; }
.progress { flex: 1; height: 6px; background: var(--line); border-radius: 3px; overflow: hidden; }
.progress div { height: 100%; background: var(--keep); width: 0; transition: width .2s; }
input, select, textarea, button { font: inherit; color: inherit; }
input, select, textarea { background: var(--bg); border: 1px solid var(--line); border-radius: 6px; padding: 4px 8px; }
button { background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 6px 12px; cursor: pointer; }
button:hover { border-color: var(--accent); }
.layout { display: grid; grid-template-columns: 220px 1fr; height: calc(100vh - 49px); }
nav { border-right: 1px solid var(--line); overflow-y: auto; background: var(--panel); }
nav .filters { padding: 8px; border-bottom: 1px solid var(--line); position: sticky; top: 0; background: var(--panel); }
nav .filters select { width: 100%; }
nav a { display: flex; justify-content: space-between; padding: 4px 10px; color: inherit;
  text-decoration: none; font-family: ui-monospace, monospace; font-size: 12px; cursor: pointer; }
nav a.active { background: var(--chip); font-weight: 600; }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-top: 6px; background: var(--line); }
.dot.keep { background: var(--keep); } .dot.correct { background: var(--correct); } .dot.discard { background: var(--discard); }
main { overflow-y: auto; padding: 16px 20px 160px; }
.meta { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 12px; }
.meta h2 { margin: 0 8px 0 0; font-size: 20px; font-family: ui-monospace, monospace; }
.badge { padding: 2px 8px; border-radius: 10px; background: var(--chip); font-size: 12px; }
.badge.warn { background: var(--hl); }
.label { font-family: ui-monospace, monospace; font-weight: 700; font-size: 15px; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px; margin-bottom: 12px; }
.card h3 { margin: 0 0 8px; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
.action { font-size: 15px; }
.seg { display: grid; grid-template-columns: 90px 140px 1fr; gap: 8px; padding: 3px 0; border-top: 1px solid var(--line); }
.seg:first-of-type { border-top: 0; }
.seg .sid { font-family: ui-monospace, monospace; font-size: 12px; color: var(--muted); }
.seg .who { font-weight: 600; }
.seg.cited { background: var(--hl); }
.ev table { border-collapse: collapse; width: 100%; font-size: 13px; margin: 4px 0; }
.ev th, .ev td { border: 1px solid var(--line); padding: 3px 6px; text-align: left; vertical-align: top; }
.ev th { background: var(--chip); font-weight: 600; }
.ev .k { font-weight: 600; margin-top: 6px; }
.ev .nest { margin-left: 12px; }
.note { white-space: pre-wrap; }
.bar { position: fixed; left: 220px; right: 0; bottom: 0; background: var(--panel); border-top: 1px solid var(--line);
  padding: 10px 20px; display: grid; gap: 8px; z-index: 3; }
.bar .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.bar .keep { border-color: var(--keep); color: var(--keep); }
.bar .correct { border-color: var(--correct); color: var(--correct); }
.bar .discard { border-color: var(--discard); color: var(--discard); }
.bar .on { color: #fff; } .bar .keep.on { background: var(--keep); }
.bar .correct.on { background: var(--correct); } .bar .discard.on { background: var(--discard); }
.bar textarea { flex: 1; min-height: 34px; height: 34px; resize: vertical; }
.chips { display: none; gap: 4px; flex-wrap: wrap; align-items: center; }
.chips.show { display: flex; }
.chip { padding: 2px 8px; border-radius: 10px; font-family: ui-monospace, monospace; font-size: 12px; }
.chip.on { background: var(--correct); color: #fff; border-color: var(--correct); }
.status { color: var(--muted); font-size: 12px; margin-left: auto; }
.status.err { color: var(--discard); }
kbd { font-family: ui-monospace, monospace; font-size: 11px; border: 1px solid var(--line); border-radius: 3px; padding: 0 4px; }
aside { position: fixed; top: 49px; right: 0; bottom: 0; width: 420px; background: var(--panel); border-left: 1px solid var(--line);
  overflow-y: auto; padding: 12px 16px; transform: translateX(100%); transition: transform .15s; z-index: 4; }
aside.open { transform: none; }
aside .rule { margin-bottom: 10px; }
aside .rule b { font-family: ui-monospace, monospace; }
body.label .review-only { display: none; }
body.label .bar { display: none; }
body.label .layout { grid-template-columns: 200px 1fr 420px; }
body.label main { padding-bottom: 24px; }
.side { display: none; }
body.label .side { display: block; overflow-y: auto; border-left: 1px solid var(--line); background: var(--panel); }
.side .head { position: sticky; top: 0; background: var(--panel); border-bottom: 1px solid var(--line); padding: 10px 14px; z-index: 1; }
.side .head .row { display: flex; gap: 8px; align-items: center; }
.side .preview { font-family: ui-monospace, monospace; font-weight: 700; font-size: 16px; flex: 1; }
.side .preview.bad { color: var(--muted); font-weight: 400; font-size: 13px; }
.side .save { background: var(--keep); color: #fff; border-color: var(--keep); font-weight: 600; }
.side .save:disabled { opacity: .4; cursor: default; }
.side .hint { font-size: 12px; color: var(--muted); margin-top: 4px; }
.side .group { padding: 8px 14px 4px; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
.opt { display: grid; grid-template-columns: 20px 1fr; gap: 6px; margin: 4px 10px; padding: 8px 10px;
  border: 1px solid var(--line); border-radius: 8px; cursor: pointer; }
.opt:hover { border-color: var(--accent); }
.opt.on { border-color: var(--correct); background: var(--hl); }
.opt input { margin-top: 3px; }
.opt .t { font-weight: 600; }
.opt .t code { font-family: ui-monospace, monospace; margin-right: 6px; }
.opt .d { font-size: 12.5px; color: var(--muted); margin-top: 2px; }
.opt.on .d { color: var(--ink); }
.opt kbd { float: right; }
</style>
</head>
<body>
<header>
  <h1>Corpus review</h1>
  <span id="count"></span>
  <div class="progress"><div id="prog"></div></div>
  <label class="review-only">Reviewer <input id="reviewer" size="16"></label>
  <button id="policyBtn" class="review-only">Policy <kbd>P</kbd></button>
</header>
<div class="layout">
  <nav>
    <div class="filters">
      <select id="filter">
        <option value="todo">To do (not reviewed by you)</option>
        <option value="all">All cases</option>
        <option value="golden">Golden set</option>
        <option value="flagged">Has audit flags</option>
        <option value="ambiguous">Ambiguous or injection</option>
        <option value="correct">Corrected</option>
        <option value="discard">Discarded</option>
      </select>
    </div>
    <div id="list"></div>
  </nav>
  <main id="main"></main>
  <section class="side" id="side"></section>
</div>
<div class="bar">
  <div class="row">
    <button class="keep review-only" data-d="keep">Keep <kbd>K</kbd></button>
    <button class="correct review-only" data-d="correct">Correct <kbd>C</kbd></button>
    <button class="discard review-only" data-d="discard">Discard <kbd>D</kbd></button>
    <textarea id="notes" class="review-only" placeholder="Review notes (N). Required for correct and discard."></textarea>
    <button id="prev"><kbd>&larr;</kbd></button>
    <button id="next"><kbd>&rarr;</kbd></button>
  </div>
  <div class="row chips" id="chips">
    <span id="labelCaption">Corrected label:</span>
    <span id="tierChips"></span>
    <span id="ruleChips"></span>
    <input id="label" size="22" placeholder="T2 R2.1">
    <button id="saveCorrect">Save <kbd>Enter</kbd></button>
  </div>
  <div class="row"><span class="status" id="status"></span></div>
</div>
<aside id="policy"></aside>
<script>
const CFG = __CONFIG__;
const LABEL = CFG.mode === "label";
const DEC = "decision(keep/correct/discard)";
const LABEL_RE = /^(none|T[1-4]( R\d\.\d)+)$/;
let items = [], rules = [], tiers = [], view = [], cur = 0, pending = null;
let sel = { tier: "", rules: new Set() };   // label mode selection
const $ = id => document.getElementById(id);

function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") e.className = v; else if (k.startsWith("on")) e[k] = v; else e.setAttribute(k, v);
  }
  for (const k of kids.flat()) if (k != null) e.append(k instanceof Node ? k : String(k));
  return e;
}

const seeded = c => c.seeded_tier === "none" ? "none" : [c.seeded_tier, ...c.seeded_rules].join(" ");
const reviewer = () => $("reviewer").value.trim();
const done = it => LABEL ? !!it.row.label : !!(it.row.reviewer && it.row[DEC]);
const mine = it => LABEL ? !!it.row.label : it.row.reviewer === reviewer() && !!it.row[DEC];

function matches(it, f) {
  const r = it.row, c = it.case;
  if (LABEL) return f === "todo" ? !r.label : true;
  if (f === "todo") return !(r.reviewer === reviewer() && r[DEC]);
  if (f === "golden") return r.in_golden === "True";
  if (f === "flagged") return !!r.audit_flags;
  if (f === "ambiguous") return c.ambiguous || c.injection;
  if (f === "correct" || f === "discard") return r[DEC] === f;
  return true;
}

function rebuild(keepId) {
  const f = $("filter").value;
  view = items.filter(it => matches(it, f));
  const idx = view.findIndex(it => it.row.case_id === keepId);
  cur = idx >= 0 ? idx : Math.min(cur, Math.max(view.length - 1, 0));
  renderList(); render();
}

function renderList() {
  const list = $("list");
  list.replaceChildren(...view.map((it, i) => el("a", {
    class: i === cur ? "active" : "", onclick: () => { cur = i; renderList(); render(); }
  }, it.row.case_id, el("span", { class: "dot " + (done(it) ? (LABEL ? "keep" : it.row[DEC]) : "") }))));
  const n = items.filter(mine).length;
  $("count").textContent = LABEL ? `${n} / ${items.length} labeled (${CFG.column})` : `${n} / ${items.length} reviewed by you`;
  $("prog").style.width = (100 * n / items.length) + "%";
  const a = list.querySelector(".active"); if (a) a.scrollIntoView({ block: "nearest" });
}

function evidence(v, depth = 0) {
  if (v === null || v === undefined) return el("span", { class: "muted" }, "null");
  if (Array.isArray(v)) {
    if (v.length && v.every(x => x && typeof x === "object" && !Array.isArray(x))) {
      const cols = [...new Set(v.flatMap(Object.keys))];
      return el("table", {}, el("tr", {}, cols.map(c => el("th", {}, c))),
        v.map(row => el("tr", {}, cols.map(c => el("td", {}, cell(row[c]))))));
    }
    return el("div", {}, v.map(x => el("div", {}, "• ", cell(x))));
  }
  if (typeof v === "object") {
    const vals = Object.values(v);
    if (vals.length && vals.every(x => x && typeof x === "object" && !Array.isArray(x))) {
      const cols = [...new Set(vals.flatMap(Object.keys))];
      return el("table", {}, el("tr", {}, el("th", {}, "id"), cols.map(c => el("th", {}, c))),
        Object.entries(v).map(([k, row]) => el("tr", {}, el("td", {}, k), cols.map(c => el("td", {}, cell(row[c]))))));
    }
    return el("div", { class: depth ? "nest" : "" }, Object.entries(v).map(([k, x]) =>
      (x && typeof x === "object") ? el("div", {}, el("div", { class: "k" }, k), evidence(x, depth + 1))
                                   : el("div", {}, el("b", {}, k + ": "), cell(x))));
  }
  return String(v);
}
const cell = x => (x && typeof x === "object") ? evidence(x, 1) : (x === null || x === undefined ? "" : String(x));

function render() {
  const main = $("main");
  const it = view[cur];
  if (!it) { main.replaceChildren(el("p", {}, "Nothing left in this filter.")); syncBar(); return; }
  const c = it.case, r = it.row, ct = c.content;
  const cited = new Set((ct.candidate_action.match(/M-\d+-S\d+/g) || []));
  if (LABEL) {
    main.replaceChildren(
      el("div", { class: "meta" }, el("h2", {}, c.id),
        el("span", { class: "badge" }, `${ct.meeting_type} · ${ct.meeting_weekday} ${ct.meeting_date} · ${ct.meeting_timezone}`),
        r.label ? el("span", { class: "badge" }, "your label ", el("span", { class: "label" }, r.label)) : null),
      el("div", { class: "card" }, el("h3", {}, "Candidate action"), el("div", { class: "action" }, ct.candidate_action)),
      transcript(ct, cited),
      el("div", { class: "card ev" }, el("h3", {}, "Evidence"), evidence(ct.evidence)));
    main.scrollTop = 0;
    syncBar();
    return;
  }
  main.replaceChildren(
    el("div", { class: "meta" },
      el("h2", {}, c.id),
      el("span", { class: "badge" }, "seeded ", el("span", { class: "label" }, seeded(c))),
      el("span", { class: "badge" }, "action class " + c.target_tier),
      el("span", { class: "badge" }, c.scenario_family),
      r.in_golden === "True" ? el("span", { class: "badge warn" }, "golden") : null,
      c.ambiguous ? el("span", { class: "badge warn" }, "ambiguous: " + (c.ambiguity_type || "?")) : null,
      c.injection ? el("span", { class: "badge warn" }, "injection") : null,
      el("span", { class: "badge" }, `${ct.meeting_type} · ${ct.meeting_weekday} ${ct.meeting_date} · ${ct.meeting_timezone}`)),
    el("div", { class: "card" }, el("h3", {}, "Candidate action"), el("div", { class: "action" }, ct.candidate_action)),
    el("div", { class: "card" }, el("h3", {}, "Generator's intent (why it is labeled this way)"),
      el("div", { class: "note" }, c.generation_note || "(none)"),
      r.audit_flags ? el("div", {}, el("b", {}, "Audit flags: "), r.audit_flags) : null),
    transcript(ct, cited),
    el("div", { class: "card ev" }, el("h3", {}, "Evidence"), evidence(ct.evidence)));
  main.scrollTop = 0;
  syncBar();
}

function transcript(ct, cited) {
  return el("div", { class: "card" }, el("h3", {}, "Transcript"),
    ct.segments.map(s => el("div", { class: "seg" + (cited.has(s.segment_id) ? " cited" : "") },
      el("span", { class: "sid" }, s.segment_id.split("-").pop()),
      el("span", { class: "who" }, s.speaker),
      el("span", {}, s.text))));
}

function syncBar() {
  const it = view[cur];
  const r = it ? it.row : {};
  if (LABEL) {
    const parts = (r.label || "").split(" ").filter(Boolean);
    sel = { tier: parts[0] || "", rules: new Set(parts.slice(1)) };
    renderSide();
    return;
  }
  const d = pending || r[DEC] || "";
  document.querySelectorAll(".bar [data-d]").forEach(b => b.classList.toggle("on", b.dataset.d === d));
  $("notes").value = it ? (r.review_notes || "") : "";
  $("chips").classList.toggle("show", d === "correct");
  if (d === "correct") {
    $("label").value = r.corrected_label || (it ? seeded(it.case) : "");
    syncChips();
  }
}

function parseLabel() {
  const parts = $("label").value.trim().split(/\s+/).filter(Boolean);
  return { tier: parts[0] || "", rules: new Set(parts.slice(1)) };
}
function setLabel(tier, rs) {
  $("label").value = tier === "none" ? "none" : [tier, ...[...rs].sort()].filter(Boolean).join(" ");
  syncChips();
}
function syncChips() {
  const { tier, rules: rs } = parseLabel();
  $("tierChips").replaceChildren(...["none", "T1", "T2", "T3", "T4"].map(t =>
    el("button", { class: "chip" + (tier === t ? " on" : ""), onclick: () => setLabel(t, t === "none" ? new Set() : rs) }, t)));
  $("ruleChips").replaceChildren(...rules.map(x => el("button", {
    class: "chip" + (rs.has(x.id) ? " on" : ""), title: x.title,
    onclick: () => { const s = new Set(rs); s.has(x.id) ? s.delete(x.id) : s.add(x.id);
      const t = tier === "none" || !tier ? "T" + x.id[1] : tier; setLabel(t, s); }
  }, x.id)));
}

function status(msg, err) { const s = $("status"); s.textContent = msg; s.classList.toggle("err", !!err); }

function selLabel() {
  if (sel.tier === "none") return "none";
  return sel.tier ? [sel.tier, ...[...sel.rules].sort()].join(" ") : "";
}

function pickTier(t) {
  sel.tier = t;
  if (t === "none") sel.rules.clear();
  renderSide();
}

function toggleRule(id) {
  sel.rules.has(id) ? sel.rules.delete(id) : sel.rules.add(id);
  if ((!sel.tier || sel.tier === "none") && sel.rules.size) sel.tier = "T" + id[1];
  renderSide();
}

function option(on, type, key, title, desc, onclick) {
  const input = el("input", { type, tabindex: "-1" });
  input.checked = on;
  return el("div", { class: "opt" + (on ? " on" : ""), onclick },
    input, el("div", {}, el("div", { class: "t" }, key ? el("kbd", {}, key) : null, ...title), el("div", { class: "d" }, desc)));
}

function renderSide() {
  const it = view[cur];
  const side = $("side");
  if (!it) { side.replaceChildren(); return; }
  const label = selLabel();
  const ok = LABEL_RE.test(label);
  let hint = "Pick the tier of the candidate action, then tick every rule it breaks. Enter saves.";
  if (sel.tier && sel.tier !== "none" && !sel.rules.size) hint = "Tick at least one broken rule, or choose No rule broken.";
  const saved = it.row.label && it.row.label === label;
  const head = el("div", { class: "head" },
    el("div", { class: "row" },
      el("span", { class: "preview" + (label ? "" : " bad") }, label || "no label yet"),
      el("button", { onclick: () => move(-1), title: "Previous (←)" }, "←"),
      el("button", { onclick: () => move(1), title: "Next (→)" }, "→"),
      Object.assign(el("button", { class: "save", onclick: saveLabel }, saved ? "Saved ✓" : "Save ⏎"), { disabled: !ok })),
    el("div", { class: "hint" }, hint));
  const byTier = t => rules.filter(r => r.id[1] === t.id[1]);
  side.replaceChildren(...[head,
    el("div", { class: "group" }, "Compliant"),
    option(sel.tier === "none", "radio", "0", ["No rule broken"],
      "Carrying out the candidate action exactly as written breaks none of the rules below. Label: none.",
      () => pickTier("none")),
    el("div", { class: "group" }, "Tier of the candidate action"),
    tiers.map((t, i) => option(sel.tier === t.id, "radio", String(i + 1), [el("code", {}, t.id), t.name],
      `${t.action}. Evidence: ${t.evidence}. Approval: ${t.approval}.`, () => pickTier(t.id))),
    tiers.map(t => [
      el("div", { class: "group" }, `Broken rules · ${t.id} ${t.name}`),
      byTier(t).map(r => option(sel.rules.has(r.id), "checkbox", "", [el("code", {}, r.id), r.title],
        r.text, () => toggleRule(r.id)))])].flat(Infinity));
}

async function saveLabel() {
  const it = view[cur]; if (!it) return;
  const label = selLabel();
  if (!LABEL_RE.test(label)) { status("Label must be 'none' or 'T<n> R<x.y>[ R<x.y>]'.", true); return; }
  const res = await fetch("/api/save", { method: "POST", body: JSON.stringify({ case_id: it.row.case_id, label }) });
  const out = await res.json();
  if (!res.ok) { status(out.error, true); return; }
  Object.assign(it.row, out.row);
  status(`Saved ${it.row.case_id}: ${label}`);
  advance();
}

async function decide(d) {
  if (LABEL) return saveLabel();
  const it = view[cur]; if (!it) return;
  if (!reviewer()) { status("Enter your name in Reviewer first.", true); $("reviewer").focus(); return; }
  const notes = $("notes").value.trim();
  if (d === "correct" && pending !== "correct") {
    pending = "correct"; syncBar(); $("label").focus(); return;
  }
  const label = d === "correct" ? $("label").value.trim().replace(/\s+/g, " ") : "";
  if (d === "correct" && !LABEL_RE.test(label)) { status("Label must be 'none' or 'T<n> R<x.y>[ R<x.y>]'.", true); return; }
  if (d !== "keep" && !notes) { status("Add a note saying why (N).", true); $("notes").focus(); return; }
  const body = { case_id: it.row.case_id, reviewer: reviewer(), [DEC]: d, corrected_label: label, review_notes: notes };
  const res = await fetch("/api/save", { method: "POST", body: JSON.stringify(body) });
  const out = await res.json();
  if (!res.ok) { status(out.error, true); return; }
  Object.assign(it.row, out.row);
  pending = null;
  status(`Saved ${it.row.case_id}: ${d}${label ? " → " + label : ""}`);
  advance();
}

function advance() {
  const id = view[cur] && view[cur].row.case_id;
  if ($("filter").value === "todo") {
    view = items.filter(it => matches(it, "todo"));
    cur = Math.min(cur, Math.max(view.length - 1, 0));
  } else {
    cur = Math.min(cur + 1, view.length - 1);
  }
  renderList(); render();
}

function move(step) { pending = null; cur = Math.max(0, Math.min(view.length - 1, cur + step)); renderList(); render(); }

document.querySelectorAll(".bar [data-d]").forEach(b => b.onclick = () => decide(b.dataset.d));
$("saveCorrect").onclick = () => decide("correct");
$("prev").onclick = () => move(-1);
$("next").onclick = () => move(1);
$("filter").onchange = () => { pending = null; rebuild(view[cur] && view[cur].row.case_id); };
$("label").oninput = syncChips;
$("policyBtn").onclick = () => $("policy").classList.toggle("open");
$("reviewer").onchange = () => { try { localStorage.setItem("reviewer", reviewer()); } catch (e) {} rebuild(view[cur] && view[cur].row.case_id); };

document.addEventListener("keydown", e => {
  const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName);
  if (e.key === "Escape") { document.activeElement.blur(); return; }
  if (typing) {
    if (LABEL && document.activeElement.id === "label" && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault(); move(e.key === "ArrowDown" ? 1 : -1); return;
    }
    if (e.key === "Enter" && !e.shiftKey && document.activeElement.id === "label") { e.preventDefault(); decide("correct"); }
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && document.activeElement.id === "notes" && pending) { e.preventDefault(); decide(pending); }
    return;
  }
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const k = e.key.toLowerCase();
  if (LABEL) {
    if (e.key === "Enter") { e.preventDefault(); saveLabel(); }
    else if (k === "0") pickTier("none");
    else if (["1", "2", "3", "4"].includes(k)) pickTier("T" + k);
    else if (e.key === "ArrowRight") { e.preventDefault(); move(1); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); move(-1); }
    return;
  }
  if (k === "k") decide("keep");
  else if (k === "c") decide("correct");
  else if (k === "d") { pending = "discard"; syncBar(); $("notes").focus(); status("Write why, then Cmd/Ctrl+Enter to discard."); }
  else if (k === "n") { e.preventDefault(); $("notes").focus(); }
  else if (k === "p") $("policy").classList.toggle("open");
  else if (e.key === "ArrowRight" || k === "j") move(1);
  else if (e.key === "ArrowLeft") move(-1);
  else return;
  e.preventDefault();
});

(async () => {
  const data = await (await fetch("/api/data")).json();
  items = data.items; rules = data.rules; tiers = data.tiers || [];
  if (LABEL) {
    document.body.classList.add("label");
    document.querySelector("header h1").textContent = "Blind labeling";
    document.title = "Blind Labeling";
    $("labelCaption").textContent = "Your label:";
    $("label").placeholder = "none  or  T2 R2.1 R2.3";
    [...$("filter").options].forEach(o => { if (!["todo", "all"].includes(o.value)) o.remove(); });
    $("filter").options[0].textContent = "To do (unlabeled)";
  }
  let saved = ""; try { saved = localStorage.getItem("reviewer") || ""; } catch (e) {}
  $("reviewer").value = saved || data.user || "";
  $("policy").replaceChildren(el("h3", {}, "Policy rules"),
    ...rules.map(x => el("div", { class: "rule" }, el("b", {}, x.id), " ", el("strong", {}, x.title + ". "), x.text)));
  rebuild();
})();
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Local review and blind labeling UI for the FP2 corpus.")
    parser.add_argument("mode", choices=["review", "label"])
    parser.add_argument("--column", choices=["labeler_a", "labeler_b"],
                        help="label mode: which golden.csv column is yours")
    parser.add_argument("--include-golden", action="store_true",
                        help="review mode: also show golden cases (unblinds them)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if args.mode == "label" and not args.column:
        parser.error("label mode needs --column labeler_a or --column labeler_b")
    settings.update(mode=args.mode, column=args.column, include_golden=args.include_golden)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    target = f"golden.csv column {args.column}" if args.mode == "label" else os.path.relpath(SHEET, ROOT)
    print(f"{args.mode} tool at {url}  (Ctrl+C to stop)")
    print(f"writes to {target}")
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
