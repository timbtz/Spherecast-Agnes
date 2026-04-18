import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ChevronDown, ChevronRight, ShieldCheck, ShieldAlert, Volume2, TrendingUp } from "lucide-react";
import { agnesApi } from "@/lib/agnesApi";
import { useAgnes } from "@/hooks/useAgnes";
import { isElevenLabsConfigured } from "@/lib/elevenlabs";
import { GradePill } from "@/components/shared/GradePill";
import { ScoreBar } from "@/components/shared/ScoreBar";
import { EmptyState, ErrorState, LoadingState } from "@/components/shared/States";
import { cn } from "@/lib/utils";

export function OpportunitiesView() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["opportunities"],
    queryFn: () => agnesApi.opportunities(),
  });
  const [expanded, setExpanded] = useState<string | null>(null);
  const { speak } = useAgnes();
  const ttsOk = isElevenLabsConfigured();

  if (isLoading) return <LoadingState label="Loading opportunities" />;
  if (error) return <ErrorState message="Could not load opportunities." onRetry={() => refetch()} />;
  if (!data?.length) {
    return (
      <EmptyState
        icon={<TrendingUp className="size-4" />}
        title="No opportunities yet"
        body="Agnes hasn't scored any consolidation opportunities yet. Run the proactive_consolidation pipeline to get started."
      />
    );
  }

  return (
    <div className="rounded-xl border border-border overflow-hidden bg-background">
      <div className="grid grid-cols-[1.6fr_90px_120px_2fr_140px_40px] gap-3 px-4 py-2.5 border-b border-border bg-surface-subtle/60 text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">
        <div>Ingredient</div>
        <div>Grade</div>
        <div>Suppliers</div>
        <div>Consolidation score</div>
        <div>Compliance</div>
        <div></div>
      </div>
      {data.map((opp) => {
        const isOpen = expanded === opp.id;
        return (
          <div key={opp.id} className={cn("border-b border-border last:border-b-0", isOpen && "bg-surface-subtle/40")}>
            <button
              onClick={() => setExpanded(isOpen ? null : opp.id)}
              className="w-full grid grid-cols-[1.6fr_90px_120px_2fr_140px_40px] gap-3 px-4 py-3 items-center hover:bg-surface-hover/60 transition-colors text-left"
            >
              <div className="text-[13px] font-medium text-foreground">{opp.ingredient_name}</div>
              <div><GradePill grade={opp.grade} /></div>
              <div className="text-[12.5px] tabular-nums text-foreground/80 font-mono">{opp.company_count}</div>
              <ScoreBar score={opp.consolidation_score} />
              <div>
                {opp.compliance_feasible ? (
                  <span className="pill bg-status-completed/10 text-status-completed border border-status-completed/20">
                    <ShieldCheck className="size-3" /> Feasible
                  </span>
                ) : (
                  <span className="pill bg-status-skipped/10 text-status-skipped border border-status-skipped/30">
                    <ShieldAlert className="size-3" /> Review
                  </span>
                )}
              </div>
              <div className="flex justify-end text-muted-foreground">
                {isOpen ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
              </div>
            </button>
            {isOpen && (
              <div className="px-4 pb-4 animate-fade-in">
                {opp.proposal_text ? (
                  <div className="rounded-lg border border-border bg-background p-4">
                    <p className="text-[13px] text-foreground whitespace-pre-wrap leading-relaxed">{opp.proposal_text}</p>
                    {ttsOk && (
                      <button
                        onClick={() => void speak(opp.proposal_text!)}
                        className="mt-3 inline-flex items-center gap-1.5 text-[12px] font-medium text-primary hover:underline"
                      >
                        <Volume2 className="size-3.5" /> Voice summary
                      </button>
                    )}
                  </div>
                ) : (
                  <p className="text-[12.5px] text-muted-foreground italic">
                    No proposal generated yet for this opportunity. Trigger the proactive_consolidation pipeline to generate one.
                  </p>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
