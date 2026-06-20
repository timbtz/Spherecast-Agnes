import type { PipelineEvent } from '@/types/agnes'

export function extractAnswer(events: PipelineEvent[]): string | null {
  for (const ev of [...events].reverse()) {
    if (ev.event_type === 'node_completed' && ev.node_output) {
      const out = ev.node_output
      if (out.proposal_text) return out.proposal_text as string
      if (out.proposals_narrative) return out.proposals_narrative as string
      if (out.summary) return out.summary as string
      const keys = Object.keys(out).filter(k => !k.startsWith('_'))
      if (keys.length > 0) return JSON.stringify(out[keys[0]], null, 2).slice(0, 500)
    }
  }
  return null
}
