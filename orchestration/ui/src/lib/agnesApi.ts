import type {
  AlertCount,
  ChatResponse,
  Citation,
  ComplianceProduct,
  DagGraph,
  FdaLimit,
  Ingredient,
  Lane,
  Opportunity,
  PipelineName,
  PipelineRun,
  PriceAlert,
  Proposal,
  Refusal,
  RegulatoryAlert,
  RunDetail,
  RunEvent,
  ScoredSupplier,
  ScoringWeights,
} from "@/types/agnes";
import { mockData } from "./mockData";

const API_URL =
  (import.meta.env.VITE_AGNES_API_URL as string | undefined) ?? "http://localhost:8001";

export type Mode = "live" | "demo";

let mode: Mode = "live";
const listeners = new Set<(m: Mode) => void>();
export function getMode(): Mode {
  return mode;
}
export function setMode(m: Mode) {
  if (m !== mode) {
    mode = m;
    listeners.forEach((l) => l(m));
  }
}
export function onModeChange(cb: (m: Mode) => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

async function safeFetch<T>(path: string, init?: RequestInit, fallback?: T): Promise<T> {
  if (mode === "demo" && fallback !== undefined) return fallback;
  try {
    const res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return (await res.json()) as T;
  } catch (err) {
    if (fallback !== undefined) {
      // Auto-flip to demo on first network failure so the UI stays usable.
      if (mode === "live") setMode("demo");
      return fallback;
    }
    throw err;
  }
}

export const agnesApi = {
  apiUrl: API_URL,

  async health(): Promise<{ status: string }> {
    const res = await fetch(`${API_URL}/health`, { method: "GET" });
    if (!res.ok) throw new Error("offline");
    return res.json();
  },

  chat(text: string): Promise<ChatResponse> {
    if (mode === "demo") {
      return Promise.resolve(mockData.simulateChat(text));
    }
    return safeFetch<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify({ message: text }),
    }, mockData.simulateChat(text));
  },

  runPipeline(name: PipelineName): Promise<{ run_id: string }> {
    if (mode === "demo") return Promise.resolve({ run_id: mockData.newRunId(name) });
    return safeFetch(`/pipelines/run/${name}`, { method: "POST" }, { run_id: mockData.newRunId(name) });
  },

  async listPipelines(): Promise<string[]> {
    const res = await safeFetch<string[] | { pipelines: string[] }>("/pipelines", undefined, [
      "supplier_fallout",
      "proactive_consolidation",
      "new_ingredient_research",
      "substitution_discovery",
      "price_audit",
    ]);
    return Array.isArray(res) ? res : (res as { pipelines: string[] }).pipelines ?? [];
  },

  pipelineGraph(name: string): Promise<DagGraph> {
    return safeFetch<DagGraph>(`/pipelines/${name}/graph`, undefined, mockData.graph(name));
  },

  async listRuns(): Promise<PipelineRun[]> {
    const res = await safeFetch<PipelineRun[] | { runs: PipelineRun[] }>("/runs", undefined, mockData.runs());
    if (Array.isArray(res)) return res;
    const wrapped = res as { runs: PipelineRun[] };
    return (wrapped.runs ?? []).map((r) => ({
      ...r,
      run_id: r.run_id ?? (r as unknown as Record<string, string>).id,
      pipeline: (r as unknown as Record<string, string>).pipeline_name ?? r.pipeline,
      started_at: (r as unknown as Record<string, string>).started_at,
      duration_ms: (() => {
        const rr = r as unknown as Record<string, string | null>;
        if (rr.completed_at && rr.started_at) {
          return new Date(rr.completed_at).getTime() - new Date(rr.started_at).getTime();
        }
        return null;
      })(),
    }));
  },

  async runDetail(id: string): Promise<RunDetail> {
    const r = await safeFetch<Record<string, unknown>>(`/runs/${id}`, undefined, mockData.runDetail(id) as unknown as Record<string, unknown>);
    return {
      run_id: (r.run_id ?? r.id) as string,
      pipeline: (r.pipeline ?? r.pipeline_name) as string,
      status: r.status as RunDetail["status"],
      started_at: r.started_at as string,
      ended_at: (r.ended_at ?? r.completed_at ?? null) as string | null,
      duration_ms: r.duration_ms as number | null ?? (() => {
        if (r.completed_at && r.started_at) {
          return new Date(r.completed_at as string).getTime() - new Date(r.started_at as string).getTime();
        }
        return null;
      })(),
      events: (r.events as RunEvent[] | undefined) ?? [],
    };
  },

  async opportunities(): Promise<Opportunity[]> {
    const r = await safeFetch<{ opportunities: Opportunity[] } | Opportunity[]>("/api/data/opportunities", undefined, mockData.opportunities());
    return Array.isArray(r) ? r : (r as { opportunities: Opportunity[] }).opportunities ?? [];
  },
  async ingredients(grade?: string): Promise<Ingredient[]> {
    const q = grade ? `?grade=${encodeURIComponent(grade)}` : "";
    const r = await safeFetch<{ ingredients: Ingredient[] } | Ingredient[]>(`/api/data/ingredients${q}`, undefined, mockData.ingredients(grade));
    return Array.isArray(r) ? r : (r as { ingredients: Ingredient[] }).ingredients ?? [];
  },
  async compliance(): Promise<ComplianceProduct[]> {
    const r = await safeFetch<ComplianceProduct[] | { products: ComplianceProduct[] }>("/api/data/compliance", undefined, mockData.compliance());
    return Array.isArray(r) ? r : (r as { products: ComplianceProduct[] }).products ?? [];
  },
  async proposals(): Promise<Proposal[]> {
    const r = await safeFetch<{ proposals: Proposal[] } | Proposal[]>("/api/data/proposals", undefined, mockData.proposals());
    return Array.isArray(r) ? r : (r as { proposals: Proposal[] }).proposals ?? [];
  },

  async scoringWeights(): Promise<ScoringWeights> {
    return safeFetch<ScoringWeights>("/api/scoring/weights", undefined, { price: 3, lead_time: 3, quality: 3 });
  },

  async saveScoringWeights(weights: ScoringWeights): Promise<ScoringWeights> {
    return safeFetch<ScoringWeights>("/api/scoring/weights", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        price: weights.price,
        lead_time: weights.lead_time,
        quality: weights.quality,
      }),
    }, weights);
  },

  async scoredSuppliers(ingredientId: number): Promise<{ ingredient_id: number; weights: ScoringWeights; suppliers: ScoredSupplier[]; count: number }> {
    return safeFetch(`/api/scoring/suppliers/${ingredientId}`, undefined, {
      ingredient_id: ingredientId,
      weights: { price: 3, lead_time: 3, quality: 3 },
      count: MOCK_SUPPLIERS.length,
      suppliers: MOCK_SUPPLIERS,
    });
  },

  // TODO: wire to /api/data/lanes
  async lanes(): Promise<{ lanes: Lane[] }> {
    return safeFetch<{ lanes: Lane[] }>("/api/data/lanes", undefined, { lanes: MOCK_LANES });
  },

  async fdaLimits(ingredientId: number): Promise<{ ingredient_id: number; limits: FdaLimit[]; count: number }> {
    return safeFetch(`/api/data/fda-limits/${ingredientId}`);
  },

  async alertCount(): Promise<AlertCount> {
    return safeFetch<AlertCount>("/api/alerts/count");
  },

  async listAlerts(dismissed = false): Promise<{ alerts: PriceAlert[]; count: number }> {
    return safeFetch(`/api/alerts/?dismissed=${dismissed}`);
  },

  async dismissAlert(alertId: number): Promise<{ status: string }> {
    return safeFetch(`/api/alerts/${alertId}/dismiss`, { method: "POST" });
  },

  async regulatoryAlerts(): Promise<{ alerts: RegulatoryAlert[]; count: number }> {
    return safeFetch<{ alerts: RegulatoryAlert[]; count: number }>("/api/data/regulatory-alerts", undefined, { alerts: [], count: 0 });
  },

  async proposalCitations(opportunityId: string): Promise<{ citations: Citation[]; count: number }> {
    return safeFetch<{ citations: Citation[]; count: number }>(`/api/data/proposals/${opportunityId}/citations`, undefined, { citations: [], count: 0 });
  },

  async refusals(): Promise<{ refusals: Refusal[]; count: number }> {
    return safeFetch<{ refusals: Refusal[]; count: number }>("/api/data/refusals", undefined, { refusals: [], count: 0 });
  },

  // SSE — caller is responsible for closing

  streamRun(
    id: string,
    onEvent: (e: RunEvent) => void,
    onClose?: () => void,
  ): () => void {
    if (mode === "demo") {
      return mockData.simulateStream(id, onEvent, onClose);
    }
    const url = `${API_URL}/runs/${id}/stream`;
    let es: EventSource | null = null;
    try {
      es = new EventSource(url);
      es.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data);
          onEvent(data);
        } catch {
          /* ignore */
        }
      };
      es.onerror = () => {
        es?.close();
        onClose?.();
      };
    } catch {
      // Fall back to mock simulation
      return mockData.simulateStream(id, onEvent, onClose);
    }
    return () => {
      es?.close();
      onClose?.();
    };
  },
};

