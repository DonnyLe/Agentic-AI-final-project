import { useCallback, useEffect, useState } from "react";

import { api, type Json, useApi } from "@/api.ts";
import { type AgentActivity, IDLE, Notice, Sidebar, TokenGate } from "@/components/Shell.tsx";
import { useRoute } from "@/route.ts";
import { CasesScreen } from "@/screens/CasesScreen.tsx";
import { PolicyScreen } from "@/screens/PolicyScreen.tsx";
import { RunScreen } from "@/screens/RunScreen.tsx";
import { RunsScreen } from "@/screens/RunsScreen.tsx";

/** A case's page shows its latest run, if it has one. */
function CaseRoute({
  caseId,
  onActivity,
}: {
  caseId: string;
  onActivity: (a: AgentActivity) => void;
}) {
  const runs = useApi(`evaluations:${caseId}`, () => api.evaluations(caseId));

  if (runs.data === null && !runs.error) {
    return null;
  }

  return <RunScreen caseId={caseId} initial={runs.data?.[0] ?? null} onActivity={onActivity} />;
}

/** A run's page needs its case ID before it can show the transcript. */
function RunRoute({
  evaluationId,
  onActivity,
}: {
  evaluationId: string;
  onActivity: (a: AgentActivity) => void;
}) {
  const run = useApi(`run:${evaluationId}`, () => api.run(evaluationId));

  if (run.error) {
    return (
      <div className="p-6">
        <Notice tone="error">{run.error.message}</Notice>
      </div>
    );
  }

  if (!run.data) {
    return null;
  }

  return (
    <RunScreen
      key={evaluationId}
      caseId={run.data.evaluation.case_id}
      initial={run.data.evaluation}
      onActivity={onActivity}
    />
  );
}

function modelLabel(models: { [role: string]: Json } | undefined): string {
  const names = [...new Set(Object.values(models ?? {}).map(String))];

  return names.map((name) => name.replace(/^.*\//, "").replace(/:free$/, "")).join(", ") || "—";
}

export function App() {
  const route = useRoute();
  const [activity, setActivity] = useState<AgentActivity>(IDLE);
  const onActivity = useCallback((next: AgentActivity) => setActivity(next), []);

  // Refetch the lists whenever the screen changes, so new runs show up.
  const listKey = route.screen === "run" || route.screen === "case" ? "detail" : route.screen;
  const cases = useApi(`cases:${listKey}`, api.cases);
  const runs = useApi(`runs:${listKey}`, () => api.evaluations());
  const policy = useApi("policy", api.policy);

  const { reload: reloadRuns } = runs;
  const { reload: reloadCases } = cases;

  // When a run finishes, refresh the counts and latest labels.
  useEffect(() => {
    if (!activity.running) {
      reloadRuns();
      reloadCases();
    }
  }, [activity.running, reloadRuns, reloadCases]);

  if (policy.error?.status === 401) {
    return <TokenGate />;
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        route={route}
        caseCount={cases.data?.length}
        runCount={runs.data?.length}
        activity={activity}
        model={modelLabel(runs.data?.[0]?.models)}
        policyVersion={policy.data ? `v${policy.data.version}` : "—"}
      />
      <main className="flex min-w-0 flex-1 flex-col">
        {route.screen === "cases" && (
          <CasesScreen cases={cases.data} error={cases.error?.message ?? ""} />
        )}
        {route.screen === "case" && (
          <CaseRoute key={route.caseId} caseId={route.caseId} onActivity={onActivity} />
        )}
        {route.screen === "runs" && (
          <RunsScreen runs={runs.data} error={runs.error?.message ?? ""} />
        )}
        {route.screen === "run" && (
          <RunRoute
            key={route.evaluationId}
            evaluationId={route.evaluationId}
            onActivity={onActivity}
          />
        )}
        {route.screen === "policy" && (
          <PolicyScreen policy={policy.data} error={policy.error?.message ?? ""} />
        )}
      </main>
    </div>
  );
}
