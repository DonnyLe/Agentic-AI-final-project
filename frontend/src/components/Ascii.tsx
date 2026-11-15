import { useEffect, useState } from "react";

export type GraphNode =
  | "intake"
  | "supervisor"
  | "evidence"
  | "adjudicator"
  | "guards"
  | "decision";

interface AsciiGraphProps {
  active: GraphNode | null;
  visited: ReadonlySet<GraphNode>;
}

/** The agent graph in ASCII. The active node is highlighted; visited nodes are bright. */
export function AsciiGraph({ active, visited }: AsciiGraphProps) {
  const node = (name: GraphNode, label: string = name) => {
    const tone =
      name === active
        ? "bg-mint text-forest-2"
        : visited.has(name)
          ? "text-cream"
          : "text-cream/45";

    return <span className={`transition-colors duration-300 ${tone}`}>[{label}]</span>;
  };

  return (
    <pre className="font-mono text-[13px] leading-[1.7] text-cream/45 select-none">
      {node("intake")} ──▶ {node("supervisor")} ──▶ {node("evidence")}
      {"\n"}
      {"                │    ▲            │\n"}
      {"                │    └────────────┘\n"}
      {"                ▼\n"}
      {"          "}
      {node("adjudicator")} ──▶ {node("guards")} ──▶ {node("decision", "● decision")}
    </pre>
  );
}

const SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

export function AsciiSpinner({ className = "" }: { className?: string }) {
  const [frame, setFrame] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => setFrame((f) => (f + 1) % SPINNER_FRAMES.length), 80);

    return () => window.clearInterval(timer);
  }, []);

  return (
    <span aria-hidden="true" className={`font-mono ${className}`}>
      {SPINNER_FRAMES[frame]}
    </span>
  );
}
