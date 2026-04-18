import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Search, X, FlaskConical } from "lucide-react";
import { agnesApi } from "@/lib/agnesApi";
import { GradePill } from "@/components/shared/GradePill";
import { EmptyState, ErrorState, LoadingState } from "@/components/shared/States";
import type { Grade, Ingredient } from "@/types/agnes";
import { cn } from "@/lib/utils";

const GRADES: Grade[] = ["supplement", "food", "excipient", "sweetener", "flavor"];

export function IngredientsView() {
  const [grade, setGrade] = useState<Grade | "">("");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Ingredient | null>(null);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["ingredients", grade],
    queryFn: () => agnesApi.ingredients(grade || undefined),
  });

  const filtered = useMemo(() => {
    if (!data) return [];
    const ql = q.toLowerCase().trim();
    return ql ? data.filter((i) => i.display_name.toLowerCase().includes(ql) || (i.cas ?? "").includes(ql)) : data;
  }, [data, q]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 items-center">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="size-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search ingredients or CAS…"
            className="w-full h-9 pl-9 pr-3 rounded-md border border-border bg-background text-[13px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/40"
          />
        </div>
        <select
          value={grade}
          onChange={(e) => setGrade(e.target.value as Grade | "")}
          className="h-9 px-3 rounded-md border border-border bg-background text-[13px] focus:outline-none focus:ring-2 focus:ring-primary/30"
        >
          <option value="">All grades</option>
          {GRADES.map((g) => (
            <option key={g} value={g}>{g}</option>
          ))}
        </select>
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-[120px] rounded-lg border border-border bg-surface-subtle animate-pulse" />
          ))}
        </div>
      )}
      {error && <ErrorState message="Could not load ingredients." onRetry={() => refetch()} />}

      {!isLoading && filtered.length === 0 && (
        <EmptyState
          icon={<FlaskConical className="size-4" />}
          title="No ingredients match"
          body="Try adjusting filters or clearing the search."
        />
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {filtered.map((i) => (
          <button
            key={i.id}
            onClick={() => setSelected(i)}
            className="text-left rounded-lg border border-border bg-background p-3.5 hover:border-border-strong hover:shadow-sm transition-all"
          >
            <div className="flex items-start justify-between gap-2 mb-2">
              <p className="text-[13.5px] font-medium text-foreground leading-snug">{i.display_name}</p>
              <GradePill grade={i.grade} />
            </div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11.5px]">
              <Field label="UNII" value={i.unii} mono />
              <Field label="CAS" value={i.cas} mono />
              <Field label="PubChem" value={i.pubchem_cid} mono />
              <Field label="Subs" value={String(i.substitution_edges ?? 0)} mono />
            </div>
            {i.smiles && (
              <p className="mt-2 font-mono text-[10.5px] text-muted-foreground truncate" title={i.smiles}>
                {i.smiles}
              </p>
            )}
          </button>
        ))}
      </div>

      {selected && <DetailDrawer ingredient={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function Field({ label, value, mono }: { label: string; value?: string | null; mono?: boolean }) {
  return (
    <div className="flex items-baseline gap-1.5 min-w-0">
      <span className="text-muted-foreground/80 text-[10.5px] uppercase tracking-wider shrink-0">{label}</span>
      <span className={cn("truncate text-foreground/85", mono && "font-mono text-[11px]")}>{value || "—"}</span>
    </div>
  );
}

function DetailDrawer({ ingredient, onClose }: { ingredient: Ingredient; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-30 flex" onClick={onClose}>
      <div className="flex-1 bg-foreground/10 backdrop-blur-[2px]" />
      <div
        className="w-[400px] bg-background border-l border-border shadow-lg p-5 overflow-auto animate-slide-in-right"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4">
          <div>
            <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">Ingredient detail</p>
            <h2 className="text-[18px] font-semibold text-foreground mt-0.5">{ingredient.display_name}</h2>
          </div>
          <button onClick={onClose} className="size-7 rounded-md hover:bg-secondary flex items-center justify-center">
            <X className="size-4 text-muted-foreground" />
          </button>
        </div>
        <GradePill grade={ingredient.grade} className="mb-4" />
        <dl className="space-y-3 text-[13px]">
          <Row label="UNII" value={ingredient.unii} />
          <Row label="CAS" value={ingredient.cas} />
          <Row label="PubChem CID" value={ingredient.pubchem_cid} />
          <Row label="Substitution edges" value={String(ingredient.substitution_edges ?? 0)} />
          <div>
            <dt className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-1">SMILES</dt>
            <dd className="font-mono text-[11.5px] text-foreground bg-surface-subtle border border-border rounded-md p-2 break-all">
              {ingredient.smiles || "—"}
            </dd>
          </div>
        </dl>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="flex justify-between items-baseline border-b border-border pb-2">
      <dt className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">{label}</dt>
      <dd className="font-mono text-foreground/90">{value || "—"}</dd>
    </div>
  );
}
