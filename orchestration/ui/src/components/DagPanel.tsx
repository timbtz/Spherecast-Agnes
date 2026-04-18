import { useEffect, useState } from 'react'
import { useRunStore } from '@/store/runStore'
import { useRunStream } from '@/hooks/useRunStream'
import { usePipelines } from '@/hooks/useData'
import { NodeCard } from '@/components/NodeCard'
import { api } from '@/lib/api'
import type { PipelineEvent } from '@/types/agnes'

export function DagPanel() {
  const { activeRunId, activePipeline, pipelineGraph, nodeStates, setActiveRun, setPipelineGraph, updateNode } = useRunStore()
  const { data: pipelinesData } = usePipelines()
  const [selectedPipeline, setSelectedPipeline] = useState('')
  const [ingredient, setIngredient] = useState('')
  const [triggering, setTriggering] = useState(false)

  useRunStream(activeRunId)

  useEffect(() => {
    if (!activeRunId || !activePipeline) return
    api.getPipelineGraph(activePipeline).then(setPipelineGraph).catch(() => {})
    api.getRun(activeRunId).then(run => {
      ;(run.events ?? []).forEach((ev) => {
        const data = JSON.parse(ev.data || '{}') as PipelineEvent
        if (!ev.node_id) return
        if (ev.event_type === 'node_started') updateNode(ev.node_id, { state: 'started' })
        if (ev.event_type === 'node_completed') updateNode(ev.node_id, { state: 'completed', elapsed: data._elapsed_ms, output: data.node_output })
        if (ev.event_type === 'node_failed') updateNode(ev.node_id, { state: 'failed', error: data.error })
        if (ev.event_type === 'node_skipped') updateNode(ev.node_id, { state: 'skipped' })
      })
    }).catch(() => {})
  }, [activeRunId, activePipeline])

  async function trigger() {
    if (!selectedPipeline) return
    setTriggering(true)
    try {
      const params: Record<string, string> = ingredient ? { ingredient_name: ingredient } : {}
      const { run_id } = await api.runPipeline(selectedPipeline, params)
      setActiveRun(run_id, selectedPipeline)
    } catch (e) {
      console.error(e)
    } finally {
      setTriggering(false)
    }
  }

  const nodeMap = Object.fromEntries((pipelineGraph?.nodes ?? []).map(n => [n.id, n]))

  return (
    <div className="w-full">
      <div className="flex gap-2 mb-4 flex-wrap">
        <select
          value={selectedPipeline}
          onChange={e => setSelectedPipeline(e.target.value)}
          className="flex-1 bg-slate-700 border border-slate-600 text-slate-300 text-sm rounded px-2 py-1.5 min-w-0"
        >
          <option value="">Select pipeline…</option>
          {pipelinesData?.pipelines.map(p => <option key={p} value={p}>{p.replace(/_/g, ' ')}</option>)}
        </select>
        <input
          value={ingredient}
          onChange={e => setIngredient(e.target.value)}
          placeholder="ingredient (optional)"
          className="flex-1 bg-slate-700 border border-slate-600 text-slate-300 text-sm rounded px-2 py-1.5 min-w-0"
        />
        <button
          onClick={trigger}
          disabled={!selectedPipeline || triggering}
          className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm px-3 py-1.5 rounded"
        >
          {triggering ? '…' : 'Run'}
        </button>
      </div>

      {pipelineGraph && (
        <div className="overflow-x-auto">
          <div className="text-xs text-slate-400 mb-2">{pipelineGraph.name} · {pipelineGraph.nodes.length} nodes</div>
          <div className="flex gap-4 items-start pb-2">
            {pipelineGraph.layers.map((layer, li) => (
              <div key={li} className="flex items-start gap-4">
                <div className="flex flex-col gap-2">
                  {layer.map(nodeId => {
                    const node = nodeMap[nodeId]
                    const state = nodeStates[nodeId] ?? { state: 'pending' as const }
                    return node ? (
                      <NodeCard
                        key={nodeId}
                        nodeId={nodeId}
                        nodeClass={node.class}
                        nodeType={node.type}
                        when={node.when}
                        state={state}
                      />
                    ) : null
                  })}
                </div>
                {li < pipelineGraph.layers.length - 1 && (
                  <span className="text-slate-600 text-lg mt-4">→</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {!pipelineGraph && (
        <div className="text-xs text-slate-600 text-center py-4">
          Select a pipeline and click Run, or select a run from the Runs tab.
        </div>
      )}
    </div>
  )
}
