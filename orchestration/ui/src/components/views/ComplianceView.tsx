import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { AlertTriangle, ShieldCheck } from "lucide-react";
import { agnesApi } from "@/lib/agnesApi";
import { ErrorState, LoadingState } from "@/components/shared/States";
import { cn } from "@/lib/utils";

export function ComplianceView() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["compliance"],
    queryFn: () => agnesApi.compliance(),
  });

  const certTypes = useMemo(() => {
    if (!data) return [];
    const set = new Set<string>();
    data.forEach((p) => Object.keys(p.certifications).forEach((c) => set.add(c)));
    return Array.from(set);
  }, [data]);

  const grouped = useMemo(() => {
    const map = new Map<string, typeof data>();
    data?.forEach((p) => {
      const arr = map.get(p.company) ?? [];
      arr.push(p);
      map.set(p.company, arr);
    });
    return Array.from(map.entries());
  }, [data]);

  if (isLoading) return <LoadingState label="Loading compliance matrix" />;
  if (error) return <ErrorState message="Could not load compliance data." onRetry={() => refetch()} />;
  if (!data?.length) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-[12.5px] text-muted-foreground">
          {data.length} products certified across {data.reduce((acc, p) => acc + Object.values(p.certifications).filter((s) => s !== "none").length, 0)} records
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
                  <th key={c} className="text-left font-semibold text-[11px] uppercase tracking-wider text-muted-foreground px-3 py-2.5 whitespace-nowrap">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {grouped.map(([company, products]) => (
                <>
                  <tr key={`${company}-h`} className="bg-surface-subtle/30 border-b border-border">
                    <td colSpan={certTypes.length + 1} className="px-4 py-1.5 text-[11px] font-semibold text-foreground/80 uppercase tracking-wider">
                      {company}
                    </td>
                  </tr>
                  {products!.map((p) => (
                    <tr key={p.product_id} className="border-b border-border last:border-b-0 hover:bg-surface-hover/40">
                      <td className="px-4 py-2 sticky left-0 bg-background z-10 group-hover:bg-surface-hover/40">
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
                            <Cell status={status} />
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

function Cell({ status }: { status: "certified" | "implied" | "none" }) {
  if (status === "none") return <span className="block size-4 rounded border border-border bg-background" />;
  return (
    <span
      className={cn(
        "inline-flex items-center justify-center size-5 rounded",
        status === "certified" ? "bg-status-completed text-white" : "bg-status-skipped/30 text-status-skipped",
      )}
      title={status}
    >
      <ShieldCheck className="size-3" strokeWidth={2.5} />
    </span>
  );
}

function Legend() {
  return (
    <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
      <div className="flex items-center gap-1.5">
        <span className="size-3.5 rounded bg-status-completed" /> Certified
      </div>
      <div className="flex items-center gap-1.5">
        <span className="size-3.5 rounded bg-status-skipped/30 border border-status-skipped/40" /> Implied
      </div>
      <div className="flex items-center gap-1.5">
        <span className="size-3.5 rounded border border-border" /> None
      </div>
    </div>
  );
}
