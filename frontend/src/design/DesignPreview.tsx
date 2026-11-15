import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useState } from "react";

import { AsciiSpinner, type GraphNode } from "@/components/Ascii.tsx";
import { DitherField } from "@/components/DitherField.tsx";
import { VerdictPill } from "@/components/Verdict.tsx";
import { CASES, CITED, EVENTS, SEGMENTS } from "@/design/sample.ts";

const STEP_MS = 1400;
const HOLD_STEPS = 8;
const EASE = [0.22, 1, 0.36, 1] as const;

type Screen = "run" | "cases";

const AGENT_STEPS: GraphNode[] = ["intake", "supervisor", "evidence", "adjudicator", "guards"];

const NAV: { label: string; screen: Screen | null; count?: string }[] = [
  { label: "Cases", screen: "cases", count: "122" },
  { label: "Runs", screen: "run", count: "34" },
  { label: "Batch eval", screen: null },
  { label: "Policy", screen: null },
];

/** Replays the sample trace on a loop. */
function useReplay() {
  const [step, setStep] = useState(0);
  const total = EVENTS.length;

  useEffect(() => {
    const timer = window.setInterval(
      () => setStep((s) => (s >= total + HOLD_STEPS ? 0 : s + 1)),
      STEP_MS,
    );

    return () => window.clearInterval(timer);
  }, [total]);

  return { shown: EVENTS.slice(0, step), done: step >= total };
}

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="relative size-7 overflow-hidden rounded-lg bg-forest">
        <DitherField intensity={0.9} cell={2} className="absolute inset-0 size-full text-mint" />
      </div>
      <span className="text-[17px] font-semibold tracking-tight">Kangaroo</span>
    </div>
  );
}

