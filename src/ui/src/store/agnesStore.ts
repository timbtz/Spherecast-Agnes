import { create } from "zustand";
import type { DagGraph, NodeStatus, RunEvent } from "@/types/agnes";

export type OrbState = "idle" | "listening" | "thinking" | "talking" | "error";

export interface NodeRuntimeState {
  id: string;
  status: NodeStatus;
  elapsedMs?: number;
  output?: Record<string, unknown>;
  startedAt?: number;
}

interface AgnesStore {
  // Voice / orb
  orbState: OrbState;
  setOrbState: (s: OrbState) => void;
  inputLevel: number; // 0..1 mic
  outputLevel: number; // 0..1 tts
  setInputLevel: (v: number) => void;
  setOutputLevel: (v: number) => void;
  transcript: string;
  setTranscript: (t: string) => void;
  lastResponse: string;
  setLastResponse: (t: string) => void;

  // Active run
  activeRunId: string | null;
  activePipeline: string | null;
  activeGraph: DagGraph | null;
  nodeStates: Record<string, NodeRuntimeState>;
  runEvents: RunEvent[];
  secondaryRunIds: string[];
  startRun: (runId: string, pipeline: string, graph: DagGraph | null) => void;
  addSecondaryRun: (runId: string) => void;
  applyEvent: (e: RunEvent) => void;
  clearRun: () => void;
  setGraph: (g: DagGraph) => void;

  // System
  apiOnline: boolean;
  setApiOnline: (b: boolean) => void;
}

export const useAgnesStore = create<AgnesStore>((set, get) => ({
  orbState: "idle",
  setOrbState: (s) => set({ orbState: s }),
  inputLevel: 0,
  outputLevel: 0,
  setInputLevel: (v) => set({ inputLevel: v }),
  setOutputLevel: (v) => set({ outputLevel: v }),
  transcript: "",
  setTranscript: (t) => set({ transcript: t }),
  lastResponse: "",
  setLastResponse: (t) => set({ lastResponse: t }),

  activeRunId: null,
  activePipeline: null,
  activeGraph: null,
  nodeStates: {},
  runEvents: [],
  secondaryRunIds: [],

  startRun: (runId, pipeline, graph) => {
    const nodeStates: Record<string, NodeRuntimeState> = {};
    if (graph) {
      graph.nodes.forEach((n) => {
        nodeStates[n.id] = { id: n.id, status: "pending" };
      });
    }
    set({
      activeRunId: runId,
      activePipeline: pipeline,
      activeGraph: graph,
      nodeStates,
      runEvents: [],
      secondaryRunIds: [],
    });
  },

  addSecondaryRun: (runId) =>
    set((s) => ({ secondaryRunIds: [...s.secondaryRunIds, runId] })),

  setGraph: (g) => {
    const cur = get().nodeStates;
    const next = { ...cur };
    g.nodes.forEach((n) => {
      if (!next[n.id]) next[n.id] = { id: n.id, status: "pending" };
    });
    set({ activeGraph: g, nodeStates: next });
  },

  applyEvent: (e) => {
    set((state) => {
      const events = [...state.runEvents, e];
      const nodeStates = { ...state.nodeStates };
      if (e.node_id) {
        const cur = nodeStates[e.node_id] ?? { id: e.node_id, status: "pending" };
        if (e.event_type === "node_started") {
          nodeStates[e.node_id] = { ...cur, status: "running", startedAt: Date.now() };
        } else if (e.event_type === "node_completed") {
          nodeStates[e.node_id] = {
            ...cur,
            status: "completed",
            elapsedMs: (e.node_output?._elapsed_ms as number) ?? cur.elapsedMs,
            output: e.node_output,
          };
        } else if (e.event_type === "node_failed") {
          nodeStates[e.node_id] = { ...cur, status: "failed", output: e.node_output };
        } else if (e.event_type === "node_skipped") {
          nodeStates[e.node_id] = { ...cur, status: "skipped" };
        }
      }
      return { runEvents: events, nodeStates };
    });
  },

  clearRun: () =>
    set({
      activeRunId: null,
      activePipeline: null,
      activeGraph: null,
      nodeStates: {},
      runEvents: [],
      secondaryRunIds: [],
    }),

  apiOnline: false,
  setApiOnline: (b) => set({ apiOnline: b }),
}));

// Extract a human-readable summary or proposal from a stream of events.
export function extractSpokenResponse(events: RunEvent[]): string | null {
  // Walk newest → oldest, prefer summary, then proposal_text.
  for (let i = events.length - 1; i >= 0; i--) {
    const out = events[i].node_output;
    if (!out) continue;
    if (typeof out.summary === "string" && out.summary.trim()) return out.summary as string;
  }
  for (let i = events.length - 1; i >= 0; i--) {
    const out = events[i].node_output;
    if (!out) continue;
    if (typeof out.proposal_text === "string" && (out.proposal_text as string).trim()) {
      return out.proposal_text as string;
    }
  }
  return null;
}
