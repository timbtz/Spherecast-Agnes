import { useState, useEffect, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { DollarSign, Clock, Star } from "lucide-react";
import { cn } from "@/lib/utils";
import { agnesApi } from "@/lib/agnesApi";
import type { ScoredSupplier, ScoringWeights, ProvenanceConfidence, UrlHealth } from "@/types/agnes";
import { ScoreBar } from "@/components/shared/ScoreBar";
import { WeightSelector } from "@/components/shared/WeightSelector";
import { LoadingState, EmptyState, ErrorState } from "@/components/shared/States";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

// ── Provenance badge ─────────────────────────────────────────────────────────

const PROVENANCE_META: Record<
  ProvenanceConfidence,
  { label: string; className: string }
> = {
  vendor_verified:   { label: "Vendor Verified",  className: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" },
  website_explicit:  { label: "Web Explicit",      className: "bg-blue-500/15 text-blue-400 border-blue-500/30" },
  directory_listing: { label: "Directory",         className: "bg-amber-500/15 text-amber-400 border-amber-500/30" },
  model_inferred:    { label: "AI Inferred",       className: "bg-orange-500/15 text-orange-400 border-orange-500/30" },
  unknown:           { label: "Unknown",           className: "bg-zinc-500/15 text-zinc-400 border-zinc-500/30" },
};

function ProvenanceBadge({ confidence }: { confidence?: ProvenanceConfidence | null }) {
  const key = confidence ?? "unknown";
  const { label, className } = PROVENANCE_META[key];
  return (
    <span
      className={cn(
        "inline-flex items-center px-1.5 py-0.5 rounded border text-[9.5px] font-medium leading-none whitespace-nowrap",
        className,
      )}
    >
      {label}
    </span>
  );
}

// ── Corroboration dots ────────────────────────────────────────────────────────

function CorroborationDots({ score }: { score: number }) {
  const clamped = Math.min(5, Math.max(0, Math.round(score)));
  return (
    <div className="flex gap-0.5" title={`Seen across ${score} source${score !== 1 ? "s" : ""}`}>
      {Array.from({ length: 5 }, (_, i) => (
        <div
          key={i}
          className={cn("size-1.5 rounded-full", i < clamped ? "bg-primary" : "bg-muted")}
        />
      ))}
    </div>
  );
}

// ── URL health dot ────────────────────────────────────────────────────────────

const URL_HEALTH_COLOR: Record<UrlHealth, string> = {
  ok:          "bg-emerald-500",
  stale:       "bg-amber-500",
  unreachable: "bg-red-500",
  not_checked: "bg-zinc-500",
};

const URL_HEALTH_LABEL: Record<UrlHealth, string> = {
  ok:          "URL reachable",
  stale:       "URL stale (>30 d)",
  unreachable: "URL unreachable",
  not_checked: "URL not checked",
};

function UrlHealthDot({ health }: { health?: UrlHealth | null }) {
  const key = health ?? "not_checked";
  return (
    <div
      className={cn("size-1.5 rounded-full shrink-0", URL_HEALTH_COLOR[key])}
      title={URL_HEALTH_LABEL[key]}
    />
  );
}

// ── Sub-score mini bar ────────────────────────────────────────────────────────

function MiniScoreBar({ label, score }: { label: string; score: number }) {
  const pct = Math.max(0, Math.min(1, score)) * 100;
  const color =
    score >= 0.75 ? "hsl(var(--status-completed))"
    : score >= 0.5 ? "hsl(var(--status-skipped))"
    : "hsl(var(--status-failed))";
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px] text-muted-foreground w-10 shrink-0">{label}</span>
      <div className="flex-1 h-1 rounded-full bg-muted overflow-hidden min-w-[40px]">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="text-[10px] font-mono text-foreground/70 w-6 text-right tabular-nums">
        {(score * 100).toFixed(0)}
      </span>
    </div>
  );
}

// ── Column grid ───────────────────────────────────────────────────────────────

const GRID = "28px 1.8fr 80px 80px 80px 80px 200px 2fr";

// ── Supplier row ──────────────────────────────────────────────────────────────

