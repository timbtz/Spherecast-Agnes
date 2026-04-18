import type {
  ChatResponse,
  ComplianceProduct,
  DagGraph,
  Ingredient,
  Opportunity,
  PipelineName,
  PipelineRun,
  Proposal,
  RunDetail,
  RunEvent,
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

  listPipelines(): Promise<string[]> {
    return safeFetch<string[]>("/pipelines", undefined, [
      "supplier_fallout",
      "proactive_consolidation",
      "new_ingredient_research",
      "substitution_discovery",
      "price_audit",
    ]);
  },

  pipelineGraph(name: string): Promise<DagGraph> {
    return safeFetch<DagGraph>(`/pipelines/${name}/graph`, undefined, mockData.graph(name));
  },

  listRuns(): Promise<PipelineRun[]> {
    return safeFetch<PipelineRun[]>("/runs", undefined, mockData.runs());
  },

  runDetail(id: string): Promise<RunDetail> {
    return safeFetch<RunDetail>(`/runs/${id}`, undefined, mockData.runDetail(id));
  },

  opportunities(): Promise<Opportunity[]> {
    return safeFetch<Opportunity[]>("/api/data/opportunities", undefined, mockData.opportunities());
  },
  ingredients(grade?: string): Promise<Ingredient[]> {
    const q = grade ? `?grade=${encodeURIComponent(grade)}` : "";
    return safeFetch<Ingredient[]>(`/api/data/ingredients${q}`, undefined, mockData.ingredients(grade));
  },
  compliance(): Promise<ComplianceProduct[]> {
    return safeFetch<ComplianceProduct[]>("/api/data/compliance", undefined, mockData.compliance());
  },
  proposals(): Promise<Proposal[]> {
    return safeFetch<Proposal[]>("/api/data/proposals", undefined, mockData.proposals());
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
