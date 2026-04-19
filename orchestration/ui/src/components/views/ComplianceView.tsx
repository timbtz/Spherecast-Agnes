import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { AlertTriangle, ShieldCheck, Search } from "lucide-react";
import { agnesApi } from "@/lib/agnesApi";
import { ErrorState, LoadingState } from "@/components/shared/States";
import { cn } from "@/lib/utils";

export function ComplianceView() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["compliance"],
    queryFn: () => agnesApi.compliance(),
  });

  const [search, setSearch] = useState("");
  const [filterMode, setFilterMode] = useState<"all" | "certified" | "implied">("all");

  const certTypes = useMemo(() => {
    if (!data) return [];
    const set = new Set<string>();
    data.forEach((p) => Object.keys(p.certifications).forEach((c) => set.add(c)));
    return Array.from(set);
  }, [data]);

  const filtered = useMemo(() => {
    if (!data) return [];
    return data.filter((p) => {
      const matchesSearch =
        !search ||
        p.product_name.toLowerCase().includes(search.toLowerCase()) ||
        p.company.toLowerCase().includes(search.toLowerCase());
      if (!matchesSearch) return false;
      if (filterMode === "certified") {
        return Object.values(p.certifications).some((s) => s === "certified");
      }
      if (filterMode === "implied") {
        return Object.values(p.certifications).some((s) => s === "implied" || s === "derived");
      }
      return true;
    });
  }, [data, search, filterMode]);

  const grouped = useMemo(() => {
    const map = new Map<string, typeof filtered>();
    filtered.forEach((p) => {
      const arr = map.get(p.company) ?? [];
      arr.push(p);
      map.set(p.company, arr);
    });
    return Array.from(map.entries());
  }, [filtered]);

  const certifiedCount = useMemo(
    () => data?.filter((p) => Object.values(p.certifications).some((s) => s === "certified")).length ?? 0,
    [data],
  );

  if (isLoading) return <LoadingState label="Loading compliance matrix" />;
  if (error) return <ErrorState message="Could not load compliance data." onRetry={() => refetch()} />;
  if (!data?.length) return null;

  return (
    <div className="space-y-4">
      {/* Controls row */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[180px] max-w-xs">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground pointer-events-none" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search products or companies…"
            className="w-full pl-8 pr-3 py-1.5 text-[12px] rounded-md border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary/50 placeholder:text-muted-foreground"
          />
        </div>
        <div className="flex items-center gap-1 rounded-md border border-border bg-background p-0.5 text-[11.5px]">
          {(["all", "certified", "implied"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setFilterMode(m)}
              className={cn(
                "px-2.5 py-1 rounded capitalize transition-colors",
                filterMode === m
                  ? "bg-primary text-primary-foreground font-medium"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {m === "all" ? "All" : m === "certified" ? "Confirmed only" : "Implied"}
            </button>
          ))}
        </div>
        <p className="text-[12px] text-muted-foreground ml-auto whitespace-nowrap">
          {certifiedCount} confirmed · {data.length} total products
        </p>
        <Legend />
      </div>

      <div className="rounded-xl border border-border overflow-hidden bg-background">
        <div className="overflow-x-auto scrollbar-thin">
          <table className="w-full text-[12.5px] border-collapse">
            <thead>
              <tr className="bg-surface-subtle/60 border-b border-border">
                <th className="text-left font-semibold text-[11px] uppercase tracking-wider text-muted-foreground px-4 py-2.5 sticky left-0 bg-surface-subtle/60 z-10">
                  Product
                </th>
                {certTypes.map((c) => (
                  <th
                    key={c}
                    className="text-left font-semibold text-[11px] uppercase tracking-wider text-muted-foreground px-3 py-2.5 whitespace-nowrap"
                    title={`${c} certification`}
                  >
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {grouped.length === 0 && (
                <tr>
                  <td colSpan={certTypes.length + 1} className="px-4 py-6 text-center text-[12px] text-muted-foreground">
                    No products match the current filter.
                  </td>
                </tr>
              )}
              {grouped.map(([company, products]) => (
                <>
                  <tr key={`${company}-h`} className="bg-surface-subtle/30 border-b border-border">
                    <td
                      colSpan={certTypes.length + 1}
                      className="px-4 py-1.5 text-[11px] font-semibold text-foreground/80 uppercase tracking-wider"
                    >
                      {company}
                    </td>
                  </tr>
                  {products!.map((p) => (
                    <tr
                      key={p.product_id}
                      className="border-b border-border last:border-b-0 hover:bg-surface-hover/40"
                    >
                      <td className="px-4 py-2 sticky left-0 bg-background z-10">
                        <div className="flex items-center gap-2">
                          <span className="text-foreground font-medium">{p.product_name}</span>
                          {p.off_market && (
                            <span title="Off-market" className="inline-flex items-center gap-1 text-status-skipped">
                              <AlertTriangle className="size-3" />
                            </span>
                          )}
                        </div>
                      </td>
                      {certTypes.map((c) => {
                        const status = p.certifications[c] ?? "none";
                        return (
                          <td key={c} className="px-3 py-2">
                            <Cell status={status} certName={c} />
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Cell({ status, certName }: { status: "certified" | "implied" | "derived" | "none"; certName: string }) {
  if (status === "none") {
    return <span className="block size-4 rounded border border-border bg-background" title={`${certName}: not certified`} />;
  }
  const tooltip =
    status === "certified"
      ? `${certName}: confirmed certification`
      : `${certName}: implied by a higher-level certification`;
  return (
    <span
      className={cn(
        "inline-flex items-center justify-center size-5 rounded cursor-help",
        status === "certified" ? "bg-status-completed text-white" : "bg-status-skipped/30 text-status-skipped",
      )}
      title={tooltip}
    >
      <ShieldCheck className="size-3" strokeWidth={2.5} />
    </span>
  );
}

function Legend() {
  return (
    <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
      <div className="flex items-center gap-1.5" title="Certification explicitly confirmed in compliance data">
        <span className="size-3.5 rounded bg-status-completed" /> Confirmed
      </div>
      <div
        className="flex items-center gap-1.5"
        title="Certification derived from a higher-level cert (e.g. Vegan → Vegetarian, Organic → NonGMO)"
      >
        <span className="size-3.5 rounded bg-status-skipped/30 border border-status-skipped/40" /> Implied
      </div>
      <div className="flex items-center gap-1.5" title="No certification data for this product">
        <span className="size-3.5 rounded border border-border" /> None
      </div>
    </div>
  );
}
