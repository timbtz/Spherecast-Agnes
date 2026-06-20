import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileText, ShieldCheck, ShieldAlert, Volume2, Users, ChevronDown, ChevronUp, BookOpen, XCircle } from "lucide-react";
import { agnesApi } from "@/lib/agnesApi";
import type { Proposal, Citation, Refusal } from "@/types/agnes";
import { useAgnes } from "@/hooks/useAgnes";
import { isElevenLabsConfigured } from "@/lib/elevenlabs";
import { GradePill } from "@/components/shared/GradePill";
import { ScoreBar } from "@/components/shared/ScoreBar";
import { EmptyState, ErrorState, LoadingState } from "@/components/shared/States";
import { cn } from "@/lib/utils";

const SOURCE_COLORS: Record<string, string> = {
  fda_iid: "text-blue-400",
  pubchem: "text-emerald-400",
  dsld: "text-violet-400",
  supplier: "text-amber-400",
  openfda: "text-red-400",
  compliance: "text-cyan-400",
};

function CitationRow({ cit }: { cit: Citation }) {
  return (
    <div className="flex items-start gap-2 text-[11px] py-1 border-b border-border last:border-0">
      <span className={cn("font-mono font-semibold uppercase shrink-0", SOURCE_COLORS[cit.source_type] ?? "text-muted-foreground")}>
        {cit.source_type.replace("_", " ")}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-foreground/90">{cit.claim_text}</p>
        {cit.source_snippet && (
          <p className="text-muted-foreground mt-0.5 line-clamp-2">{cit.source_snippet}</p>
        )}
      </div>
      {cit.confidence != null && (
        <span className="shrink-0 font-mono text-muted-foreground">{(cit.confidence * 100).toFixed(0)}%</span>
      )}
    </div>
  );
}

function ProposalCard({ p }: { p: Proposal }) {
  const [showCitations, setShowCitations] = useState(false);
  const { speak } = useAgnes();
  const ttsOk = isElevenLabsConfigured();

  const { data: citData } = useQuery({
    queryKey: ["citations", p.id],
    queryFn: () => agnesApi.proposalCitations(p.id),
    enabled: showCitations,
  });

  return (
    <article className="rounded-xl border border-border bg-background p-5 hover:shadow-sm transition-shadow flex flex-col">
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
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowCitations(v => !v)}
            className="inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"
          >
            <BookOpen className="size-3" />
            Evidence
            {showCitations ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
          </button>
          {ttsOk && (
            <button
              onClick={() => void speak(p.proposal_text)}
              className="inline-flex items-center gap-1.5 text-[12px] font-medium text-primary hover:underline"
            >
              <Volume2 className="size-3.5" /> Read aloud
            </button>
          )}
        </div>
      </footer>

      {showCitations && (
        <div className="mt-3 pt-3 border-t border-border">
          {citData?.citations?.length ? (
            <div className="space-y-0">
              {citData.citations.map(cit => <CitationRow key={cit.id} cit={cit} />)}
            </div>
          ) : (
            <p className="text-[11px] text-muted-foreground">No citations available for this proposal. Re-run proposal generator to extract evidence.</p>
          )}
        </div>
      )}

      <ScoreBar score={p.consolidation_score} className="mt-3" showValue={false} />
    </article>
  );
}

function RefusalsPanel() {
  const [open, setOpen] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["refusals"],
    queryFn: () => agnesApi.refusals(),
    enabled: open,
  });

  return (
    <div className="mt-8 rounded-xl border border-border bg-background">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-5 py-3 text-left hover:bg-surface-subtle/40 transition-colors rounded-xl"
      >
        <div className="flex items-center gap-2">
          <XCircle className="size-4 text-red-400" strokeWidth={2} />
          <span className="text-[14px] font-semibold text-foreground">Refused &amp; Deferred</span>
          <span className="text-[11px] text-muted-foreground">Substitutions Agnes cannot confidently recommend</span>
        </div>
        {open ? <ChevronUp className="size-4 text-muted-foreground" /> : <ChevronDown className="size-4 text-muted-foreground" />}
      </button>

      {open && (
        <div className="px-5 pb-5 space-y-3 border-t border-border pt-4">
          {isLoading && <p className="text-[12px] text-muted-foreground">Loading refusals…</p>}
          {(data?.refusals ?? []).map((r: Refusal) => (
            <div key={r.id} className="rounded-lg border border-red-500/20 bg-red-500/5 p-3 space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-[13px] font-semibold">{r.ingredient_name}</span>
                <span className={cn(
                  "text-[10px] uppercase px-1.5 py-0.5 rounded font-semibold",
                  r.decision.startsWith("defer") ? "bg-amber-500/10 text-amber-400 border border-amber-500/20" : "bg-red-500/10 text-red-400 border border-red-500/20"
                )}>
                  {r.decision.startsWith("defer") ? "Deferred" : "Refused"}
                </span>
                <span className="text-[10px] font-mono text-muted-foreground ml-auto">{(r.confidence * 100).toFixed(0)}% confidence</span>
              </div>
              <p className="text-[12px] text-foreground/80">{r.justification}</p>
              {r.unblock_hint && (
                <p className="text-[11px] text-muted-foreground border-t border-red-500/10 pt-1 mt-1">
                  <span className="font-medium text-foreground/70">To unblock: </span>{r.unblock_hint}
                </p>
              )}
            </div>
          ))}
          {data?.refusals?.length === 0 && !isLoading && (
            <p className="text-[12px] text-muted-foreground">No refusals recorded yet. Run compliance pipelines to populate.</p>
          )}
        </div>
      )}
    </div>
  );
}

export function ProposalsView() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["proposals"],
    queryFn: () => agnesApi.proposals(),
  });

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
    <div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {data.map((p) => <ProposalCard key={p.id} p={p} />)}
      </div>
      <RefusalsPanel />
    </div>
  );
}
