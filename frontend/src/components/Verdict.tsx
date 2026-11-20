const TONES = new Map([
  ["none", "bg-ok-bg text-ok"],
  ["unsupported", "bg-out-bg text-out"],
  ["needs_review", "bg-hold-bg text-hold"],
]);

const VIOLATION_TONE = "bg-bad-bg text-bad";

function describe(label: string) {
  if (label === "none") {
    return "No violation";
  }

  if (label === "unsupported") {
    return "Unsupported";
  }

  if (label === "needs_review") {
    return "Needs review";
  }

  return label.replace(" ", " · ");
}

/** A golden-format label (`none`, `T2 R2.3`, `unsupported`, `needs_review`) as a pill. */
export function VerdictPill({ label, size = "sm" }: { label: string; size?: "sm" | "lg" }) {
  const tone = TONES.get(label) ?? VIOLATION_TONE;
  const sizing = size === "lg" ? "gap-2 px-3 py-1.5 text-sm" : "gap-1.5 px-2.5 py-1 text-xs";

  return (
    <span className={`inline-flex items-center rounded-full font-medium ${sizing} ${tone}`}>
      <span className="size-1.5 rounded-full bg-current" />
      {describe(label)}
    </span>
  );
}
