// Typed client for the FastAPI backend. Types mirror app/src/kangaroo/db/records.py.
import { useCallback, useEffect, useState } from "react";

export type Json = string | number | boolean | null | Json[] | { [key: string]: Json };

export type EvaluationStatus = "running" | "completed" | "failed";

export interface CaseSummary {
  id: string;
  source: "corpus" | "custom";
  meeting_type: string;
  meeting_date: string | null;
  candidate_action: string;
  golden_label: string | null;
  last_label: string | null;
}

export interface Segment {
  segment_id: string;
  speaker_id: string;
  speaker: string;
  text: string;
}

export interface StoredCase {
  case: {
    id: string;
    content: {
      meeting_id: string;
      meeting_type: string;
      meeting_date: string | null;
      meeting_weekday: string | null;
      meeting_timezone: string | null;
      segments: Segment[];
      candidate_action: string;
      evidence: { [key: string]: Json };
    };
  };
  source: "corpus" | "custom";
  golden: { case_id: string; final: string; notes: string; action_tier: string } | null;
}

export interface ProposedAction {
  restrictiveness: number;
  summary: string;
  requires_approval: boolean;
  approver: string;
}

export interface Evaluation {
  id: string;
  case_id: string;
  status: EvaluationStatus;
  verdict: string | null;
  tier: string | null;
  label: string | null;
  rule_ids: string[];
  rationale: string;
  proposed_action: ProposedAction | null;
  cited_segment_ids: string[];
  evidence_refs: string[];
  flags: string[];
  models: { [role: string]: Json };
  policy_version: string;
  golden_label: string | null;
  golden_match: boolean | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

export type TraceKind =
  | "intake"
  | "route"
  | "tool_call"
  | "tool_result"
  | "findings"
  | "adjudication"
  | "guard"
  | "decision"
  | "error";

export interface TraceRecord {
  seq: number;
  event: {
    node: string;
    kind: TraceKind;
    message: string;
    payload: { [key: string]: Json };
    at: string;
  };
}

export interface Review {
  id: number;
  evaluation_id: string;
  decision: "approve" | "reject";
  reviewer: string;
  note: string;
  created_at: string;
}

export interface RunDetail {
  evaluation: Evaluation;
  trace: TraceRecord[];
  reviews: Review[];
}

export interface Rule {
  id: string;
  tier: string;
  name: string;
  text: string;
}

export interface PolicyView {
  version: string;
  rules: Rule[];
  markdown: string;
}

const TOKEN_KEY = "kangaroo.accessToken";

export function readToken(): string {
  try {
    return window.localStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

export function saveToken(token: string) {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Private windows can block storage; the token then lasts only for this page.
  }
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = readToken();

  if (token) {
    headers.set("x-access-token", token);
  }

  if (init.body) {
    headers.set("content-type", "application/json");
  }

  const response = await fetch(path, { ...init, headers });

  if (!response.ok) {
    let detail = response.statusText;

    try {
      const body: { detail?: string } = await response.json();
      detail = body.detail ?? detail;
    } catch {
      // Non-JSON error body; keep the status text.
    }

    throw new ApiError(response.status, detail);
  }

  const data: T = await response.json();

  return data;
}

export const api = {
  cases: () => request<CaseSummary[]>("/api/cases"),
  getCase: (id: string) => request<StoredCase>(`/api/cases/${encodeURIComponent(id)}`),
  evaluations: (caseId?: string) =>
    request<Evaluation[]>(
      caseId ? `/api/evaluations?case_id=${encodeURIComponent(caseId)}` : "/api/evaluations",
    ),
  run: (id: string) => request<RunDetail>(`/api/runs/${id}`),
  startRun: (caseId: string) =>
    request<{ evaluation_id: string }>("/api/runs", {
      method: "POST",
      body: JSON.stringify({ case_id: caseId }),
    }),
  review: (evaluationId: string, decision: Review["decision"], reviewer: string, note: string) =>
    request<Review>(`/api/evaluations/${evaluationId}/reviewer-decision`, {
      method: "POST",
      body: JSON.stringify({ decision, reviewer, note }),
    }),
  policy: () => request<PolicyView>("/api/policy"),
};

export interface Loaded<T> {
  data: T | null;
  error: ApiError | null;
  reload: () => void;
}

/** Fetch once per `key` change. `reload` refetches without clearing the old data. */
export function useApi<T>(key: string | null, load: () => Promise<T>): Loaded<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (key === null) {
      return;
    }

    let cancelled = false;

    load().then(
      (value) => {
        if (!cancelled) {
          setData(value);
          setError(null);
        }
      },
      (reason: Error) => {
        if (!cancelled) {
          setError(reason instanceof ApiError ? reason : new ApiError(0, reason.message));
        }
      },
    );

    return () => {
      cancelled = true;
    };
    // `load` is a fresh closure every render; `key` is what identifies the request.
  }, [key, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);

  return { data, error, reload };
}

export interface RunStream {
  trace: TraceRecord[];
  /** The finished evaluation, once the server sends `done`. */
  finished: Evaluation | null;
}

/** Live trace for a run over SSE. Completed runs replay their stored trace, then finish. */
export function useRunStream(evaluationId: string | null): RunStream {
  const [trace, setTrace] = useState<TraceRecord[]>([]);
  const [finished, setFinished] = useState<Evaluation | null>(null);

  useEffect(() => {
    setTrace([]);
    setFinished(null);

    if (!evaluationId) {
      return;
    }

    const token = readToken();
    const query = token ? `?access_token=${encodeURIComponent(token)}` : "";
    const source = new EventSource(`/api/runs/${evaluationId}/events${query}`);

    source.addEventListener("trace", (message) => {
      const record: TraceRecord = JSON.parse(message.data);

      // The browser reconnects with Last-Event-ID, but guard against repeats anyway.
      setTrace((current) =>
        current.some((r) => r.seq === record.seq) ? current : [...current, record],
      );
    });

    source.addEventListener("done", (message) => {
      const evaluation: Evaluation = JSON.parse(message.data);
      setFinished(evaluation);
      source.close();
    });

    return () => source.close();
  }, [evaluationId]);

  return { trace, finished };
}
