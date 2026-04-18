export type AgentState = null | 'listening' | 'thinking' | 'talking'

export interface Opportunity {
  id: number
  ingredient: string
  unii: string | null
  grade_flag: string | null
  company_count: number
  score: number
  score_formula_component: number | null
  compliance_feasible: boolean | null
  proposal_text: string | null
}

export interface Ingredient {
  id: number
  display_name: string
  unii_code: string | null
  cas_number: string | null
  pubchem_cid: number | null
  smiles: string | null
  grade_flag: string | null
  match_score: number | null
  substitution_edges: number
}

export interface ComplianceRow {
  product_id: number
  company: string
  cert_type: string
  status: string
  cert_body: string | null
  off_market_warning: string | null
}

export interface Proposal {
  ingredient: string
  company_count: number
  score: number
  proposal_text: string
  compliance_feasible: boolean | null
  grade_flag: string | null
}

export interface PipelineRun {
  id: string
  pipeline_name: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  started_at: string
  error: string | null
}

export interface PipelineEvent {
  event_type: string
  node_id: string | null
  created_at: string
  error?: string
  node_output?: Record<string, unknown>
  _elapsed_ms?: number
}

export interface NodeState {
  state: 'pending' | 'started' | 'completed' | 'failed' | 'skipped'
  elapsed?: number
  error?: string
  output?: Record<string, unknown>
}

export interface PipelineGraph {
  name: string
  trigger: string
  layers: string[][]
  nodes: Array<{ id: string; class: string; type: string; when?: string }>
}

export const PIPELINE_COLORS: Record<string, [string, string]> = {
  supplier_fallout:        ['#FEB2B2', '#FC8181'],
  proactive_consolidation: ['#9AE6B4', '#68D391'],
  new_ingredient_research: ['#D6BCFA', '#B794F4'],
  price_audit:             ['#FAF089', '#F6E05E'],
  substitution_discovery:  ['#FBD38D', '#F6AD55'],
  default:                 ['#CADCFC', '#A0B9D1'],
}

export const NODE_STATUS_COLORS = {
  pending:   { ring: 'ring-slate-600',  icon: '—',  text: 'text-slate-400' },
  started:   { ring: 'ring-blue-400',   icon: '●',  text: 'text-blue-300', pulse: true },
  completed: { ring: 'ring-green-400',  icon: '✓',  text: 'text-green-300' },
  failed:    { ring: 'ring-red-500',    icon: '✗',  text: 'text-red-300' },
  skipped:   { ring: 'ring-amber-500',  icon: '⊘',  text: 'text-amber-400' },
}
