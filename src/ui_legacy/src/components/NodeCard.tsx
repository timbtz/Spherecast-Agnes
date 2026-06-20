import { useState } from 'react'
import { NODE_STATUS_COLORS } from '@/types/agnes'
import type { NodeState } from '@/types/agnes'

interface NodeCardProps {
  nodeId: string
  nodeClass: string
  nodeType: string
  when?: string
  state: NodeState
}

export function NodeCard({ nodeId, nodeClass, nodeType, when, state }: NodeCardProps) {
  const [expanded, setExpanded] = useState(false)
  const colors = NODE_STATUS_COLORS[state.state]
  const isPulse = state.state === 'started'

  return (
    <div
      className={`min-w-[140px] p-3 rounded-lg bg-slate-800 border-2 ring-2 ${colors.ring} border-transparent cursor-pointer ${isPulse ? 'animate-pulse' : ''}`}
      onClick={() => state.output && setExpanded(!expanded)}
    >
      <div className={`flex items-center gap-1.5 ${colors.text} font-semibold text-sm`}>
        <span>{colors.icon}</span>
        <span className="truncate">{nodeId}</span>
      </div>
      <div className="text-xs text-slate-500 mt-0.5 truncate">{nodeClass}</div>
      <span className={`inline-block mt-1 text-xs px-1.5 py-0.5 rounded ${nodeType === 'tool' ? 'bg-blue-900 text-blue-300' : 'bg-purple-900 text-purple-300'}`}>
        {nodeType}
      </span>
      {when && <div className="text-xs text-amber-400 mt-1 truncate">when: {when}</div>}
      {state.elapsed && <div className="text-xs text-green-400 mt-1">✓ {state.elapsed}ms</div>}
      {state.error && <div className="text-xs text-red-400 mt-1 truncate">{state.error}</div>}
      {expanded && state.output && (
        <pre className="mt-2 text-xs bg-slate-900 p-2 rounded overflow-x-auto max-h-32 text-slate-300 whitespace-pre-wrap">
          {JSON.stringify(state.output, null, 2).slice(0, 500)}
        </pre>
      )}
    </div>
  )
}
