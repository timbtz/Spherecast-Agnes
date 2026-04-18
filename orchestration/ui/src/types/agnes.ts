// Domain types for the Agnes / Spherecast API surface.
export type Grade = "supplement" | "food" | "excipient" | "sweetener" | "flavor";

export interface Ingredient {
  id: string;
  display_name: string;
  unii?: string | null;
  cas?: string | null;
  pubchem_cid?: string | null;
  grade?: Grade | null;
  smiles?: string | null;
  substitution_edges?: number;
}

export interface Opportunity {
  id: string;
  ingredient_id: string;
  ingredient_name: string;
  grade?: Grade | null;
  company_count: number;
  consolidation_score: number; // 0..1
  compliance_feasible: boolean;
  proposal_text?: string | null;
}

export interface Proposal {
  id: string;
  ingredient_id: string;
  ingredient_name: string;
  grade?: Grade | null;
  consolidation_score: number;
  company_count: number;
  compliance_feasible: boolean;
  proposal_text: string;
  created_at: string;
}

export type CertStatus = "certified" | "implied" | "none";
export interface ComplianceProduct {
  product_id: string;
  product_name: string;
  company: string;
  off_market: boolean;
  certifications: Record<string, CertStatus>;
}

export type PipelineName =
  | "supplier_fallout"
  | "proactive_consolidation"
  | "new_ingredient_research"
  | "substitution_discovery"
  | "price_audit";

export type RunStatus = "running" | "completed" | "failed" | "queued";

export interface PipelineRun {
  run_id: string;
  pipeline: PipelineName | string;
  status: RunStatus;
  started_at: string;
  ended_at?: string | null;
  duration_ms?: number | null;
}

export type NodeStatus = "pending" | "running" | "completed" | "failed" | "skipped";
export type NodeType = "agent" | "tool";

export interface DagNode {
  id: string;
  type: NodeType;
  class?: string;
  depends_on: string[];
  when?: string | null;
}
export interface DagGraph {
  name: string;
  trigger: string;
  layers: string[][];
  nodes: DagNode[];
}

export interface RunEvent {
  event_type:
    | "node_started"
    | "node_completed"
    | "node_failed"
    | "node_skipped"
    | "pipeline_completed"
    | "pipeline_failed";
  node_id?: string;
  created_at: string;
  node_output?: Record<string, unknown> & { _elapsed_ms?: number };
  message?: string;
}

export interface RunDetail extends PipelineRun {
  events: RunEvent[];
}

export interface ChatResponse {
  run_id: string;
  pipeline: PipelineName | string;
  status: RunStatus;
  confidence?: number;
}