const MOCK_SUPPLIERS: ScoredSupplier[] = [
  {
    SupplierId: 1,
    supplier_name: "Lonza Group AG",
    Price_USD_Per_KG: 42.50,
    Lead_Time_Days: 21,
    MOQ_KG: 100,
    Purity_Pct: 99.5,
    Purity_Qualifier: "USP",
    Grade_Unverified: 0,
    Confidence: 0.92,
    Country_Origin: "CH",
    Country_Shipping: "CH",
    Price_Source: "vendor_portal",
    Price_Type: "contract",
    Last_Updated: "2026-03-15T00:00:00Z",
    price_score: 0.78,
    lead_time_score: 0.72,
    quality_score: 0.95,
    weighted_score: 0.83,
    provenance_confidence: "vendor_verified",
    corroboration_score: 5,
    url_health: "ok",
    vetted: true,
    url_archetype: "vendor_portal",
  },
  {
    SupplierId: 2,
    supplier_name: "DSM Nutritional Products",
    Price_USD_Per_KG: 38.00,
    Lead_Time_Days: 28,
    MOQ_KG: 500,
    Purity_Pct: 99.0,
    Purity_Qualifier: "FCC",
    Grade_Unverified: 0,
    Confidence: 0.87,
    Country_Origin: "NL",
    Country_Shipping: "NL",
    Price_Source: "google_search",
    Price_Type: "list",
    Last_Updated: "2026-02-20T00:00:00Z",
    price_score: 0.85,
    lead_time_score: 0.60,
    quality_score: 0.88,
    weighted_score: 0.79,
    provenance_confidence: "website_explicit",
    corroboration_score: 4,
    url_health: "ok",
    vetted: false,
    url_archetype: "manufacturer_website",
  },
  {
    SupplierId: 3,
    supplier_name: "Molport Catalog CN-447",
    Price_USD_Per_KG: 28.75,
    Lead_Time_Days: 45,
    MOQ_KG: 1000,
    Purity_Pct: 98.0,
    Purity_Qualifier: null,
    Grade_Unverified: 1,
    Confidence: 0.61,
    Country_Origin: "CN",
    Country_Shipping: "CN",
    Price_Source: "molport",
    Price_Type: "retail_proxy",
    Last_Updated: "2025-11-10T00:00:00Z",
    price_score: 0.96,
    lead_time_score: 0.35,
    quality_score: 0.58,
    weighted_score: 0.65,
    provenance_confidence: "directory_listing",
    corroboration_score: 2,
    url_health: "stale",
    vetted: false,
    url_archetype: "b2b_marketplace",
  },
  {
    SupplierId: 4,
    supplier_name: "Spec-Est Biotech",
    Price_USD_Per_KG: 51.20,
    Lead_Time_Days: 14,
    MOQ_KG: 25,
    Purity_Pct: 99.8,
    Purity_Qualifier: "Ph.Eur",
    Grade_Unverified: 0,
    Confidence: 0.55,
    Country_Origin: "DE",
    Country_Shipping: "DE",
    Price_Source: "google_search",
    Price_Type: "list",
    Last_Updated: "2026-01-05T00:00:00Z",
    price_score: 0.62,
    lead_time_score: 0.88,
    quality_score: 0.91,
    weighted_score: 0.76,
    provenance_confidence: "model_inferred",
    corroboration_score: 1,
    url_health: "unreachable",
    vetted: false,
    url_archetype: "ai_web_inference",
  },
  {
    SupplierId: 5,
    supplier_name: "Unknown Bulk Co.",
    Price_USD_Per_KG: 19.99,
    Lead_Time_Days: null,
    MOQ_KG: 2000,
    Purity_Pct: null,
    Purity_Qualifier: null,
    Grade_Unverified: 1,
    Confidence: 0.30,
    Country_Origin: null,
    Country_Shipping: null,
    Price_Source: null,
    Price_Type: null,
    Last_Updated: null,
    price_score: 0.99,
    lead_time_score: 0.20,
    quality_score: 0.15,
    weighted_score: 0.42,
    provenance_confidence: "unknown",
    corroboration_score: 0,
    url_health: "not_checked",
    vetted: false,
    url_archetype: null,
  },
];

