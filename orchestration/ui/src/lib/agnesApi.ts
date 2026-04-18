import type {
  AlertCount,
  ChatResponse,
  Citation,
  ComplianceProduct,
  DagGraph,
  FdaLimit,
  Ingredient,
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
    return safeFetch<ScoringWeights>("/api/scoring/weights");
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
    });
  },

  async scoredSuppliers(ingredientId: number): Promise<{ ingredient_id: number; weights: ScoringWeights; suppliers: ScoredSupplier[]; count: number }> {
    return safeFetch(`/api/scoring/suppliers/${ingredientId}`);
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
