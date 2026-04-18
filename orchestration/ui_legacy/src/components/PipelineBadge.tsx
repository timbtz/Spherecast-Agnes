import { PIPELINE_COLORS } from '@/types/agnes'

export function PipelineBadge({ pipeline }: { pipeline: string }) {
  const [color] = PIPELINE_COLORS[pipeline] ?? PIPELINE_COLORS.default
  return (
    <span className="flex items-center gap-1 text-xs text-slate-400">
      <span style={{ color }} className="text-base">●</span>
      {pipeline.replace(/_/g, ' ')}
    </span>
  )
}
