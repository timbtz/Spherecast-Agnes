import { useMemo, useState } from "react";
import { Bot, Wrench, CheckCircle2, XCircle, MinusCircle, Loader2, X, ChevronDown, ChevronUp } from "lucide-react";
import type { DagGraph, DagNode } from "@/types/agnes";
import { useAgnesStore, type NodeRuntimeState } from "@/store/agnesStore";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// DagGraphView — left→right flowchart, one column per topological layer.
// Nodes render as cards with status rings; SVG paths animate between them.
// Selected-node output renders in a panel BELOW the canvas (no clipping).
// ---------------------------------------------------------------------------

const NODE_W = 180;
const NODE_H = 84;
const COL_GAP = 64;
const ROW_GAP = 18;
const PAD = 24;

// Prose output field names — any of these will be rendered as formatted text.
const PROSE_FIELDS = ["summary", "proposals_narrative", "proposal_text", "alert_narrative", "narrative"];

function humanizeClass(s?: string): string {
  if (!s) return "";
  return s
    .replace(/([A-Z])/g, " $1")
    .replace(/^\s/, "")
    .replace(/\s*(Tool|Agent)\s*$/, "")
    .trim();
}

function statusRing(status: NodeRuntimeState["status"]): string {
  if (status === "running") return "ring-2 ring-status-running ring-offset-2 ring-offset-background animate-status-pulse";
  if (status === "completed") return "ring-1 ring-status-completed/50";
  if (status === "failed") return "ring-2 ring-status-failed";
  if (status === "skipped") return "ring-1 ring-status-skipped/40 opacity-60";
  return "ring-1 ring-border";
}

function StatusIcon({ status }: { status: NodeRuntimeState["status"] }) {
  if (status === "running") return <Loader2 className="size-3 text-status-running animate-spin" />;
  if (status === "completed") return <CheckCircle2 className="size-3 text-status-completed" />;
  if (status === "failed") return <XCircle className="size-3 text-status-failed" />;
  if (status === "skipped") return <MinusCircle className="size-3 text-status-skipped" />;
  return <span className="size-1.5 rounded-full bg-muted-foreground/40" />;
}