function Transcript() {
  return (
    <div className="space-y-4">
      {SEGMENTS.map((segment) => {
        const cited = CITED.has(segment.id);

        return (
          <div key={segment.id} className="flex gap-3">
            <span className="mt-0.5 w-7 shrink-0 font-mono text-[11px] text-ink-3">
              {segment.id}
            </span>
            <div>
              <p className="text-[13px] font-medium">{segment.speaker}</p>
              <p
                className={`mt-0.5 text-[13px] leading-relaxed ${
                  cited
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

function TraceList({ shown, done }: { shown: typeof EVENTS; done: boolean }) {
  return (
    <ol className="relative space-y-4 before:absolute before:top-2 before:bottom-2 before:left-[7px] before:w-px before:bg-line">
      <AnimatePresence initial={false}>
        {shown.map((event, index) => (
          <motion.li
            key={`${index}-${event.node}`}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease: EASE }}
            className="relative pl-7"
          >
            <span className="absolute top-1 left-0 grid size-[15px] place-items-center rounded-full border border-line bg-white">
              <span className="size-[5px] rounded-full bg-forest" />
            </span>
            <p className="text-xs font-medium text-ink-3 capitalize">{event.node}</p>
            <p className="mt-0.5 text-[13px] leading-snug">{event.title}</p>
            {event.steps && (
              <div className="mt-2 space-y-1 rounded-lg bg-cream-2 px-3 py-2">
                {event.steps.map((step) => (
                  <p key={step} className="font-mono text-[11.5px] text-ink-2">
                    <span className="text-ink-3">└ </span>
                    {step}
                  </p>
                ))}
              </div>
            )}
          </motion.li>
        ))}
      </AnimatePresence>
      {!done && (
        <li className="relative flex items-center gap-2 pl-7 text-[13px] text-ink-3">
          <AsciiSpinner className="absolute left-[3px] text-forest" />
          Working
        </li>
      )}
    </ol>
  );
}

function DecisionPanel({ done }: { done: boolean }) {
  return (
    <div className="relative h-full min-h-[440px] overflow-hidden rounded-xl border border-line">
      <AnimatePresence mode="wait">
        {done ? (
          <motion.div
            key="decision"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: EASE }}
            className="flex h-full flex-col p-5"
          >
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">Decision</p>
              <VerdictPill label="T2 R2.3" />
            </div>
            <p className="mt-6 text-xs font-medium text-ink-3">Proposed action</p>
            <p className="mt-1.5 text-[19px] leading-snug font-medium tracking-[-0.01em]">
              File the ticket with the third-party cause marked{" "}
              <span className="font-serif text-[22px] font-normal italic">unverified</span>, and
              attach the lookups.
            </p>
            <p className="mt-4 text-[13px] leading-relaxed text-ink-2">
              The ticket names jwt-verify-lite 4.2.0 as a verified cause. The only support is that
              the version exists, and no upstream report backs it.
            </p>
            <div className="mt-4 flex flex-wrap gap-1.5">
              {["S05", "S07", "package_registry_lookup", "upstream_issue_lookup"].map((ref) => (
                <span
                  key={ref}
                  className="rounded-md border border-line bg-cream px-2 py-0.5 font-mono text-[11px] text-ink-2"
                >
                  {ref}
                </span>
              ))}
            </div>
            <div className="mt-auto border-t border-line pt-4">
              <p className="mb-3 text-xs text-ink-3">
                Approver: an engineer who didn't propose it. Approving records the decision only.
              </p>
              <div className="flex gap-2">
                <button className="flex-1 rounded-lg bg-ink py-2.5 text-sm font-medium text-cream hover:bg-ink-2">
                  Approve
                </button>
                <button className="flex-1 rounded-lg border border-line bg-white py-2.5 text-sm font-medium text-ink-2 hover:border-bad/40 hover:text-bad">
                  Reject
                </button>
              </div>
            </div>
          </motion.div>
        ) : (
          <motion.div key="pending" exit={{ opacity: 0 }} className="absolute inset-0 bg-forest">
            <DitherField
              intensity={0.75}
              cell={4}
              className="absolute inset-0 size-full text-mint/70"
            />
            <div className="absolute bottom-5 left-5 rounded-full bg-forest-2/80 px-3 py-1 text-xs text-mint backdrop-blur">
              Waiting for the adjudicator
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Sidebar({ screen, onNavigate }: { screen: Screen; onNavigate: (s: Screen) => void }) {
  const { shown, done } = useReplay();
  const visited = useMemo(() => new Set<GraphNode>(shown.map((e) => e.node)), [shown]);
  const active = done ? "decision" : (shown.at(-1)?.node ?? null);

  return (
    <aside className="flex h-screen w-[248px] shrink-0 flex-col border-r border-line bg-cream px-3 py-4">
      <div className="px-2">
        <Logo />
      </div>
      <nav className="mt-7 space-y-0.5">
        {NAV.map((item) => {
          const current = item.screen === screen;

          return (
            <button
              key={item.label}
              type="button"
              onClick={() => item.screen && onNavigate(item.screen)}
              className={`flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-sm transition-colors ${
                current
                  ? "bg-white font-medium text-ink shadow-card"
                  : "text-ink-2 hover:bg-cream-2"
              }`}
            >
              {item.label}
              {item.count && <span className="text-xs text-ink-3">{item.count}</span>}
            </button>
          );
        })}
      </nav>
      <div className="mt-auto space-y-3">
        <div className="relative overflow-hidden rounded-xl bg-forest p-3 text-cream">
          <DitherField
            intensity={done ? 0.35 : 0.8}
            cell={3}
            fadeFrom={0.2}
            className="absolute inset-0 size-full text-mint/40"
          />
          <div className="relative">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium">Agents</span>
              <span className="flex items-center gap-1 text-mint">
                {done ? (
                  "Idle"
                ) : (
                  <>
                    <AsciiSpinner /> 1 running
                  </>
                )}
              </span>
            </div>
            <ol className="mt-3 space-y-1 rounded-lg bg-forest-2/45 px-2.5 py-2 font-mono text-[11px]">
              {AGENT_STEPS.map((step) => {
                const reached = done || visited.has(step);

                const tone =
                  step === active ? "text-mint" : reached ? "text-cream" : "text-cream/40";

                const mark = step === active ? "●" : reached ? "✓" : "○";

                return (
                  <li key={step} className={`flex items-center gap-2 ${tone}`}>
                    <span>{mark}</span>
                    {step}
                  </li>
                );
              })}
            </ol>
          </div>
        </div>
        <div className="space-y-1 px-2 text-xs text-ink-3">
          <p className="flex justify-between">
            <span>Model</span>
            <span className="font-mono text-ink-2">nemotron-3.5-lightning</span>
          </p>
          <p className="flex justify-between">
            <span>Free requests today</span>
            <span className="font-mono text-ink-2">812 / 1000</span>
          </p>
          <p className="flex justify-between">
            <span>Policy</span>
            <span className="font-mono text-ink-2">v1.3</span>
          </p>
        </div>
      </div>
    </aside>
  );
}

function TopBar({ crumbs, children }: { crumbs: string[]; children?: React.ReactNode }) {
  return (
    <div className="flex h-14 shrink-0 items-center justify-between border-b border-line bg-white px-6">
      <p className="text-sm text-ink-3">
        {crumbs.map((crumb, index) => (
          <span key={crumb}>
            {index > 0 && <span className="px-1.5">/</span>}
            <span className={index === crumbs.length - 1 ? "font-medium text-ink" : ""}>
              {crumb}
            </span>
          </span>
        ))}
      </p>
      <div className="flex items-center gap-2">{children}</div>
    </div>
  );
}

function RunScreen() {
  const { shown, done } = useReplay();

  return (
    <>
      <TopBar crumbs={["Runs", "K-054"]}>
        {done ? (
          <span className="rounded-full bg-ok-bg px-2.5 py-1 text-xs font-medium text-ok">
            Completed in 23.8s
          </span>
        ) : (
          <span className="flex items-center gap-1.5 rounded-full bg-cream-2 px-2.5 py-1 text-xs font-medium text-ink-2">
            <AsciiSpinner className="text-forest" /> Running
          </span>
        )}
        <button className="rounded-lg border border-line bg-white px-3 py-1.5 text-sm text-ink-2 hover:text-ink">
          Run again
        </button>
      </TopBar>
      <div className="border-b border-line bg-white px-6 py-4">
        <div className="flex items-start justify-between gap-8">
          <div className="min-w-0">
            <p className="text-xs text-ink-3">Standup · Mar 10, 2026 · proposed by Aisha Rahman</p>
            <h1 className="mt-1 truncate text-xl font-medium tracking-[-0.02em]">
              File a defect: token refresh fails with 401 invalid_signature
            </h1>
          </div>
          <div className="flex shrink-0 items-center gap-6 text-xs text-ink-3">
            <div>
              <p>Golden label</p>
              <div className="mt-1">
                <VerdictPill label="T2 R2.3" />
              </div>
            </div>
            <div>
              <p>Tier</p>
              <p className="mt-1.5 font-medium text-ink">T2 · Ticket</p>
            </div>
          </div>
        </div>
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-[1fr_1fr_360px] divide-x divide-line bg-white">
        <div className="min-h-0 overflow-y-auto p-6">
          <p className="mb-4 text-xs font-medium text-ink-3">Transcript</p>
          <Transcript />
        </div>
        <div className="min-h-0 overflow-y-auto p-6">
          <p className="mb-4 text-xs font-medium text-ink-3">Agent trace</p>
          <TraceList shown={shown} done={done} />
        </div>
        <div className="min-h-0 overflow-y-auto bg-cream/40 p-4">
          <DecisionPanel done={done} />
        </div>
      </div>
    </>
  );
}

function CasesScreen({ onOpen }: { onOpen: () => void }) {
  const filters = ["All", "Golden", "T1", "T2", "Out of scope", "Not run"];

  return (
    <>
      <TopBar crumbs={["Cases"]}>
        <button className="rounded-lg border border-line bg-white px-3 py-1.5 text-sm text-ink-2 hover:text-ink">
          New case
        </button>
        <button className="rounded-lg bg-ink px-3 py-1.5 text-sm font-medium text-cream hover:bg-ink-2">
          Run selected
        </button>
      </TopBar>
      <div className="flex items-center gap-2 border-b border-line bg-white px-6 py-3">
        <div className="flex w-72 items-center gap-2 rounded-lg border border-line bg-cream/50 px-3 py-1.5 text-sm text-ink-3">
          <span aria-hidden="true">⌕</span> Search cases
        </div>
        {filters.map((filter, index) => (
          <span
            key={filter}
            className={`rounded-full border px-3 py-1 text-xs ${
              index === 1
                ? "border-ink bg-ink text-cream"
                : "border-line bg-white text-ink-2 hover:border-ink-3"
            }`}
          >
            {filter}
          </span>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto bg-white">
        <div className="grid grid-cols-[96px_140px_1fr_150px_150px] gap-4 border-b border-line bg-cream/50 px-6 py-2 text-xs font-medium text-ink-3">
          <span>Case</span>
          <span>Meeting</span>
          <span>Candidate action</span>
          <span>Golden</span>
          <span>Latest run</span>
        </div>
        {CASES.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={onOpen}
            className="grid w-full grid-cols-[96px_140px_1fr_150px_150px] items-center gap-4 border-b border-line px-6 py-3 text-left text-sm transition-colors hover:bg-cream/50"
          >
            <span className="font-mono text-[13px]">{item.id}</span>
            <span className="text-ink-2 capitalize">{item.meeting}</span>
            <span className="truncate text-ink-2">{item.action}</span>
            <span>
              <VerdictPill label={item.golden} />
            </span>
            <span>
              {item.last ? (
                <VerdictPill label={item.last} />
              ) : (
                <span className="text-xs text-ink-3">Not run yet</span>
              )}
            </span>
          </button>
        ))}
      </div>
    </>
  );
}

export function DesignPreview() {
  const [screen, setScreen] = useState<Screen>("run");

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar screen={screen} onNavigate={setScreen} />
      <main className="flex min-w-0 flex-1 flex-col">
        {screen === "run" ? <RunScreen /> : <CasesScreen onOpen={() => setScreen("run")} />}
      </main>
    </div>
  );
}
