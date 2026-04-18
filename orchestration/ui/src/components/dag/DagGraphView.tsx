import { useEffect, useMemo, useRef, useState } from "react";
import { Bot, Wrench, ChevronRight, ChevronDown, CheckCircle2, XCircle, MinusCircle, Loader2 } from "lucide-react";
import type { DagGraph } from "@/types/agnes";
import { useAgnesStore, type NodeRuntimeState } from "@/store/agnesStore";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// DagGraphView — left→right flowchart, one column per topological layer.
// Nodes render as cards with status rings; SVG paths animate between them.
// ---------------------------------------------------------------------------

const NODE_W = 180;
const NODE_H = 64;
const COL_GAP = 64;
const ROW_GAP = 18;
const PAD = 24;

function statusRing(status: NodeRuntimeState["status"]): string {
  if (status === "running") return "ring-2 ring-status-running ring-offset-2 ring-offset-background animate-status-pulse";
  if (status === "completed") return "ring-1 ring-status-completed/50";
  if (status === "failed") return "ring-2 ring-status-failed";
  if (status === "skipped") return "ring-1 ring-status-skipped/40";
  return "ring-1 ring-border";
}

function StatusIcon({ status }: { status: NodeRuntimeState["status"] }) {
  if (status === "running") return <Loader2 className="size-3 text-status-running animate-spin" />;
  if (status === "completed") return <CheckCircle2 className="size-3 text-status-completed" />;
  if (status === "failed") return <XCircle className="size-3 text-status-failed" />;
  if (status === "skipped") return <MinusCircle className="size-3 text-status-skipped" />;
  return <span className="size-1.5 rounded-full bg-muted-foreground/40" />;
}

