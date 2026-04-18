import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Workflow, Play } from "lucide-react";
import { agnesApi } from "@/lib/agnesApi";
import { useAgnesStore } from "@/store/agnesStore";
import { DagGraphView } from "@/components/dag/DagGraphView";
import { EmptyState, ErrorState, LoadingState } from "@/components/shared/States";
import type { PipelineName, RunStatus } from "@/types/agnes";
import { cn } from "@/lib/utils";

const PIPELINE_COLORS: Record<string, string> = {
  proactive_consolidation: "bg-primary/10 text-primary border-primary/20",
  supplier_fallout: "bg-status-failed/10 text-status-failed border-status-failed/20",
  price_audit: "bg-status-skipped/10 text-status-skipped border-status-skipped/30",
  substitution_discovery: "bg-orb-thinking/10 text-orb-thinking border-orb-thinking/20",
  new_ingredient_research: "bg-status-completed/10 text-status-completed border-status-completed/20",
};

const STATUS_COLORS: Record<RunStatus, string> = {
  running: "bg-status-running/10 text-status-running border-status-running/20",
  completed: "bg-status-completed/10 text-status-completed border-status-completed/20",
  failed: "bg-status-failed/10 text-status-failed border-status-failed/20",
  queued: "bg-muted text-muted-foreground border-border",
};