export function DagGraphView({
  graph,
  overrideNodeStates,
}: {
  graph: DagGraph;
  overrideNodeStates?: Record<string, NodeRuntimeState>;
}) {
  const storeNodeStates = useAgnesStore((s) => s.nodeStates);
  const nodeStates = overrideNodeStates ?? storeNodeStates;
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

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
    const m = new Map<string, DagNode>();
    graph.nodes.forEach((n) => m.set(n.id, n));
    return m;
  }, [graph]);

  const edges = useMemo(() => {
    const list: Array<{ from: string; to: string }> = [];
    graph.nodes.forEach((n) => n.depends_on.forEach((dep) => list.push({ from: dep, to: n.id })));
    return list;
  }, [graph]);

  const selectedNode = selectedNodeId ? nodeById.get(selectedNodeId) : null;
  const selectedState = selectedNodeId
    ? (nodeStates[selectedNodeId] ?? { id: selectedNodeId, status: "pending" as const })
    : null;

  return (
    <div className="rounded-xl border border-border bg-background overflow-hidden">
      {/* Header */}
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

      {/* DAG Canvas — horizontal scroll only; overflow-y visible so output panels aren't clipped */}
      <div className="overflow-x-auto scrollbar-thin">
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
            const isSelected = selectedNodeId === n.id;
            const classLabel = humanizeClass(n.class);
            return (
              <div
                key={n.id}
                className="absolute"
                style={{ left: pos.x, top: pos.y, width: NODE_W }}
              >
                <button
                  onClick={() => setSelectedNodeId(isSelected ? null : n.id)}
                  title="Click to view output"
                  className={cn(
                    "w-full text-left bg-background rounded-lg px-2.5 py-2 transition-all hover:shadow-md",
                    statusRing(rs.status),
                    isSelected && "shadow-md ring-2 ring-primary/60",
                  )}
                  style={{ height: NODE_H }}
                >
                  <div className="flex items-center justify-between gap-1.5 mb-0.5">
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
                  <p className="text-[12px] font-medium text-foreground truncate leading-snug">{n.id}</p>
                  {classLabel && (
                    <p className="text-[10px] text-muted-foreground truncate leading-snug mt-0.5">{classLabel}</p>
                  )}
                  {rs.elapsedMs != null && rs.status === "completed" ? (
                    <p className="text-[10px] font-mono text-status-completed/80 tabular-nums mt-0.5">✓ {rs.elapsedMs}ms</p>
                  ) : n.when ? (
                    <p className="text-[10px] text-muted-foreground/70 truncate mt-0.5 italic">when: {n.when}</p>
                  ) : null}
                </button>
              </div>
            );
          })}
        </div>
      </div>

      {/* Selected node detail panel — rendered OUTSIDE overflow-x-auto so it's never clipped */}
      {selectedNode && selectedState && (
        <NodeDetailPanel
          node={selectedNode}
          state={selectedState}
          onClose={() => setSelectedNodeId(null)}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// NodeDetailPanel — shown below the DAG canvas when a node is selected.
// ---------------------------------------------------------------------------

function NodeDetailPanel({
  node,
  state,
  onClose,
}: {
  node: DagNode;
  state: NodeRuntimeState;
  onClose: () => void;
}) {
  const [expanded, setExpanded] = useState(true);
  const isAgent = node.type === "agent";
  const classLabel = humanizeClass(node.class);
  const output = (state.output ?? {}) as Record<string, unknown>;

  // Extract prose fields
  let prose: string | undefined;
  for (const f of PROSE_FIELDS) {
    if (typeof output[f] === "string" && output[f]) {
      prose = output[f] as string;
      break;
    }
  }

  const {
    _elapsed_ms,
    error,
    skipped,
    ...rest
  } = output;

  // Remove prose fields from rest
  const restWithoutProse = Object.fromEntries(
    Object.entries(rest).filter(([k]) => !PROSE_FIELDS.includes(k))
  );

  const errorText = error as string | undefined;
  const skippedReason = state.status === "skipped"
    ? (skipped as string | undefined) ?? (node.when ? `Condition not met: ${node.when}` : "Skipped by pipeline")
    : undefined;

  const scalars = Object.entries(restWithoutProse).filter(
    ([, v]) => typeof v === "string" || typeof v === "number" || typeof v === "boolean",
  );
  const complex = Object.entries(restWithoutProse).filter(
    ([, v]) => Array.isArray(v) || (typeof v === "object" && v !== null),
  );

  const hasOutput = prose || errorText || skippedReason || scalars.length > 0 || complex.length > 0;

  return (
    <div className="border-t border-border bg-surface-subtle/30 animate-fade-in">
      {/* Panel header */}
      <div className="flex items-center justify-between px-4 py-2.5 gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className={cn(
            "pill border text-[10px] shrink-0",
            isAgent
              ? "bg-orb-thinking/10 text-orb-thinking border-orb-thinking/20"
              : "bg-secondary text-secondary-foreground border-border",
          )}>
            {isAgent ? <Bot className="size-2.5" /> : <Wrench className="size-2.5" />}
            {isAgent ? "Agent" : "Tool"}
          </span>
          <p className="text-[13px] font-semibold text-foreground truncate">{node.id}</p>
          {classLabel && (
            <p className="text-[11px] text-muted-foreground truncate hidden sm:block">{classLabel}</p>
          )}
          {node.when && (
            <span className="pill bg-muted text-muted-foreground border border-border text-[10px] shrink-0">
              when: {node.when}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {state.elapsedMs != null && (
            <span className="text-[11px] font-mono text-muted-foreground tabular-nums">
              {state.elapsedMs}ms
            </span>
          )}
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            {expanded ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
          </button>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="size-4" />
          </button>
        </div>
      </div>

      {/* Panel body */}
      {expanded && (
        <div className="px-4 pb-4 space-y-3 text-[12px]">
          {/* Node description line */}
          {classLabel && (
            <p className="text-[11.5px] text-muted-foreground sm:hidden">{classLabel}</p>
          )}

          {/* Status pill */}
          <div className="flex items-center gap-2">
            <span className={cn(
              "pill border capitalize text-[11px]",
              state.status === "completed" && "bg-status-completed/10 text-status-completed border-status-completed/30",
              state.status === "running" && "bg-status-running/10 text-status-running border-status-running/30",
              state.status === "failed" && "bg-status-failed/10 text-status-failed border-status-failed/30",
              state.status === "skipped" && "bg-muted text-muted-foreground border-border",
              state.status === "pending" && "bg-muted text-muted-foreground border-border",
            )}>
              {state.status === "running" && <span className="size-1.5 rounded-full bg-current animate-status-pulse" />}
              {state.status}
            </span>
            {state.status === "pending" && state.status !== "running" && !hasOutput && (
              <span className="text-[11px] text-muted-foreground">Waiting to run…</span>
            )}
          </div>

          {/* Skipped reason */}
          {skippedReason && (
            <div className="rounded-md bg-muted/50 border border-border px-3 py-2">
              <p className="text-[10.5px] uppercase tracking-wider text-muted-foreground font-semibold mb-1">Skipped</p>
              <p className="text-foreground/80 font-mono text-[11px]">{skippedReason}</p>
            </div>
          )}

          {/* Error */}
          {errorText && (
            <div className="rounded-md bg-status-failed/5 border border-status-failed/20 px-3 py-2">
              <p className="text-[10.5px] uppercase tracking-wider text-status-failed font-semibold mb-1">Error</p>
              <p className="text-status-failed/90 font-mono text-[11px] whitespace-pre-wrap">{errorText}</p>
            </div>
          )}

          {/* Prose output */}
          {prose && (
            <div className="rounded-md bg-background border border-border px-3 py-2.5">
              <p className="text-[10.5px] uppercase tracking-wider text-muted-foreground font-semibold mb-1.5">Output</p>
              <p className="text-foreground/90 leading-relaxed whitespace-pre-wrap text-[12px]">{prose}</p>
            </div>
          )}

          {/* Scalar key-value table */}
          {scalars.length > 0 && (
            <div className="rounded-md bg-background border border-border overflow-hidden">
              <table className="w-full text-[11.5px]">
                <tbody>
                  {scalars.map(([k, v]) => (
                    <tr key={k} className="border-b border-border/50 last:border-b-0">
                      <td className="text-muted-foreground px-3 py-1.5 font-mono align-top w-[40%] border-r border-border/50">{k}</td>
                      <td className="text-foreground/85 px-3 py-1.5 font-mono break-all">{String(v)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Complex / array fields */}
          {complex.length > 0 && (
            <div className="space-y-2">
              {complex.map(([k, v]) => (
                <ComplexField key={k} label={k} value={v} />
              ))}
            </div>
          )}

          {!hasOutput && state.status !== "pending" && state.status !== "running" && (
            <p className="text-[11.5px] text-muted-foreground italic">No output captured for this node.</p>
          )}
        </div>
      )}
    </div>
  );
}

// Renders a single complex (object/array) output field with a toggle.
function ComplexField({ label, value }: { label: string; value: unknown }) {
  const [open, setOpen] = useState(false);
  const isArray = Array.isArray(value);
  const count = isArray ? (value as unknown[]).length : null;

  return (
    <div className="rounded-md bg-background border border-border overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-1.5 text-[11px] font-mono text-muted-foreground hover:bg-surface-hover/60 transition-colors"
      >
        <span>
          {label}
          {count !== null && (
            <span className="ml-1.5 pill bg-muted text-muted-foreground border border-border">{count} items</span>
          )}
        </span>
        {open ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
      </button>
      {open && (
        <pre className="px-3 py-2 text-[10.5px] font-mono text-foreground/70 whitespace-pre-wrap break-words border-t border-border/60 max-h-48 overflow-auto scrollbar-thin">
          {JSON.stringify(value, null, 2)}
        </pre>
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

// ---------------------------------------------------------------------------
// ActiveRunInline — compact status panel shown next to the orb
// ---------------------------------------------------------------------------
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
