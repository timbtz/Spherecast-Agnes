import { useEffect } from 'react'
import { useRunStore } from '@/store/runStore'
import type { PipelineEvent } from '@/types/agnes'

export function useRunStream(runId: string | null) {
  const { updateNode } = useRunStore()
  useEffect(() => {
    if (!runId) return
    const base = import.meta.env.VITE_AGNES_API_URL ?? ''
    const es = new EventSource(`${base}/runs/${runId}/stream`)
    es.onmessage = (e) => {
      const ev = JSON.parse(e.data) as PipelineEvent
      if (!ev.node_id) return
      if (ev.event_type === 'node_started') updateNode(ev.node_id, { state: 'started' })
      if (ev.event_type === 'node_completed') updateNode(ev.node_id, { state: 'completed', elapsed: ev._elapsed_ms, output: ev.node_output })
      if (ev.event_type === 'node_failed') updateNode(ev.node_id, { state: 'failed', error: ev.error })
      if (ev.event_type === 'node_skipped') updateNode(ev.node_id, { state: 'skipped' })
      if (ev.event_type === 'stream_closed') es.close()
    }
    es.onerror = () => {}
    return () => es.close()
  }, [runId, updateNode])
}