export function PipelineRunsView() {
  const { data: runs, isLoading, error, refetch } = useQuery({
    queryKey: ["runs"],
    queryFn: () => agnesApi.listRuns(),
    refetchInterval: 8000,
  });
  const [expanded, setExpanded] = useState<string | null>(null);
  const startRun = useAgnesStore((s) => s.startRun);
  const applyEvent = useAgnesStore((s) => s.applyEvent);
  const activeRunId = useAgnesStore((s) => s.activeRunId);
  const activeGraph = useAgnesStore((s) => s.activeGraph);

  const triggerPipeline = async (name: string) => {
    try {
      const { run_id } = await agnesApi.runPipeline(name as PipelineName);
      const graph = await agnesApi.pipelineGraph(name);
      startRun(run_id, name, graph);
      setExpanded(run_id);
      const close = agnesApi.streamRun(run_id, applyEvent);
      // optimistically prepend a new row
      setTimeout(() => refetch(), 6000);
      // Auto-clean stream subscription after 30s safety
      setTimeout(close, 30000);
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="space-y-5">
      {/* Triggers */}
      <div className="rounded-xl border border-border bg-background p-3.5">
        <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-2">
          Trigger a pipeline
        </p>
        <div className="flex flex-wrap gap-2">
          {Object.keys(PIPELINE_COLORS).map((p) => (
            <button
              key={p}
              onClick={() => void triggerPipeline(p)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-border bg-background hover:bg-surface-hover text-[12px] font-medium text-foreground transition-colors"
            >
              <Play className="size-3 text-primary" />
              {p.replace(/_/g, " ")}
            </button>
          ))}
        </div>
      </div>

      {/* Live active run (separate from history) */}
      {activeRunId && activeGraph && (
        <div className="space-y-2">
          <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">
            Live execution
          </p>
          <DagGraphView graph={activeGraph} />
        </div>
      )}

      {/* History */}
      <div>
        <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-2">
          Run history
        </p>
        {isLoading && <LoadingState label="Loading runs" />}
        {error && <ErrorState message="Could not load run history." onRetry={() => refetch()} />}
        {!isLoading && !runs?.length && (
          <EmptyState
            icon={<Workflow className="size-4" />}
            title="No runs yet"
            body="Trigger one of the pipelines above or talk to Agnes via the orb."
          />
        )}

        {!!runs?.length && (
          <div className="rounded-xl border border-border overflow-hidden bg-background">
            <div className="grid grid-cols-[1.4fr_1.6fr_120px_1.4fr_100px_36px] gap-3 px-4 py-2.5 border-b border-border bg-surface-subtle/60 text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">
              <div>Run ID</div>
              <div>Pipeline</div>
              <div>Status</div>
              <div>Started</div>
              <div>Duration</div>
              <div></div>
            </div>
            {runs.map((r) => {
              const open = expanded === r.run_id;
              return (
                <div key={r.run_id} className={cn("border-b border-border last:border-b-0", open && "bg-surface-subtle/40")}>
                  <button
                    onClick={() => setExpanded(open ? null : r.run_id)}
                    className="w-full grid grid-cols-[1.4fr_1.6fr_120px_1.4fr_100px_36px] gap-3 px-4 py-2.5 items-center hover:bg-surface-hover/60 transition-colors text-left"
                  >
                    <code className="text-[11.5px] font-mono text-foreground/85 truncate">{r.run_id}</code>
                    <div>
                      <span className={cn("pill border", PIPELINE_COLORS[r.pipeline] ?? "bg-muted text-muted-foreground border-border")}>
                        {r.pipeline}
                      </span>
                    </div>
                    <div>
                      <span className={cn("pill border capitalize", STATUS_COLORS[r.status])}>
                        {r.status === "running" && <span className="size-1.5 rounded-full bg-current animate-status-pulse" />}
                        {r.status}
                      </span>
                    </div>
                    <div className="text-[12px] text-muted-foreground tabular-nums">
                      {new Date(r.started_at).toLocaleString()}
                    </div>
                    <div className="text-[12px] font-mono tabular-nums text-foreground/80">
                      {r.duration_ms ? `${(r.duration_ms / 1000).toFixed(2)}s` : "—"}
                    </div>
                    <div className="flex justify-end text-muted-foreground">
                      {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                    </div>
                  </button>
                  {open && <RunGraph runId={r.run_id} pipeline={r.pipeline} />}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function RunGraph({ runId, pipeline }: { runId: string; pipeline: string }) {
  const { data: graph } = useQuery({
    queryKey: ["graph", pipeline],
    queryFn: () => agnesApi.pipelineGraph(pipeline),
  });
  const { data: detail } = useQuery({
    queryKey: ["run-detail", runId],
    queryFn: () => agnesApi.runDetail(runId),
  });

  // Build node states from historical events (independent of the global active-run store)
  const historicalNodeStates = useMemo(() => {
    if (!detail?.events || !graph) return null;
    const states: Record<string, import("@/store/agnesStore").NodeRuntimeState> = {};
    graph.nodes.forEach((n) => { states[n.id] = { id: n.id, status: "pending" }; });
    for (const ev of detail.events) {
      const e = ev as import("@/types/agnes").RunEvent & { node_id?: string; data?: string };
      const rawData = typeof e.data === "string" ? JSON.parse(e.data) : {};
      const nodeOutput = rawData.node_output ?? e.node_output;
      const nodeId = e.node_id;
      if (!nodeId) continue;
      const cur = states[nodeId] ?? { id: nodeId, status: "pending" as const };
      if (e.event_type === "node_started") {
        states[nodeId] = { ...cur, status: "running" };
      } else if (e.event_type === "node_completed") {
        states[nodeId] = {
          ...cur,
          status: "completed",
          elapsedMs: nodeOutput?._elapsed_ms,
          output: nodeOutput,
        };
      } else if (e.event_type === "node_failed") {
        states[nodeId] = { ...cur, status: "failed", output: nodeOutput ?? rawData };
      } else if (e.event_type === "node_skipped") {
        states[nodeId] = { ...cur, status: "skipped" };
      }
    }
    return states;
  }, [detail, graph]);

  if (!graph) return <div className="px-4 pb-4"><LoadingState label="Loading graph" /></div>;
  return (
    <div className="px-4 pb-4 animate-fade-in">
      <DagGraphView graph={graph} overrideNodeStates={historicalNodeStates ?? undefined} />
    </div>
  );
}
