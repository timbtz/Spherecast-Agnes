import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { DollarSign, Clock, Star } from "lucide-react";
import { agnesApi } from "@/lib/agnesApi";
import type { ScoringWeights, ScoredSupplier } from "@/types/agnes";
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
        ) : !suppliersData?.suppliers?.length ? (
          <EmptyState
            title="No supplier data"
            body="No commercial data yet for this ingredient. Run the Molport enrichment to populate."
          />
        ) : (
          <div className="flex flex-col gap-2">
            <div
              className="grid gap-x-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wide px-3 pb-1"
              style={{ gridTemplateColumns: "1.8fr 80px 80px 80px 80px 2fr" }}
            >
              <span>Supplier</span>
              <span>Price/kg</span>
              <span>Lead Time</span>
              <span>Purity</span>
              <span>Country</span>
              <span>Weighted Score</span>
            </div>
            {suppliersData.suppliers.map((sup) => (
              <SupplierRow key={sup.SupplierId} supplier={sup} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function SupplierRow({ supplier: s }: { supplier: ScoredSupplier }) {
  return (
    <div
      className="grid gap-x-3 items-center px-3 py-2.5 rounded-lg border border-border bg-background hover:bg-accent/30 transition-colors text-[13px]"
      style={{ gridTemplateColumns: "1.8fr 80px 80px 80px 80px 2fr" }}
    >
      <span className="font-medium truncate">{s.supplier_name}</span>
      <span className="font-mono text-[12px]">
        {s.Price_USD_Per_KG != null ? `$${s.Price_USD_Per_KG.toFixed(2)}` : "—"}
      </span>
      <span className="font-mono text-[12px]">
        {s.Lead_Time_Days != null ? `${s.Lead_Time_Days}d` : "—"}
      </span>
      <span className="font-mono text-[12px]">
        {s.Purity_Pct != null ? `${s.Purity_Pct}%` : "—"}
      </span>
      <span className="text-[12px] text-muted-foreground">{s.Country_Origin ?? "—"}</span>
      <ScoreBar score={s.weighted_score} />
    </div>
  );
}
