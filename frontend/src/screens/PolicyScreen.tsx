import type { PolicyView } from "@/api.ts";
import { Notice, TopBar } from "@/components/Shell.tsx";

export function PolicyScreen({ policy, error }: { policy: PolicyView | null; error: string }) {
  const tiers = [...new Set((policy?.rules ?? []).map((rule) => rule.tier))];

  return (
    <>
      <TopBar crumbs={["Policy", policy ? `v${policy.version}` : ""]} />
      <div className="min-h-0 flex-1 overflow-y-auto bg-white">
        <div className="mx-auto max-w-3xl space-y-8 px-6 py-8">
          {error && <Notice tone="error">{error}</Notice>}
          {tiers.map((tier) => (
            <section key={tier}>
              <h2 className="text-xs font-medium text-ink-3">{tier}</h2>
              <div className="mt-3 space-y-4">
                {policy?.rules
                  .filter((rule) => rule.tier === tier)
                  .map((rule) => (
                    <div key={rule.id} id={rule.id} className="scroll-mt-6">
                      <p className="text-sm font-medium">
                        <span className="mr-2 font-mono text-[12px] text-ink-3">{rule.id}</span>
                        {rule.name}
                      </p>
                      <p className="mt-1 text-[13px] leading-relaxed text-ink-2">{rule.text}</p>
                    </div>
                  ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    </>
  );
}
