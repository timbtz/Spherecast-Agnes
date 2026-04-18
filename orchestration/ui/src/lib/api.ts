import type { Opportunity, Ingredient, ComplianceRow, Proposal, PipelineRun, PipelineGraph } from '@/types/agnes'

const BASE = import.meta.env.VITE_AGNES_API_URL ?? ''

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`)
  return res.json()
}

export const api = {
  getOpportunities: () =>
    fetchJSON<{ opportunities: Opportunity[]; count: number }>('/api/data/opportunities'),
  getIngredients: (grade?: string) =>
    fetchJSON<{ ingredients: Ingredient[] }>(`/api/data/ingredients${grade ? `?grade=${grade}` : ''}`),
  getCompliance: () =>
    fetchJSON<{ compliance: ComplianceRow[] }>('/api/data/compliance'),
  getProposals: () =>
    fetchJSON<{ proposals: Proposal[] }>('/api/data/proposals'),
  getPipelines: () =>
    fetchJSON<{ pipelines: string[] }>('/pipelines'),
  getRuns: (limit = 50) =>
    fetchJSON<{ runs: PipelineRun[] }>(`/runs?limit=${limit}`),
  getRun: (id: string) =>
    fetchJSON<PipelineRun & { events: Array<{ event_type: string; node_id: string | null; data: string }> }>(`/runs/${id}`),
  getPipelineGraph: (name: string) =>
    fetchJSON<PipelineGraph>(`/pipelines/${name}/graph`),
  chat: (message: string) =>
    fetchJSON<{ run_id: string; pipeline: string; status: string; confidence: number }>('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, user_id: 'voice-user' }),
    }),
  runPipeline: (name: string, params: Record<string, string>) =>
    fetchJSON<{ run_id: string }>(`/pipelines/run/${name}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ params }),
    }),
  getHealth: () =>
    fetchJSON<{ status: string }>('/health'),
}
