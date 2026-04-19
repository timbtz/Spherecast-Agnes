import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Info } from "lucide-react";
import { agnesApi } from "@/lib/agnesApi";
import type { Lane } from "@/types/agnes";
import { LoadingState, EmptyState, ErrorState } from "@/components/shared/States";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// ── Mode icons ────────────────────────────────────────────────────────────────

const MODE_ICON: Record<Lane["mode"], string> = {
  ocean: "🚢",
  air:   "✈️",
  truck: "🚛",
  rail:  "🚂",
};

const MODE_LABEL: Record<Lane["mode"], string> = {
  ocean: "Ocean",
  air:   "Air",
  truck: "Truck",
  rail:  "Rail",
};

// ── Landed Cost Index bar ─────────────────────────────────────────────────────

function LandedCostBar({ index }: { index: number }) {
  // index is 0–1, lower is better; bar fills proportionally, color inverted
  const pct = Math.max(0, Math.min(1, index)) * 100;
  const color =
    index <= 0.33 ? "hsl(var(--status-completed))"
    : index <= 0.66 ? "hsl(var(--status-skipped))"
    : "hsl(var(--status-failed))";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden min-w-[60px]">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="text-[12px] font-mono tabular-nums text-foreground/80 min-w-[36px] text-right">
        {index.toFixed(2)}
      </span>
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function computeLandedIndex(lanes: Lane[]): Map<Lane, number> {
  if (!lanes.length) return new Map();
  const maxCost = Math.max(...lanes.map((l) => l.cost_usd_per_kg));
  const minCost = Math.min(...lanes.map((l) => l.cost_usd_per_kg));
  const maxLead = Math.max(...lanes.map((l) => l.lead_time_days));
  const minLead = Math.min(...lanes.map((l) => l.lead_time_days));

  const normCost = (v: number) =>
    maxCost === minCost ? 0 : (v - minCost) / (maxCost - minCost);
  const normLead = (v: number) =>
    maxLead === minLead ? 0 : (v - minLead) / (maxLead - minLead);

  const result = new Map<Lane, number>();
  for (const lane of lanes) {
    result.set(lane, normCost(lane.cost_usd_per_kg) * 0.6 + normLead(lane.lead_time_days) * 0.4);
  }
  return result;
}

function uniqueSorted<T>(arr: T[]): T[] {
  return Array.from(new Set(arr)).sort() as T[];
}

// ── Main view ─────────────────────────────────────────────────────────────────

export function TradeRoutesView() {
  const [originFilter, setOriginFilter] = useState<string>("all");
  const [modeFilter, setModeFilter]   = useState<string>("all");

  const { data, isLoading, error } = useQuery({
    queryKey: ["lanes"],
    queryFn: () => agnesApi.lanes(),
  });

  const allLanes = data?.lanes ?? [];

  const origins = useMemo(() => uniqueSorted(allLanes.map((l) => l.origin)), [allLanes]);

  const filtered = useMemo(() => {
    let lanes = allLanes;
    if (originFilter !== "all") lanes = lanes.filter((l) => l.origin === originFilter);
    if (modeFilter !== "all")   lanes = lanes.filter((l) => l.mode === modeFilter);
    return lanes.slice().sort((a, b) => a.cost_usd_per_kg - b.cost_usd_per_kg);
  }, [allLanes, originFilter, modeFilter]);

  const landedMap = useMemo(() => computeLandedIndex(filtered), [filtered]);

  return (
    <div className="flex flex-col gap-4">
      {/* Info callout */}
      <div className="flex items-start gap-2.5 rounded-lg border border-blue-500/25 bg-blue-500/10 px-4 py-3 text-[12.5px] text-blue-300">
        <Info className="size-4 shrink-0 mt-0.5 text-blue-400" />
        <p>
          Rates are indicative at country level. Production volumes require direct negotiation.
        </p>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="text-[12px] font-semibold text-muted-foreground uppercase tracking-wide whitespace-nowrap">
            Origin
          </span>
          <Select value={originFilter} onValueChange={setOriginFilter}>
            <SelectTrigger className="w-[110px] text-[12px] h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              {origins.map((o) => (
                <SelectItem key={o} value={o}>{o}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[12px] font-semibold text-muted-foreground uppercase tracking-wide whitespace-nowrap">
            Mode
          </span>
          <Select value={modeFilter} onValueChange={setModeFilter}>
            <SelectTrigger className="w-[110px] text-[12px] h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="ocean">🚢 Ocean</SelectItem>
              <SelectItem value="air">✈️ Air</SelectItem>
              <SelectItem value="truck">🚛 Truck</SelectItem>
              <SelectItem value="rail">🚂 Rail</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Table */}
      {isLoading ? (
        <LoadingState label="Loading trade routes…" />
      ) : error ? (
        <ErrorState message="Failed to load trade route data." />
      ) : !filtered.length ? (
        <EmptyState title="No routes match" body="Adjust the origin or mode filter." />
      ) : (
        <div className="flex flex-col gap-2">
          {/* Header */}
          <div
            className="grid gap-x-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wide px-3 pb-1"
            style={{ gridTemplateColumns: "1.5fr 100px 120px 100px 2fr" }}
          >
            <span>Origin → Dest</span>
            <span>Mode</span>
            <span>Lead Time</span>
            <span>Cost $/kg</span>
            <span>Landed Cost Index ↓ lower is better</span>
          </div>

          {filtered.map((lane, i) => {
            const idx = landedMap.get(lane) ?? 0;
            return (
              <div
                key={i}
                className="grid gap-x-3 items-center px-3 py-2.5 rounded-lg border border-border bg-background hover:bg-accent/30 transition-colors text-[13px]"
                style={{ gridTemplateColumns: "1.5fr 100px 120px 100px 2fr" }}
              >
                <span className="font-medium font-mono">
                  {lane.origin} → {lane.dest}
                </span>
                <span>
                  {MODE_ICON[lane.mode]}{" "}
                  <span className="text-[12px] text-muted-foreground">{MODE_LABEL[lane.mode]}</span>
                </span>
                <span className="font-mono text-[12px]">{lane.lead_time_days}d</span>
                <span className="font-mono text-[12px]">${lane.cost_usd_per_kg.toFixed(2)}</span>
                <LandedCostBar index={idx} />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
