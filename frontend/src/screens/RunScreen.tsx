import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";

import {
  ApiError,
  api,
  type Evaluation,
  type Json,
  type Review,
  type Segment,
  type StoredCase,
  type TraceRecord,
  useApi,
  useRunStream,
} from "@/api.ts";
import { AsciiSpinner } from "@/components/Ascii.tsx";
import { DitherField } from "@/components/DitherField.tsx";
import { type AgentActivity, IDLE, Notice, TopBar } from "@/components/Shell.tsx";
import { VerdictPill } from "@/components/Verdict.tsx";
import { navigate } from "@/route.ts";

const EASE = [0.22, 1, 0.36, 1] as const;
const REVIEWER_KEY = "kangaroo.reviewer";

const FLAG_TEXT = new Map([
  ["possible_injection", "Possible prompt injection in the transcript or evidence"],
  ["approver_is_proposer", "An approver is also a proposer of this action"],
  ["agent_error", "An agent failed during this run"],
  ["evidence_incomplete", "The adjudicator asked for evidence that could not be gathered"],
]);

type Finding = { task: string; status: string; summary: string; sources: string[] };

function findingsOf(payload: { [key: string]: Json }): Finding[] {
  const raw = payload.findings;

  if (!Array.isArray(raw)) {
    return [];
  }

  // SAFETY: the evidence node writes EvidenceFinding.model_dump() items here (graph.py).
  return raw as Finding[];
}

function seconds(evaluation: Evaluation): string {
  if (!evaluation.finished_at) {
    return "";
  }

  const ms = Date.parse(evaluation.finished_at) - Date.parse(evaluation.created_at);

  return `${(ms / 1000).toFixed(1)}s`;
}

