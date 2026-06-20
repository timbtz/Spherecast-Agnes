import { create } from 'zustand'
import type { NodeState, PipelineGraph } from '@/types/agnes'

interface RunStore {
  activeRunId: string | null
  nodeStates: Record<string, NodeState>
  pipelineGraph: PipelineGraph | null
  activePipeline: string | null
  setActiveRun: (runId: string, pipeline: string) => void
  updateNode: (nodeId: string, state: Partial<NodeState>) => void
  setPipelineGraph: (graph: PipelineGraph) => void
  reset: () => void
}

export const useRunStore = create<RunStore>((set) => ({
  activeRunId: null,
  nodeStates: {},
  pipelineGraph: null,
  activePipeline: null,
  setActiveRun: (runId, pipeline) => set({ activeRunId: runId, activePipeline: pipeline, nodeStates: {} }),
  updateNode: (nodeId, state) => set((s) => ({
    nodeStates: { ...s.nodeStates, [nodeId]: { ...s.nodeStates[nodeId], ...state } as NodeState },
  })),
  setPipelineGraph: (graph) => set({ pipelineGraph: graph }),
  reset: () => set({ activeRunId: null, nodeStates: {}, pipelineGraph: null, activePipeline: null }),
}))
