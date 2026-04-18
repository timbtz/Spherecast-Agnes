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

export interface ScoringWeights {
  price: number;       // 1-5
  lead_time: number;   // 1-5
  quality: number;     // 1-5
}

export interface ScoredSupplier {
  SupplierId: number;
  supplier_name: string;
  Price_USD_Per_KG: number | null;
  Lead_Time_Days: number | null;
  MOQ_KG: number | null;
  Purity_Pct: number | null;
  Purity_Qualifier: string | null;
  Grade_Unverified: number;
  Confidence: number | null;
  Country_Origin: string | null;
  Country_Shipping: string | null;
  Price_Source: string | null;
  Price_Type: string | null;
  Last_Updated: string | null;
  price_score: number;
  lead_time_score: number;
  quality_score: number;
  weighted_score: number;
}

export interface FdaLimit {
  Route: string;
  DosageForm: string;
  MaxDailyExposure: number | null;
  MaxDailyExposureUnit: string | null;
}

export interface PriceAlert {
  Id: number;
  CanonicalIngredientId: number;
  SupplierId: number | null;
  Ingredient_Name: string;
  Supplier_Name: string | null;
  Previous_Price_USD: number | null;
  New_Price_USD: number | null;
  Change_Pct: number | null;
  Direction: "up" | "down";
  Severity: "info" | "warning" | "critical";
  Alert_Narrative: string | null;
  Dismissed: number;
  Detected_At: string;
  Run_Id: string | null;
}

export interface AlertCount {
  count: number;
}
