import { useState } from "react";

import type { CaseSummary } from "@/api.ts";
import { Notice, TopBar } from "@/components/Shell.tsx";
import { VerdictPill } from "@/components/Verdict.tsx";
import { href } from "@/route.ts";

const FILTERS = ["All", "Golden", "Run", "Not run"] as const;

type Filter = (typeof FILTERS)[number];

function keep(item: CaseSummary, filter: Filter): boolean {
  switch (filter) {
    case "Golden":
      return item.golden_label !== null;
    case "Run":
      return item.last_label !== null;
    case "Not run":
      return item.last_label === null;
    default:
      return true;
  }
}

export function CasesScreen({ cases, error }: { cases: CaseSummary[] | null; error: string }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("Golden");
  const needle = query.trim().toLowerCase();

  const shown = (cases ?? []).filter(
    (item) =>
      keep(item, filter) &&
      (!needle ||
        item.id.toLowerCase().includes(needle) ||
        item.candidate_action.toLowerCase().includes(needle) ||
        item.meeting_type.toLowerCase().includes(needle)),
  );

  return (
    <>
      <TopBar crumbs={["Cases"]} />
      <div className="flex flex-wrap items-center gap-2 border-b border-line bg-white px-6 py-3">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search cases"
          className="w-72 max-w-full rounded-lg border border-line bg-cream/50 px-3 py-1.5 text-sm outline-none placeholder:text-ink-3 focus:border-ink-3"
        />
        {FILTERS.map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => setFilter(name)}
            className={`rounded-full border px-3 py-1 text-xs ${
              name === filter
                ? "border-ink bg-ink text-cream"
                : "border-line bg-white text-ink-2 hover:border-ink-3"
            }`}
          >
            {name}
          </button>
        ))}
        <span className="ml-auto text-xs text-ink-3">{shown.length} shown</span>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto bg-white">
        {error && (
          <div className="p-6">
            <Notice tone="error">{error}</Notice>
          </div>
        )}
        <div className="grid grid-cols-[88px_130px_1fr_140px_140px] gap-4 border-b border-line bg-cream/50 px-6 py-2 text-xs font-medium text-ink-3">
          <span>Case</span>
          <span>Meeting</span>
          <span>Candidate action</span>
          <span>Golden</span>
          <span>Latest run</span>
        </div>
        {shown.map((item) => (
          <a
            key={item.id}
            href={href({ screen: "case", caseId: item.id })}
            className="grid w-full grid-cols-[88px_130px_1fr_140px_140px] items-center gap-4 border-b border-line px-6 py-3 text-left text-sm transition-colors hover:bg-cream/50"
          >
            <span className="font-mono text-[13px]">{item.id}</span>
            <span className="truncate text-ink-2 capitalize">{item.meeting_type}</span>
            <span className="truncate text-ink-2">{item.candidate_action}</span>
            <span>
              {item.golden_label ? (
                <VerdictPill label={item.golden_label} />
              ) : (
                <span className="text-xs text-ink-3">—</span>
              )}
            </span>
            <span>
              {item.last_label ? (
                <VerdictPill label={item.last_label} />
              ) : (
                <span className="text-xs text-ink-3">Not run yet</span>
              )}
            </span>
          </a>
        ))}
        {cases === null && !error && <p className="px-6 py-4 text-sm text-ink-3">Loading cases</p>}
      </div>
    </>
  );
}
