"""Stand-in corpus checker for FP2.

NOT the official course checking scripts (we do not have them). It checks the
requirements quoted in our F2 document plus internal consistency:
  >=100 cases, all four tiers, >=15% violating, >=5 ambiguous, >=2 injection,
  golden set >=30 and containing every ambiguous and injection case,
  unique IDs, valid label syntax, review completion, no metadata leakage in
  the labelers' packet.

Usage: python3 scripts/check_corpus.py [dir]
Exit code 1 if any ERROR; WARN lines are things to resolve before submission.
"""
import csv
import json
import os
import re
import sys
from collections import Counter

TIERS = {"T1", "T2", "T3", "T4"}
SEEDED_TIERS = TIERS | {"none"}
RULES = {"R1.1", "R1.2", "R1.3", "R2.1", "R2.2", "R2.3", "R2.4",
         "R3.1", "R3.2", "R3.3", "R4.1", "R4.2", "R4.3", "R4.4"}
REQUIRED = ["id", "seeded_tier", "seeded_rules", "ambiguous", "injection",
            "generated_by", "reviewed_by", "content", "target_tier",
            "ambiguity_type", "scenario_family", "generation_note",
            "review_status"]
CONTENT_REQUIRED = ["meeting_id", "segments", "candidate_action", "evidence"]
HIDDEN = {"seeded_tier", "seeded_rules", "target_tier", "ambiguous",
          "ambiguity_type", "injection", "scenario_family", "generation_note",
          "generated_by", "reviewed_by", "review_status"}
LABEL_RE = re.compile(r"^(none|T[1-4]( R\d\.\d)+)$")

errors, warns = [], []
err = errors.append
warn = warns.append


def normalize(label):
    """Sort the rule IDs so 'T4 R4.3 R4.1' and 'T4 R4.1 R4.3' compare equal."""
    tier, *rules = label.split()
    return " ".join([tier] + sorted(rules))


def cohen_kappa(a, b):
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb[k] for k in ca) / (n * n)
    if expected == 1:
        return 1.0
    return (observed - expected) / (1 - expected)


