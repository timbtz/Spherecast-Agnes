import { useRuns } from '@/hooks/useData'
import { PipelineBadge } from '@/components/PipelineBadge'
import type { PipelineRun } from '@/types/agnes'

const STATUS_STYLES: Record<string, string> = {
  completed: 'bg-green-900 text-green-300',
  running:   'bg-blue-900 text-blue-300 animate-pulse',
  failed:    'bg-red-900 text-red-300',
  pending:   'bg-slate-700 text-slate-300',
}

function SkeletonRow() {
  return (
    <div className="px-4 py-3 border-b border-slate-700">
      <div className="h-4 bg-slate-700 rounded animate-pulse mb-1" />
      <div className="h-3 w-32 bg-slate-800 rounded animate-pulse" />
    </div>
  )
}

export function RunsTab({ onSelectRun }: { onSelectRun?: (run: PipelineRun) => void }) {
  const { data, isLoading, error } = useRuns()

  if (isLoading) return <div>{Array.from({ length: 6 }).map((_, i) => <SkeletonRow key={i} />)}</div>
  if (error) return <p className="text-red-400 text-sm p-4">Failed to load runs</p>

  if (!data || data.runs.length === 0) {
    return <div className="py-20 text-center text-slate-500">No pipeline runs yet</div>
  }

  return (
    <div>
      <h2 className="text-lg font-semibold text-slate-100 mb-4">
        Pipeline Runs <span className="text-sm font-normal text-slate-400">({data.runs.length})</span>
      </h2>
      <div className="divide-y divide-slate-700">
        {data.runs.map(run => (
          <div
            key={run.id}
            className="px-4 py-3 hover:bg-slate-800 cursor-pointer flex items-center justify-between"
            onClick={() => onSelectRun?.(run)}
          >
            <div>
              <PipelineBadge pipeline={run.pipeline_name} />
              <div className="text-xs text-slate-500 mt-1">
                {run.id.slice(0, 8)}… · {run.started_at ? new Date(run.started_at).toLocaleTimeString() : ''}
              </div>
              {run.error && <div className="text-xs text-red-400 mt-1">{run.error}</div>}
            </div>
            <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_STYLES[run.status] ?? STATUS_STYLES.pending}`}>
              {run.status}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
