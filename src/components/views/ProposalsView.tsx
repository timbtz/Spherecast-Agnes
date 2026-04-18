import { useQuery } from "@tanstack/react-query";
import { FileText, ShieldCheck, ShieldAlert, Volume2, Users } from "lucide-react";
import { agnesApi } from "@/lib/agnesApi";
import { useAgnes } from "@/hooks/useAgnes";
import { isElevenLabsConfigured } from "@/lib/elevenlabs";
import { GradePill } from "@/components/shared/GradePill";
import { ScoreBar } from "@/components/shared/ScoreBar";
import { EmptyState, ErrorState, LoadingState } from "@/components/shared/States";

export function ProposalsView() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["proposals"],
    queryFn: () => agnesApi.proposals(),
  });
  const { speak } = useAgnes();
  const ttsOk = isElevenLabsConfigured();

  if (isLoading) return <LoadingState label="Loading proposals" />;
  if (error) return <ErrorState message="Could not load proposals." onRetry={() => refetch()} />;

  if (!data?.length) {
    return (
      <EmptyState
        icon={<FileText className="size-4" />}
        title="No proposals yet"
        body="Agnes generates these by running the proactive_consolidation or supplier_fallout pipelines."
      />
    );
  }

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
      {data.map((p) => (
        <article
          key={p.id}
          className="rounded-xl border border-border bg-background p-5 hover:shadow-sm transition-shadow flex flex-col"
        >
          <header className="flex items-start justify-between gap-3 mb-3 pb-3 border-b border-border">
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="text-[15px] font-semibold text-foreground">{p.ingredient_name}</h3>
                <GradePill grade={p.grade} />
              </div>
              <p className="text-[11px] text-muted-foreground mt-1 font-mono">
                {new Date(p.created_at).toLocaleString()}
              </p>
            </div>
            <div className="shrink-0 text-right">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Score</p>
              <p className="text-[18px] font-mono tabular-nums font-semibold text-foreground leading-none mt-0.5">
                {(p.consolidation_score * 100).toFixed(0)}
              </p>
            </div>
          </header>

          <p className="text-[13px] text-foreground/90 leading-[1.65] whitespace-pre-wrap flex-1">
            {p.proposal_text}
          </p>

          <footer className="mt-4 pt-3 border-t border-border flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 text-[11.5px] text-muted-foreground">
              <span className="inline-flex items-center gap-1">
                <Users className="size-3" /> {p.company_count} suppliers
              </span>
              {p.compliance_feasible ? (
                <span className="inline-flex items-center gap-1 text-status-completed">
                  <ShieldCheck className="size-3" /> Compliance feasible
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-status-skipped">
                  <ShieldAlert className="size-3" /> Review required
                </span>
              )}
            </div>
            {ttsOk && (
              <button
                onClick={() => void speak(p.proposal_text)}
                className="inline-flex items-center gap-1.5 text-[12px] font-medium text-primary hover:underline"
              >
                <Volume2 className="size-3.5" /> Read aloud
              </button>
            )}
          </footer>
          <ScoreBar score={p.consolidation_score} className="mt-3" showValue={false} />
        </article>
      ))}
    </div>
  );
}