def check(d):
    path = lambda n: os.path.join(d, n)
    for n in ["policy.md", "corpus.jsonl", "golden.csv", "README.md"]:
        if not os.path.exists(path(n)):
            err(f"missing file {n}")
    if errors:
        return

    cases = []
    with open(path("corpus.jsonl")) as f:
        for ln, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError as e:
                err(f"corpus.jsonl line {ln}: invalid JSON ({e})")
    n = len(cases)
    by_id = {}
    seg_ids = Counter()
    for c in cases:
        cid = c.get("id", "?")
        for k in REQUIRED:
            if k not in c:
                err(f"{cid}: missing field {k}")
        content = c.get("content")
        if not isinstance(content, dict):
            err(f"{cid}: content is not an object")
            content = {}
        for k in CONTENT_REQUIRED:
            if k not in content:
                err(f"{cid}: missing content.{k}")
        leak = HIDDEN & set(content)
        if leak:
            err(f"{cid}: content contains hidden metadata {sorted(leak)}")
        if cid in by_id:
            err(f"duplicate id {cid}")
        by_id[cid] = c
        if c.get("seeded_tier") not in SEEDED_TIERS:
            err(f"{cid}: bad seeded_tier {c.get('seeded_tier')}")
        if c.get("target_tier") not in TIERS:
            err(f"{cid}: bad target_tier {c.get('target_tier')}")
        bad = [r for r in c.get("seeded_rules", []) if r not in RULES]
        if bad:
            err(f"{cid}: unknown rule IDs {bad}")
        if c.get("ambiguous") and not c.get("ambiguity_type"):
            warn(f"{cid}: ambiguous but no ambiguity_type")
        if not content.get("segments"):
            err(f"{cid}: no transcript segments")
        for s in content.get("segments", []):
            seg_ids[s.get("segment_id")] += 1
        if not c.get("reviewed_by") or c.get("review_status") == "pending_human_review":
            warn(f"{cid}: not yet human-reviewed")
    for s, k in seg_ids.items():
        if k > 1:
            warn(f"segment_id {s} used {k} times")

    tiers = Counter(c.get("seeded_tier") for c in cases)
    viol = sum(1 for c in cases if c.get("seeded_rules"))
    amb = {c.get("id") for c in cases if c.get("ambiguous")}
    inj = {c.get("id") for c in cases if c.get("injection")}
    print(f"cases: {n}")
    print(f"tiers: {dict(sorted(tiers.items()))}")
    print(f"violating: {viol} ({viol / max(n, 1):.1%})  clean: {n - viol}")
    print(f"ambiguous: {len(amb)}  injection: {len(inj)}")
    print(f"scenario families: {len({c.get('scenario_family') for c in cases})}")
    if n < 100:
        err(f"only {n} cases (<100)")
    if not TIERS <= set(tiers):
        err(f"tiers missing: {TIERS - set(tiers)}")
    if viol / max(n, 1) < 0.15:
        err("violations <15%")
    if len(amb) < 5:
        err("fewer than 5 ambiguous cases")
    if len(inj) < 2:
        err("fewer than 2 injection cases")

    with open(path("golden.csv"), newline="") as f:
        rows = list(csv.DictReader(f))
    cols = {"case_id", "labeler_a", "labeler_b", "final", "notes"}
    if rows and not cols <= set(rows[0]):
        err(f"golden.csv columns {list(rows[0])} missing {cols - set(rows[0])}")
    gids = [r["case_id"] for r in rows]
    print(f"golden: {len(gids)}")
    if len(gids) < 30:
        err(f"golden set has {len(gids)} cases (<30)")
    if len(set(gids)) != len(gids):
        err("duplicate IDs in golden.csv")
    for g in gids:
        if g not in by_id:
            err(f"golden ID {g} not in corpus")
    for g in sorted((amb | inj) - set(gids)):
        err(f"ambiguous/injection case {g} missing from golden set")
    pairs = []
    for r in rows:
        for col in ("labeler_a", "labeler_b", "final"):
            v = (r.get(col) or "").strip()
            if not v:
                warn(f"golden {r['case_id']}: {col} empty")
            elif not LABEL_RE.match(v):
                err(f"golden {r['case_id']}: {col}={v!r} not 'none' or 'T<n> R<x.y>[ R<x.y>]'")
        a, b = (r.get("labeler_a") or "").strip(), (r.get("labeler_b") or "").strip()
        if LABEL_RE.match(a) and LABEL_RE.match(b):
            a, b = normalize(a), normalize(b)
            pairs.append((a, b))
            if a != b and not (r.get("notes") or "").strip():
                warn(f"golden {r['case_id']}: labelers disagree but notes empty")
    if pairs:
        la, lb = zip(*pairs)
        agree = sum(x == y for x, y in pairs)
        print(f"labeler agreement: {agree}/{len(pairs)} ({agree / len(pairs):.1%})  "
              f"Cohen's kappa: {cohen_kappa(la, lb):.3f}")

    pk = path("labeling_packet_for_labelers.jsonl")
    if os.path.exists(pk):
        with open(pk) as f:
            for line in f:
                if line.strip():
                    p = json.loads(line)
                    pid = p.get("id", "?")
                    extra = set(p) - {"id", "content"}
                    if extra:
                        err(f"labeler packet {pid} has fields other than id/content: {sorted(extra)}")
                    leak = HIDDEN & set(p.get("content") or {})
                    if leak:
                        err(f"labeler packet {pid} content leaks {sorted(leak)}")

    with open(path("README.md")) as f:
        if "TEAM TO COMPLETE" in f.read():
            warn("README.md still contains [TEAM TO COMPLETE] placeholders")


if __name__ == "__main__":
    check(sys.argv[1] if len(sys.argv) > 1 else ".")
    pending = sum("not yet human-reviewed" in w for w in warns)
    empty = sum(" empty" in w for w in warns)
    for w in warns:
        if "not yet human-reviewed" not in w and " empty" not in w:
            print("WARN ", w)
    if pending:
        print(f"WARN  {pending} cases not yet human-reviewed")
    if empty:
        print(f"WARN  {empty} empty golden label cells")
    for e in errors:
        print("ERROR", e)
    print("RESULT:", "FAIL" if errors else "PASS (with warnings)" if warns else "PASS")
    sys.exit(1 if errors else 0)