function formatDate(value: string | null): string {
  if (!value) {
    return "date unknown";
  }

  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function Transcript({ segments, cited }: { segments: Segment[]; cited: ReadonlySet<string> }) {
  return (
    <div className="space-y-4">
      {segments.map((segment) => {
        const isCited = cited.has(segment.segment_id);

        return (
          <div key={segment.segment_id} className="flex gap-3">
            <span
              title={segment.segment_id}
              className="mt-0.5 w-8 shrink-0 font-mono text-[11px] text-ink-3"
            >
              {segment.segment_id.replace(/^.*-/, "")}
            </span>
            <div>
              <p className="text-[13px] font-medium">{segment.speaker}</p>
              <p
                className={`mt-0.5 text-[13px] leading-relaxed ${
                  isCited
                    ? "text-ink underline decoration-butter decoration-2 underline-offset-4"
                    : "text-ink-2"
                }`}
              >
                {segment.text}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function TraceDetail({ record }: { record: TraceRecord }) {
  const { kind, payload } = record.event;

  if (kind === "tool_call") {
    return (
      <p className="mt-1.5 rounded-lg bg-cream-2 px-3 py-2 font-mono text-[11.5px] break-all text-ink-2">
        <span className="text-ink-3">└ args </span>
        {JSON.stringify(payload.args ?? {})}
      </p>
    );
  }

  if (kind === "tool_result") {
    return (
      <details className="mt-1.5 rounded-lg bg-cream-2 px-3 py-2 text-[11.5px]">
        <summary className="cursor-pointer text-ink-3">Show output</summary>
        <pre className="mt-2 max-h-64 overflow-auto font-mono break-all whitespace-pre-wrap text-ink-2">
          {String(payload.output ?? "")}
        </pre>
      </details>
    );
  }

  if (kind === "findings") {
    return (
      <div className="mt-2 space-y-1.5 rounded-lg bg-cream-2 px-3 py-2">
        {findingsOf(payload).map((finding) => (
          <p key={`${finding.task}-${finding.summary}`} className="text-[12px] text-ink-2">
            <span className="font-mono text-[11px] text-ink-3">
              {finding.task} · {finding.status}
            </span>
            <br />
            {finding.summary}
          </p>
        ))}
      </div>
    );
  }

  if (kind === "guard" && Array.isArray(payload.problems)) {
    return (
      <ul className="mt-1.5 list-disc pl-4 text-[12px] text-ink-2">
        {payload.problems.map((problem) => (
          <li key={String(problem)}>{String(problem)}</li>
        ))}
      </ul>
    );
  }

  return null;
}

function TraceList({ trace, running }: { trace: TraceRecord[]; running: boolean }) {
  return (
    <ol className="relative space-y-4 before:absolute before:top-2 before:bottom-2 before:left-[7px] before:w-px before:bg-line">
      <AnimatePresence initial={false}>
        {trace.map((record) => {
          const { node, kind, message, payload } = record.event;

          const flagged =
            payload.possible_injection === true ||
            (Array.isArray(payload.possible_injection) && payload.possible_injection.length > 0);

          const isError = kind === "error";

          return (
            <motion.li
              key={record.seq}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, ease: EASE }}
              className="relative pl-7"
            >
              <span className="absolute top-1 left-0 grid size-[15px] place-items-center rounded-full border border-line bg-white">
                <span className={`size-[5px] rounded-full ${isError ? "bg-bad" : "bg-forest"}`} />
              </span>
              <p className="flex items-center gap-2 text-xs font-medium text-ink-3">
                <span className="capitalize">{node}</span>
                <span className="font-mono text-[10.5px] font-normal">{kind}</span>
                {flagged && (
                  <span className="rounded bg-hold-bg px-1.5 text-[10.5px] text-hold">
                    possible injection
                  </span>
                )}
              </p>
              <p className={`mt-0.5 text-[13px] leading-snug ${isError ? "text-bad" : ""}`}>
                {message}
              </p>
              <TraceDetail record={record} />
            </motion.li>
          );
        })}
      </AnimatePresence>
      {running && (
        <li className="relative flex items-center gap-2 pl-7 text-[13px] text-ink-3">
          <AsciiSpinner className="absolute left-[3px] text-forest" />
          Working
        </li>
      )}
    </ol>
  );
}

function readReviewer(): string {
  try {
    return window.localStorage.getItem(REVIEWER_KEY) ?? "";
  } catch {
    return "";
  }
}

function ReviewForm({ evaluation, onSaved }: { evaluation: Evaluation; onSaved: () => void }) {
  const [reviewer, setReviewer] = useState(readReviewer);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = (decision: Review["decision"]) => async () => {
    setSaving(true);
    setError("");

    try {
      window.localStorage.setItem(REVIEWER_KEY, reviewer);
    } catch {
      // Storage blocked; the name just won't be remembered.
    }

    try {
      await api.review(evaluation.id, decision, reviewer.trim(), note.trim());
      setNote("");
      onSaved();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Couldn't save the review.");
    } finally {
      setSaving(false);
    }
  };

  const disabled = saving || !reviewer.trim();

  return (
    <form className="space-y-2">
      <div className="flex gap-2">
        <input
          value={reviewer}
          onChange={(event) => setReviewer(event.target.value)}
          placeholder="Your name"
          className="w-1/3 min-w-0 rounded-lg border border-line bg-white px-2.5 py-1.5 text-[13px] outline-none focus:border-ink-3"
        />
        <input
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Note (optional)"
          className="min-w-0 flex-1 rounded-lg border border-line bg-white px-2.5 py-1.5 text-[13px] outline-none focus:border-ink-3"
        />
      </div>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={submit("approve")}
          disabled={disabled}
          className="flex-1 rounded-lg bg-ink py-2.5 text-sm font-medium text-cream hover:bg-ink-2 disabled:opacity-40"
        >
          Approve
        </button>
        <button
          type="button"
          onClick={submit("reject")}
          disabled={disabled}
          className="flex-1 rounded-lg border border-line bg-white py-2.5 text-sm font-medium text-ink-2 hover:border-bad/40 hover:text-bad disabled:opacity-40"
        >
          Reject
        </button>
      </div>
      {error && <Notice tone="error">{error}</Notice>}
    </form>
  );
}

interface DecisionPanelProps {
  evaluation: Evaluation | null;
  running: boolean;
  reviews: Review[];
  onReviewed: () => void;
}

function DecisionPanel({ evaluation, running, reviews, onReviewed }: DecisionPanelProps) {
  const completed = evaluation?.status === "completed";

  return (
    <div className="relative flex min-h-full flex-col overflow-hidden rounded-xl border border-line bg-white">
      <AnimatePresence mode="wait">
        {evaluation && completed && evaluation.label ? (
          <motion.div
            key="decision"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: EASE }}
            className="flex min-h-[440px] flex-1 flex-col p-5"
          >
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-medium">Decision</p>
              <VerdictPill label={evaluation.label} />
            </div>
            {evaluation.golden_match !== null && (
              <p className={`mt-2 text-xs ${evaluation.golden_match ? "text-ok" : "text-bad"}`}>
                {evaluation.golden_match ? "Matches" : "Doesn't match"} the golden label
                {evaluation.golden_label ? ` (${evaluation.golden_label})` : ""}
              </p>
            )}
            <p className="mt-6 text-xs font-medium text-ink-3">Proposed action</p>
            <p className="mt-1.5 text-[17px] leading-snug font-medium tracking-[-0.01em]">
              {evaluation.proposed_action?.summary}
            </p>
            <p className="mt-4 text-[13px] leading-relaxed text-ink-2">{evaluation.rationale}</p>
            {[...evaluation.cited_segment_ids, ...evaluation.evidence_refs].length > 0 && (
              <div className="mt-4 flex flex-wrap gap-1.5">
                {[...evaluation.cited_segment_ids, ...evaluation.evidence_refs].map((ref) => (
                  <span
                    key={ref}
                    className="rounded-md border border-line bg-cream px-2 py-0.5 font-mono text-[11px] text-ink-2"
                  >
                    {ref}
                  </span>
                ))}
              </div>
            )}
            {evaluation.flags.length > 0 && (
              <div className="mt-4 space-y-1">
                {evaluation.flags.map((flag) => (
                  <p key={flag} className="rounded-md bg-hold-bg px-2 py-1 text-xs text-hold">
                    {FLAG_TEXT.get(flag) ?? flag}
                  </p>
                ))}
              </div>
            )}
            <div className="mt-auto border-t border-line pt-4">
              {reviews.length > 0 && (
                <ul className="mb-3 space-y-1 text-xs text-ink-2">
                  {reviews.map((review) => (
                    <li key={review.id}>
                      <span
                        className={
                          review.decision === "approve"
                            ? "font-medium text-ok"
                            : "font-medium text-bad"
                        }
                      >
                        {review.decision === "approve" ? "Approved" : "Rejected"}
                      </span>{" "}
                      by {review.reviewer}
                      {review.note && <span className="text-ink-3"> · {review.note}</span>}
                    </li>
                  ))}
                </ul>
              )}
              <p className="mb-3 text-xs text-ink-3">
                {evaluation.proposed_action?.requires_approval
                  ? `Approver: ${evaluation.proposed_action.approver || "a reviewer"}. `
                  : ""}
                Approving records the decision only. Nothing is executed.
              </p>
              <ReviewForm evaluation={evaluation} onSaved={onReviewed} />
            </div>
          </motion.div>
        ) : evaluation?.status === "failed" ? (
          <motion.div key="failed" className="p-5">
            <p className="text-sm font-medium">Run failed</p>
            <p className="mt-2 font-mono text-[12px] break-all text-bad">{evaluation.error}</p>
          </motion.div>
        ) : (
          <motion.div key="pending" exit={{ opacity: 0 }} className="absolute inset-0 bg-forest">
            <DitherField
              intensity={running ? 0.75 : 0.3}
              cell={4}
              className="absolute inset-0 size-full text-mint/70"
            />
            <div className="absolute bottom-5 left-5 rounded-full bg-forest-2/80 px-3 py-1 text-xs text-mint backdrop-blur">
              {running ? "Waiting for the adjudicator" : "Not run yet"}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

interface RunScreenProps {
  caseId: string;
  /** The run to show (live if still running), or null when the case has none. */
  initial: Evaluation | null;
  onActivity: (activity: AgentActivity) => void;
}

/** A case with one of its runs: transcript, live agent trace, and the decision. */
export function RunScreen({ caseId, initial, onActivity }: RunScreenProps) {
  const evaluationId = initial?.id ?? null;
  const stored = useApi<StoredCase>(`case:${caseId}`, () => api.getCase(caseId));
  const { trace, finished } = useRunStream(evaluationId);
  const running = initial?.status === "running" && finished === null;

  // Reviews live on the run detail; fetch it once the run is no longer running.
  const detail = useApi(evaluationId && !running ? `run:${evaluationId}` : null, () =>
    api.run(evaluationId ?? ""),
  );

  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState("");

  const evaluation = detail.data?.evaluation ?? finished ?? (running ? null : initial);

  useEffect(() => {
    const visited = new Set(trace.map((record) => record.event.node));
    const active = trace.at(-1)?.event.node ?? null;
    onActivity(evaluationId ? { running, visited, active } : IDLE);
  }, [trace, running, evaluationId, onActivity]);

  useEffect(() => () => onActivity(IDLE), [onActivity]);

  const start = async () => {
    setStarting(true);
    setStartError("");

    try {
      const { evaluation_id } = await api.startRun(caseId);
      navigate({ screen: "run", evaluationId: evaluation_id });
    } catch (reason) {
      setStartError(reason instanceof ApiError ? reason.message : "Couldn't start the run.");
    } finally {
      setStarting(false);
    }
  };

  if (stored.error) {
    return (
      <div className="p-6">
        <Notice tone="error">{stored.error.message}</Notice>
      </div>
    );
  }

  const content = stored.data?.case.content;
  const golden = stored.data?.golden;
  const cited = new Set(evaluation?.cited_segment_ids ?? []);

  return (
    <>
      <TopBar crumbs={evaluationId ? ["Runs", caseId] : ["Cases", caseId]}>
        {running && (
          <span className="flex items-center gap-1.5 rounded-full bg-cream-2 px-2.5 py-1 text-xs font-medium text-ink-2">
            <AsciiSpinner className="text-forest" /> Running
          </span>
        )}
        {evaluation?.status === "completed" && (
          <span className="rounded-full bg-ok-bg px-2.5 py-1 text-xs font-medium text-ok">
            Completed in {seconds(evaluation)}
          </span>
        )}
        {evaluation?.status === "failed" && (
          <span className="rounded-full bg-bad-bg px-2.5 py-1 text-xs font-medium text-bad">
            Failed
          </span>
        )}
        <button
          type="button"
          onClick={start}
          disabled={starting || running}
          className="rounded-lg bg-ink px-3 py-1.5 text-sm font-medium text-cream hover:bg-ink-2 disabled:opacity-40"
        >
          {evaluationId ? "Run again" : "Run case"}
        </button>
      </TopBar>
      <div className="border-b border-line bg-white px-6 py-4">
        <div className="flex items-start justify-between gap-8">
          <div className="min-w-0">
            <p className="text-xs text-ink-3">
              {content ? (
                <>
                  <span className="capitalize">{content.meeting_type}</span> ·{" "}
                  {formatDate(content.meeting_date)}
                </>
              ) : (
                "Loading case"
              )}
            </p>
            <h1 className="mt-1 line-clamp-2 text-lg leading-snug font-medium tracking-[-0.01em]">
              {content?.candidate_action}
            </h1>
          </div>
          <div className="flex shrink-0 items-center gap-6 text-xs text-ink-3">
            {golden && (
              <div>
                <p>Golden label</p>
                <div className="mt-1">
                  <VerdictPill label={golden.final} />
                </div>
              </div>
            )}
            {golden && (
              <div>
                <p>Action tier</p>
                <p className="mt-1.5 font-medium text-ink">{golden.action_tier}</p>
              </div>
            )}
          </div>
        </div>
        {startError && (
          <div className="mt-3">
            <Notice tone="error">{startError}</Notice>
          </div>
        )}
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-1 divide-line overflow-y-auto bg-white lg:grid-cols-[1fr_1fr_380px] lg:divide-x lg:overflow-hidden">
        <div className="min-h-0 p-6 lg:overflow-y-auto">
          <p className="mb-4 text-xs font-medium text-ink-3">Transcript</p>
          {content && <Transcript segments={content.segments} cited={cited} />}
        </div>
        <div className="min-h-0 p-6 lg:overflow-y-auto">
          <p className="mb-4 text-xs font-medium text-ink-3">Agent trace</p>
          {evaluationId ? (
            <TraceList trace={trace} running={running} />
          ) : (
            <p className="text-[13px] text-ink-3">
              No runs for this case yet. Press "Run case" to send it through the agents.
            </p>
          )}
        </div>
        <div className="min-h-0 bg-cream/40 p-4 lg:overflow-y-auto">
          <DecisionPanel
            evaluation={evaluation}
            running={running}
            reviews={detail.data?.reviews ?? []}
            onReviewed={detail.reload}
          />
        </div>
      </div>
    </>
  );
}