function SupplierRow({ supplier: s, rank }: { supplier: ScoredSupplier; rank: number }) {
  const lastUpdated = s.Last_Updated
    ? new Date(s.Last_Updated).toLocaleDateString("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : null;

  return (
    <Tooltip delayDuration={300}>
      <TooltipTrigger asChild>
        <div
          className="grid gap-x-3 items-start px-3 py-2.5 rounded-lg border border-border bg-background hover:bg-accent/30 transition-colors text-[13px] cursor-default"
          style={{ gridTemplateColumns: GRID }}
        >
          {/* Rank */}
          <span className="text-[11px] font-mono text-muted-foreground pt-1 text-center">#{rank}</span>

          {/* Supplier name */}
          <div className="font-medium truncate pt-0.5">{s.supplier_name}</div>

          {/* Price/kg */}
          <span className="font-mono text-[12px] pt-0.5">
            {s.Price_USD_Per_KG != null ? `$${s.Price_USD_Per_KG.toFixed(2)}` : "—"}
          </span>

          {/* Lead time */}
          <span className="font-mono text-[12px] pt-0.5">
            {s.Lead_Time_Days != null ? `${s.Lead_Time_Days}d` : "—"}
          </span>

          {/* Purity */}
          <span className="font-mono text-[12px] pt-0.5">
            {s.Purity_Pct != null ? `${s.Purity_Pct}%` : "—"}
          </span>

          {/* Country */}
          <span className="text-[12px] text-muted-foreground pt-0.5">
            {s.Country_Origin ?? "—"}
          </span>

          {/* Trust column */}
          <div className="flex flex-col gap-1 pt-0.5">
            <ProvenanceBadge confidence={s.provenance_confidence} />
            <div className="flex items-center gap-1.5">
              <CorroborationDots score={s.corroboration_score ?? 0} />
              <UrlHealthDot health={s.url_health} />
              {s.vetted && (
                <span className="text-[9.5px] text-emerald-500 font-semibold leading-none">
                  ✓ Verified
                </span>
              )}
            </div>
          </div>

          {/* Weighted Score + sub-score breakdown */}
          <div className="flex flex-col gap-1 min-w-0">
            <ScoreBar score={s.weighted_score} />
            <div className="flex flex-col gap-0.5 pt-0.5">
              <MiniScoreBar label="Price"   score={s.price_score} />
              <MiniScoreBar label="Lead"    score={s.lead_time_score} />
              <MiniScoreBar label="Quality" score={s.quality_score} />
            </div>
          </div>
        </div>
      </TooltipTrigger>

      <TooltipContent side="left" className="w-64 p-3 space-y-3 text-[12px]" sideOffset={8}>
        {/* Sub-score breakdown */}
        <div className="space-y-1.5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">
            Score breakdown
          </p>
          <MiniScoreBar label="Price"   score={s.price_score} />
          <MiniScoreBar label="Lead"    score={s.lead_time_score} />
          <MiniScoreBar label="Quality" score={s.quality_score} />
          <p className="text-[10.5px] text-muted-foreground leading-snug pt-0.5">
            Quality composed from purity %, grade verification status, and data confidence.
          </p>
        </div>

        {/* Provenance */}
        <div className="border-t border-border pt-2 space-y-0.5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">
            Provenance
          </p>
          <p className="text-foreground/80">
            Source:{" "}
            <span className="font-mono text-[11px]">
              {s.url_archetype ?? s.Price_Source ?? "unknown"}
            </span>
          </p>
          {lastUpdated && (
            <p className="text-muted-foreground">Last updated: {lastUpdated}</p>
          )}
          <p className="text-muted-foreground">
            Corroboration: {s.corroboration_score ?? 0} source
            {(s.corroboration_score ?? 0) !== 1 ? "s" : ""}
          </p>
        </div>

        {/* GLEIF entity verification */}
        {(s.LEI || s.Legal_Name) && (
          <div className="border-t border-border pt-2 space-y-0.5">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">
              Entity (GLEIF)
            </p>
            {s.Legal_Name && (
              <p className="text-foreground/80 truncate" title={s.Legal_Name}>
                {s.Legal_Name}
              </p>
            )}
            {s.LEI && (
              <p className="font-mono text-[10.5px] text-muted-foreground">
                LEI: {s.LEI}
              </p>
            )}
          </div>
        )}
      </TooltipContent>
    </Tooltip>
  );
}

// ── Main view ─────────────────────────────────────────────────────────────────

export function SuppliersView() {
  const qc = useQueryClient();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [pendingWeights, setPendingWeights] = useState<ScoringWeights>({
    price: 3,
    lead_time: 3,
    quality: 3,
  });

  const { data: ingredientsData } = useQuery({
    queryKey: ["ingredients"],
    queryFn: () => agnesApi.ingredients(),
  });

  const { data: savedWeights } = useQuery({
    queryKey: ["scoring-weights"],
    queryFn: () => agnesApi.scoringWeights(),
  });

  useEffect(() => {
    if (savedWeights) setPendingWeights(savedWeights);
  }, [savedWeights]);

  const { data: suppliersData, isLoading, error } = useQuery({
    queryKey: ["scored-suppliers", selectedId],
    queryFn: () => agnesApi.scoredSuppliers(selectedId!),
    enabled: !!selectedId,
  });

  const saveMutation = useMutation({
    mutationFn: (w: ScoringWeights) => agnesApi.saveScoringWeights(w),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scoring-weights"] });
      qc.invalidateQueries({ queryKey: ["scored-suppliers"] });
    },
  });

  const handleApply = () => saveMutation.mutate(pendingWeights);
  const ingredientList = ingredientsData ?? [];

  // Client-side re-score and sort based on saved weights (works in demo mode too)
  const rankedSuppliers = useMemo(() => {
    const suppliers = suppliersData?.suppliers;
    if (!suppliers?.length) return [];
    const w = savedWeights ?? { price: 1, lead_time: 1, quality: 1 };
    const total = (w.price + w.lead_time + w.quality) || 1;
    return [...suppliers]
      .map((s) => ({
        ...s,
        weighted_score:
          (s.price_score * w.price + s.lead_time_score * w.lead_time + s.quality_score * w.quality) / total,
      }))
      .sort((a, b) => b.weighted_score - a.weighted_score);
  }, [suppliersData, savedWeights]);

  return (
    <div className="flex gap-6 p-5 h-full">
      {/* Left: Config panel */}
      <div className="w-64 shrink-0 flex flex-col gap-5">
        <div>
          <p className="text-[12px] font-semibold text-muted-foreground uppercase tracking-wide mb-2">
            Ingredient
          </p>
          <Select onValueChange={(v) => setSelectedId(Number(v))}>
            <SelectTrigger className="w-full text-[13px]">
              <SelectValue placeholder="Select ingredient…" />
            </SelectTrigger>
            <SelectContent>
              {ingredientList.map((ing: { id: string | number; display_name: string }) => (
                <SelectItem key={ing.id} value={String(ing.id)}>
                  {ing.display_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="border-t border-border pt-4">
          <p className="text-[12px] font-semibold text-muted-foreground uppercase tracking-wide mb-3">
            Scoring Weights
          </p>
          <div className="flex flex-col gap-4">
            <WeightSelector
              label="Price"
              description="$/kg importance"
              value={pendingWeights.price}
              onChange={(v) => setPendingWeights((w) => ({ ...w, price: v }))}
              icon={<DollarSign size={13} />}
            />
            <WeightSelector
              label="Lead Time"
              description="Days to delivery"
              value={pendingWeights.lead_time}
              onChange={(v) => setPendingWeights((w) => ({ ...w, lead_time: v }))}
              icon={<Clock size={13} />}
            />
            <WeightSelector
              label="Quality"
              description="Purity, grade, confidence"
              value={pendingWeights.quality}
              onChange={(v) => setPendingWeights((w) => ({ ...w, quality: v }))}
              icon={<Star size={13} />}
            />
          </div>
          <Button
            size="sm"
            className="w-full mt-4 text-[12px]"
            onClick={handleApply}
            disabled={saveMutation.isPending}
          >
            {saveMutation.isPending ? "Saving…" : "Apply Weights"}
          </Button>
        </div>
      </div>

      {/* Right: Supplier table */}
      <div className="flex-1 min-w-0">
        {!selectedId ? (
          <EmptyState
            title="No ingredient selected"
            body="Choose an ingredient from the left panel to see ranked suppliers."
          />
        ) : isLoading ? (
          <LoadingState label="Loading suppliers…" />
        ) : error ? (
          <ErrorState message="Failed to load supplier data." />
        ) : !rankedSuppliers.length ? (
          <EmptyState
            title="No supplier data"
            body="No commercial data yet for this ingredient. Run the Molport enrichment to populate."
          />
        ) : (
          <div className="flex flex-col gap-2">
            <div
              className="grid gap-x-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wide px-3 pb-1"
              style={{ gridTemplateColumns: GRID }}
            >
              <span>#</span>
              <span>Supplier</span>
              <span>Price/kg</span>
              <span>Lead Time</span>
              <span>Purity</span>
              <span>Country</span>
              <span>Trust</span>
              <span>Weighted Score</span>
            </div>
            {rankedSuppliers.map((sup, i) => (
              <SupplierRow key={sup.SupplierId} supplier={sup} rank={i + 1} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