const MOCK_LANES: Lane[] = [
  { origin: "CN", dest: "US", mode: "ocean", lead_time_days: 28, cost_usd_per_kg: 1.20 },
  { origin: "CN", dest: "US", mode: "air",   lead_time_days: 5,  cost_usd_per_kg: 4.80 },
  { origin: "CN", dest: "EU", mode: "ocean", lead_time_days: 22, cost_usd_per_kg: 1.05 },
  { origin: "IN", dest: "US", mode: "ocean", lead_time_days: 22, cost_usd_per_kg: 1.10 },
  { origin: "IN", dest: "EU", mode: "ocean", lead_time_days: 18, cost_usd_per_kg: 0.95 },
  { origin: "IN", dest: "US", mode: "air",   lead_time_days: 4,  cost_usd_per_kg: 3.90 },
  { origin: "DE", dest: "US", mode: "air",   lead_time_days: 3,  cost_usd_per_kg: 3.20 },
  { origin: "DE", dest: "EU", mode: "truck", lead_time_days: 4,  cost_usd_per_kg: 0.85 },
  { origin: "JP", dest: "US", mode: "ocean", lead_time_days: 18, cost_usd_per_kg: 1.35 },
  { origin: "JP", dest: "US", mode: "air",   lead_time_days: 3,  cost_usd_per_kg: 4.20 },
  { origin: "BR", dest: "US", mode: "ocean", lead_time_days: 15, cost_usd_per_kg: 0.90 },
  { origin: "CA", dest: "US", mode: "truck", lead_time_days: 2,  cost_usd_per_kg: 0.35 },
  { origin: "MX", dest: "US", mode: "truck", lead_time_days: 3,  cost_usd_per_kg: 0.45 },
  { origin: "CH", dest: "US", mode: "air",   lead_time_days: 3,  cost_usd_per_kg: 3.50 },
  { origin: "CH", dest: "EU", mode: "truck", lead_time_days: 2,  cost_usd_per_kg: 0.60 },
  { origin: "US", dest: "US", mode: "truck", lead_time_days: 1,  cost_usd_per_kg: 0.25 },
  { origin: "NL", dest: "EU", mode: "truck", lead_time_days: 3,  cost_usd_per_kg: 0.70 },
  { origin: "NL", dest: "US", mode: "ocean", lead_time_days: 10, cost_usd_per_kg: 0.80 },
];