export function DagGraphView({ graph, overrideNodeStates }: { graph: DagGraph; overrideNodeStates?: Record<string, NodeRuntimeState> }) {
  const storeNodeStates = useAgnesStore((s) => s.nodeStates);
  const nodeStates = overrideNodeStates ?? storeNodeStates;
  const [expanded, setExpanded] = useState<string | null>(null);

  // Compute (col, row) for each node from `layers`
  const positions = useMemo(() => {
    const map = new Map<string, { x: number; y: number }>();
    const layerHeights = graph.layers.map((l) => l.length);
    const tallest = Math.max(...layerHeights, 1);
    const totalH = tallest * NODE_H + (tallest - 1) * ROW_GAP;
    graph.layers.forEach((layer, ci) => {
      const layerH = layer.length * NODE_H + (layer.length - 1) * ROW_GAP;
      const offsetY = (totalH - layerH) / 2;
      layer.forEach((nid, ri) => {
        map.set(nid, {
          x: PAD + ci * (NODE_W + COL_GAP),
          y: PAD + offsetY + ri * (NODE_H + ROW_GAP),
        });
      });
    });
    const width = PAD * 2 + graph.layers.length * NODE_W + (graph.layers.length - 1) * COL_GAP;
    const height = PAD * 2 + totalH;
    return { map, width, height };
  }, [graph]);

  const nodeById = useMemo(() => {
    const m = new Map<string, (typeof graph.nodes)[number]>();
    graph.nodes.forEach((n) => m.set(n.id, n));
    return m;
  }, [graph]);

  // Edges = depends_on relationships
  const edges = useMemo(() => {
    const list: Array<{ from: string; to: string }> = [];
    graph.nodes.forEach((n) => n.depends_on.forEach((dep) => list.push({ from: dep, to: n.id })));
    return list;
  }, [graph]);

  return (
    <div className="rounded-xl border border-border bg-background overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-surface-subtle/40">
        <div className="flex items-center gap-2">
          <p className="text-[12px] font-semibold text-foreground">{graph.name}</p>
          <span className="pill bg-muted text-muted-foreground border border-border">
            trigger: {graph.trigger}
          </span>
          <span className="text-[11px] text-muted-foreground">
            {graph.nodes.length} nodes · {graph.layers.length} layers
          </span>
        </div>
        <div className="flex items-center gap-3 text-[10.5px] text-muted-foreground">
          <LegendDot color="status-running" label="Running" />
          <LegendDot color="status-completed" label="Done" />
          <LegendDot color="status-failed" label="Failed" />
          <LegendDot color="status-skipped" label="Skipped" />
        </div>
      </div>

      <div className="overflow-auto scrollbar-thin">
        <div className="relative" style={{ width: positions.width, height: positions.height }}>
          {/* SVG edges */}
          <svg
            className="absolute inset-0 pointer-events-none"
            width={positions.width}
            height={positions.height}
          >
            <defs>
              <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="hsl(var(--border-strong))" />
              </marker>
              <marker id="arrow-active" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="hsl(var(--status-running))" />
              </marker>
            </defs>
            {edges.map(({ from, to }, i) => {
              const a = positions.map.get(from);
              const b = positions.map.get(to);
              if (!a || !b) return null;
              const fromStatus = nodeStates[from]?.status;
              const toStatus = nodeStates[to]?.status;
              const active = fromStatus === "completed" && (toStatus === "running" || toStatus === "pending");
              const flowed = fromStatus === "completed" && toStatus === "completed";
              const x1 = a.x + NODE_W;
              const y1 = a.y + NODE_H / 2;
              const x2 = b.x;
              const y2 = b.y + NODE_H / 2;
              const mx = (x1 + x2) / 2;
              const d = `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
              const stroke = active
                ? "hsl(var(--status-running))"
                : flowed
                  ? "hsl(var(--status-completed) / 0.5)"
                  : "hsl(var(--border-strong))";
              return (
                <path
                  key={i}
                  d={d}
                  fill="none"
                  stroke={stroke}
                  strokeWidth={1.5}
                  markerEnd={active ? "url(#arrow-active)" : "url(#arrow)"}
                  strokeDasharray={active ? "6 4" : undefined}
                  className={active ? "animate-dash-flow" : undefined}
                />
              );
            })}
          </svg>

          {/* Nodes */}
          {graph.nodes.map((n) => {
            const pos = positions.map.get(n.id);
            if (!pos) return null;
            const rs = nodeStates[n.id] ?? { id: n.id, status: "pending" as const };
            const isAgent = n.type === "agent";
            const isExpanded = expanded === n.id;
            return (
              <div
                key={n.id}
                className="absolute"
                style={{ left: pos.x, top: pos.y, width: NODE_W }}
              >
                <button
                  onClick={() => setExpanded(isExpanded ? null : n.id)}
                  className={cn(
                    "w-full text-left bg-background rounded-lg px-2.5 py-2 transition-all hover:shadow-md",
                    statusRing(rs.status),
                  )}
                  style={{ height: NODE_H }}
                >
                  <div className="flex items-center justify-between gap-1.5 mb-1">
                    <span className={cn(
                      "pill border text-[10px]",
                      isAgent
                        ? "bg-orb-thinking/10 text-orb-thinking border-orb-thinking/20"
                        : "bg-secondary text-secondary-foreground border-border",
                    )}>
                      {isAgent ? <Bot className="size-2.5" /> : <Wrench className="size-2.5" />}
                      {isAgent ? "Agent" : "Tool"}
                    </span>
                    <StatusIcon status={rs.status} />
                  </div>
                  <p className="text-[12px] font-medium text-foreground truncate">{n.id}</p>
                  {rs.elapsedMs != null && rs.status === "completed" && (
                    <p className="text-[10.5px] font-mono text-muted-foreground tabular-nums mt-0.5">
                      ✓ {rs.elapsedMs}ms
                    </p>
                  )}
                </button>
                {isExpanded && rs.output && (
                  <NodeOutputPanel output={rs.output} />
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// Structured display of node_output — prose fields first, then scalar table, then raw JSON for anything else
function NodeOutputPanel({ output }: { output: Record<string, unknown> }) {
  const { summary, proposals_narrative, proposal_text, skipped, error, _elapsed_ms, ...rest } = output;
  const prose = (summary ?? proposals_narrative ?? proposal_text) as string | undefined;
  const errorText = (error ?? skipped) as string | undefined;

  const scalars = Object.entries(rest).filter(
    ([, v]) => typeof v === "string" || typeof v === "number" || typeof v === "boolean",
  );
  const complex = Object.entries(rest).filter(
    ([, v]) => typeof v === "object" && v !== null,
  );

  return (
    <div className="absolute z-10 left-0 right-0 mt-1 max-h-72 overflow-auto bg-popover border border-border rounded-md shadow-lg scrollbar-thin text-[11px]">
      {prose && (
        <div className="px-3 py-2.5 border-b border-border/60">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold mb-1">Output</p>
          <p className="text-foreground/90 leading-relaxed whitespace-pre-wrap">{prose}</p>
        </div>
      )}
      {errorText && (
        <div className="px-3 py-2.5 border-b border-border/60 bg-status-failed/5">
          <p className="text-[10px] uppercase tracking-wider text-status-failed font-semibold mb-1">{skipped ? "Skipped" : "Error"}</p>
          <p className="text-status-failed/90 leading-relaxed font-mono text-[10.5px] whitespace-pre-wrap">{errorText}</p>
        </div>
      )}
      {scalars.length > 0 && (
        <div className="px-3 py-2 border-b border-border/60">
          <table className="w-full">
            <tbody>
              {scalars.map(([k, v]) => (
                <tr key={k}>
                  <td className="text-muted-foreground pr-3 py-0.5 font-mono align-top">{k}</td>
                  <td className="text-foreground/85 py-0.5 font-mono break-all">{String(v)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {complex.length > 0 && (
        <div className="px-3 py-2">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold mb-1">Data</p>
          <pre className="text-foreground/70 whitespace-pre-wrap break-words font-mono text-[10px]">
            {JSON.stringify(Object.fromEntries(complex), null, 2)}
          </pre>
        </div>
      )}
      {!prose && !errorText && scalars.length === 0 && complex.length === 0 && (
        <div className="px-3 py-2 text-muted-foreground">No output captured.</div>
      )}
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-1">
      <span className={`size-1.5 rounded-full bg-${color}`} />
      <span>{label}</span>
    </div>
  );
}

// Compact status panel shown next to the orb when a run is active
export function ActiveRunInline() {
  const activeRunId = useAgnesStore((s) => s.activeRunId);
  const activePipeline = useAgnesStore((s) => s.activePipeline);
  const activeGraph = useAgnesStore((s) => s.activeGraph);
  const nodeStates = useAgnesStore((s) => s.nodeStates);
  if (!activeRunId || !activeGraph) return null;
  const total = activeGraph.nodes.length;
  const done = Object.values(nodeStates).filter((n) => n.status === "completed").length;
  const running = Object.values(nodeStates).filter((n) => n.status === "running").length;
  return (
    <div className="rounded-lg border border-border bg-surface-subtle px-3 py-2 flex items-center gap-3 text-[12px]">
      <Loader2 className={cn("size-3.5 text-status-running", running > 0 && "animate-spin")} />
      <div className="flex flex-col">
        <span className="font-medium text-foreground">{activePipeline}</span>
        <span className="text-[11px] text-muted-foreground font-mono truncate max-w-[180px]">{activeRunId}</span>
      </div>
      <span className="ml-auto text-muted-foreground tabular-nums">{done}/{total}</span>
    </div>
  );
}
