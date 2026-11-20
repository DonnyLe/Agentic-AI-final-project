import { type FormEvent, type ReactNode, useState } from "react";

import { saveToken } from "@/api.ts";
import { AsciiSpinner, type GraphNode } from "@/components/Ascii.tsx";
import { DitherField } from "@/components/DitherField.tsx";
import { href, type Route } from "@/route.ts";

export const AGENT_STEPS: GraphNode[] = [
  "intake",
  "supervisor",
  "evidence",
  "adjudicator",
  "guards",
];

/** What the open run is doing, shown in the sidebar's agent panel. */
export interface AgentActivity {
  running: boolean;
  visited: ReadonlySet<string>;
  active: string | null;
}

export const IDLE: AgentActivity = { running: false, visited: new Set(), active: null };

export function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="relative size-7 overflow-hidden rounded-lg bg-forest">
        <DitherField intensity={0.9} cell={2} className="absolute inset-0 size-full text-mint" />
      </div>
      <span className="text-[17px] font-semibold tracking-tight">Kangaroo</span>
    </div>
  );
}

interface NavItem {
  label: string;
  target: Route;
  matches: Route["screen"][];
  count?: number | undefined;
}

interface SidebarProps {
  route: Route;
  caseCount: number | undefined;
  runCount: number | undefined;
  activity: AgentActivity;
  model: string;
  policyVersion: string;
}

export function Sidebar(props: SidebarProps) {
  const { route, activity } = props;

  const nav: NavItem[] = [
    {
      label: "Cases",
      target: { screen: "cases" },
      matches: ["cases", "case"],
      count: props.caseCount,
    },
    { label: "Runs", target: { screen: "runs" }, matches: ["runs", "run"], count: props.runCount },
    { label: "Policy", target: { screen: "policy" }, matches: ["policy"] },
  ];

  return (
    <aside className="flex h-screen w-[248px] shrink-0 flex-col border-r border-line bg-cream px-3 py-4">
      <a href={href({ screen: "cases" })} className="px-2">
        <Logo />
      </a>
      <nav className="mt-7 space-y-0.5">
        {nav.map((item) => {
          const current = item.matches.includes(route.screen);

          return (
            <a
              key={item.label}
              href={href(item.target)}
              className={`flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-sm transition-colors ${
                current
                  ? "bg-white font-medium text-ink shadow-card"
                  : "text-ink-2 hover:bg-cream-2"
              }`}
            >
              {item.label}
              {item.count !== undefined && <span className="text-xs text-ink-3">{item.count}</span>}
            </a>
          );
        })}
      </nav>
      <div className="mt-auto space-y-3">
        <div className="relative overflow-hidden rounded-xl bg-forest p-3 text-cream">
          <DitherField
            intensity={activity.running ? 0.8 : 0.35}
            cell={3}
            fadeFrom={0.2}
            className="absolute inset-0 size-full text-mint/40"
          />
          <div className="relative">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium">Agents</span>
              <span className="flex items-center gap-1 text-mint">
                {activity.running ? (
                  <>
                    <AsciiSpinner /> Running
                  </>
                ) : (
                  "Idle"
                )}
              </span>
            </div>
            <ol className="mt-3 space-y-1 rounded-lg bg-forest-2/45 px-2.5 py-2 font-mono text-[11px]">
              {AGENT_STEPS.map((step) => {
                const reached = activity.visited.has(step);
                const current = activity.running && step === activity.active;
                const tone = current ? "text-mint" : reached ? "text-cream" : "text-cream/40";
                const mark = current ? "●" : reached ? "✓" : "○";

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
          <p className="flex justify-between gap-2">
            <span>Model</span>
            <span className="truncate font-mono text-ink-2" title={props.model}>
              {props.model}
            </span>
          </p>
          <p className="flex justify-between">
            <span>Policy</span>
            <span className="font-mono text-ink-2">{props.policyVersion}</span>
          </p>
        </div>
      </div>
    </aside>
  );
}

export function TopBar({ crumbs, children }: { crumbs: string[]; children?: ReactNode }) {
  return (
    <div className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-line bg-white px-6">
      <p className="truncate text-sm text-ink-3">
        {crumbs.map((crumb, index) => (
          <span key={crumb}>
            {index > 0 && <span className="px-1.5">/</span>}
            <span className={index === crumbs.length - 1 ? "font-medium text-ink" : ""}>
              {crumb}
            </span>
          </span>
        ))}
      </p>
      <div className="flex shrink-0 items-center gap-2">{children}</div>
    </div>
  );
}

export function Notice({
  tone = "info",
  children,
}: {
  tone?: "info" | "error";
  children: ReactNode;
}) {
  const colors =
    tone === "error" ? "border-bad/30 bg-bad-bg text-bad" : "border-line bg-cream text-ink-2";

  return <div className={`rounded-lg border px-3 py-2 text-[13px] ${colors}`}>{children}</div>;
}

/** Shown when the server has KANGAROO_ACCESS_TOKEN set and we don't have it yet. */
export function TokenGate() {
  const [token, setToken] = useState("");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    saveToken(token.trim());
    window.location.reload();
  };

  return (
    <div className="grid min-h-screen place-items-center bg-cream px-4">
      <form
        onSubmit={submit}
        className="w-full max-w-sm rounded-xl border border-line bg-white p-6 shadow-card"
      >
        <Logo />
        <p className="mt-5 text-sm text-ink-2">This deployment needs an access token.</p>
        <input
          type="password"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          placeholder="Access token"
          className="mt-3 w-full rounded-lg border border-line bg-cream/50 px-3 py-2 text-sm outline-none focus:border-ink-3"
        />
        <button
          type="submit"
          disabled={!token.trim()}
          className="mt-3 w-full rounded-lg bg-ink py-2 text-sm font-medium text-cream hover:bg-ink-2 disabled:opacity-40"
        >
          Continue
        </button>
      </form>
    </div>
  );
}
