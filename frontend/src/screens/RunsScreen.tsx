import type { Evaluation } from "@/api.ts";
import { Notice, TopBar } from "@/components/Shell.tsx";
import { VerdictPill } from "@/components/Verdict.tsx";
import { href } from "@/route.ts";

function when(value: string): string {
  return new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function Outcome({ run }: { run: Evaluation }) {
  if (run.status === "running") {
    return <span className="text-xs text-ink-3">Running</span>;
  }

  if (run.status === "failed" || !run.label) {
    return <span className="text-xs text-bad">Failed</span>;
  }

  return <VerdictPill label={run.label} />;
}

function Match({ run }: { run: Evaluation }) {
  if (run.golden_match === null) {
    return <span className="text-xs text-ink-3">—</span>;
  }

  return run.golden_match ? (
    <span className="text-xs font-medium text-ok">Match</span>
  ) : (
    <span className="text-xs font-medium text-bad">Mismatch</span>
  );
}

/** Saved evaluations, newest first. Each one reopens with its stored trace. */
export function RunsScreen({ runs, error }: { runs: Evaluation[] | null; error: string }) {
  const scored = (runs ?? []).filter((run) => run.golden_match !== null);
  const matched = scored.filter((run) => run.golden_match).length;

  return (
    <>
      <TopBar crumbs={["Runs"]}>
        {scored.length > 0 && (
          <span className="text-xs text-ink-3">
            {matched}/{scored.length} golden runs matched
          </span>
        )}
      </TopBar>
      <div className="min-h-0 flex-1 overflow-y-auto bg-white">
        {error && (
          <div className="p-6">
            <Notice tone="error">{error}</Notice>
          </div>
        )}
        <div className="grid grid-cols-[88px_150px_150px_90px_1fr_130px] gap-4 border-b border-line bg-cream/50 px-6 py-2 text-xs font-medium text-ink-3">
          <span>Case</span>
          <span>Decision</span>
          <span>Golden</span>
          <span>Result</span>
          <span>Proposed action</span>
          <span>Started</span>
        </div>
        {(runs ?? []).map((run) => (
          <a
            key={run.id}
            href={href({ screen: "run", evaluationId: run.id })}
            className="grid w-full grid-cols-[88px_150px_150px_90px_1fr_130px] items-center gap-4 border-b border-line px-6 py-3 text-left text-sm transition-colors hover:bg-cream/50"
          >
            <span className="font-mono text-[13px]">{run.case_id}</span>
            <span>
              <Outcome run={run} />
            </span>
            <span>
              {run.golden_label ? (
                <VerdictPill label={run.golden_label} />
              ) : (
                <span className="text-xs text-ink-3">—</span>
              )}
            </span>
            <Match run={run} />
            <span className="truncate text-ink-2">
              {run.proposed_action?.summary ?? run.error ?? ""}
            </span>
            <span className="text-xs text-ink-3">{when(run.created_at)}</span>
          </a>
        ))}
        {runs?.length === 0 && (
          <p className="px-6 py-4 text-sm text-ink-3">No runs yet. Open a case and run it.</p>
        )}
      </div>
    </>
  );
}
