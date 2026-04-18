# Feature: Agnes UI — Voice Dashboard & Data Explorer

The following plan should be complete, but validate documentation and codebase patterns before implementing. Pay special attention to **actual SQLite column names** — several differ from what the PRD specifies.

## Feature Description

Build a Vite + React 18 + TypeScript single-page application that serves as Agnes's decision-support dashboard. It features an ElevenLabs WebGL Orb voice interface at center, a live DAG pipeline monitor with SSE streaming, and a 5-tab data explorer backed by `db_enriched.sqlite`. The app is served as a static build from the existing FastAPI server at `/ui`.

## User Story

As a procurement analyst,
I want to speak supply chain questions to Agnes and see live pipeline execution,
So that I can quickly find consolidation opportunities and trace every reasoning step.

## Problem Statement

The current UI (`orchestration/ui/index.html`) is a 189-line vanilla JS pipeline monitor with no voice interface, no data exploration, and no proposal review. The data pipeline is complete with 129 scored consolidation opportunities; there is no way to browse or act on them without querying SQLite directly.

## Solution Statement

Replace the vanilla JS monitor with a full Vite+React SPA that wraps the ElevenLabs Orb for voice, upgrades the DAG panel to React components with Zustand state, and adds a 5-tab data explorer consuming new FastAPI data endpoints.

## Feature Metadata

**Feature Type**: New Capability  
**Estimated Complexity**: High  
**Primary Systems Affected**: orchestration/api, orchestration/ui  
**Dependencies**: Vite 5, React 18, TypeScript 5, Tailwind 3, Zustand 4, @tanstack/react-query 5, Three.js, @react-three/fiber, @react-three/drei, @elevenlabs/cli (Orb component)

---

## CRITICAL SCHEMA CORRECTIONS

> **The PRD SQL queries contain column name errors. Use these corrected names.**

| PRD Says | Actual Column | Table |
|---|---|---|
| `co.Score` | `co.Consolidation_Score` | `Consolidation_Opportunity` |
| `ic.DisplayName` | `ic.Name` | `Ingredient_Canonical` |
| `Finished_Good` | `Product` | (table name) |
| `pc.cert_type` | `pc.Certification` | `Product_Compliance` |

**Current data state (2026-04-18):**
- `Consolidation_Opportunity`: 129 rows scored; **Proposal_Text = NULL for all** (needs ANTHROPIC_API_KEY)
- `Ingredient_Canonical`: 250 rows; SMILES 50%, UNII 54%, Grade_Flag populated
- `Product_Compliance`: 126 rows; 66 products
- `Ingredient_Substitution`: 30 edges
- Top opportunity: CanonicalIngredientId=10, Company_Count=33, Consolidation_Score=0.8929

**Company JOIN chain for compliance:** `Product_Compliance.ProductId → Product.Id → Product.CompanyId → Company.Name`

---

## REFERENCE IMAGES & VISUAL DESIGN

No external image files are linked in the PRD. Visual design references come from the ElevenLabs documentation:

- **ElevenLabs UI Docs**: https://ui.elevenlabs.io/docs/components/orb — visual demos of the orb's 4 states (idle/listening/thinking/talking)
- **ElevenLabs UI GitHub**: https://github.com/elevenlabs/ui — Orb source repository
- **ElevenLabs Blog**: https://elevenlabs.io/blog/elevenlabs-ui — screenshots of the orb in context

**Visual summary**: The Orb is a dark circular container (~192×192px) with a WebGL 3D sphere inside. The sphere uses custom GLSL shaders with gradient colors that pulse in sync with audio. In idle state it undulates slowly; in listening it pulses with mic input; in thinking it shows complex shader patterns; in talking it pulses with TTS audio output.

**Orb container pattern** (from `REF-ELEVENLABS-ORB-UI.md`):
```tsx
<div className="relative h-48 w-48 rounded-full p-2 bg-[#0f1117]
    shadow-[inset_0_2px_12px_rgba(0,0,0,0.6)] cursor-pointer">
  <div className="h-full w-full overflow-hidden rounded-full">
    <Orb colors={colors} agentState={agentState} seed={42}
         inputVolumeRef={inputVolRef} outputVolumeRef={outputVolRef} />
  </div>
</div>
```

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ BEFORE IMPLEMENTING

- `orchestration/api/main.py` (full file) — FastAPI app; currently mounts `orchestration/ui/` directly (not `/dist`); must update mount point after Vite build
- `orchestration/api/routes/chat.py` — POST /chat endpoint; returns `{run_id, pipeline, params, confidence, reasoning, status}`
- `orchestration/api/routes/pipelines.py` — all pipeline + run endpoints; SSE at `/runs/{run_id}/stream`
- `orchestration/ui/index.html` (full file) — existing vanilla JS monitor to replace; study `selectRun()` and `renderDag()` for SSE patterns
- `Orchestration/References/Tech/General/REF-ELEVENLABS-ORB-UI.md` — Orb props, audio volume wiring patterns A/B/C, container HTML
- `Orchestration/References/Tech/Orchestration/REF-ELEVENLABS-VOICE-PIPELINE-INTEGRATION.md` — complete `useAgnesVoice` hook (§1.6), `AgnesVoiceOrb` component (§1.7), TTS pattern (§1.2), STT pattern (§1.3), SSE consumption (§1.4), `extractAnswer()` (§1.5)
- `Orchestration/References/Tech/Orchestration/REF-DAG-CANVAS-ALPINEJS.md` — DAG layout patterns, STATUS_COLORS scheme, node state machine (adapt from Alpine.js to React/Zustand)
- `Orchestration/References/Tech/General/REF-SSE-STREAMING-FASTAPI.md` — SSE event types, wire format, reconnect behavior
- `schema/enriched_schema.sql` — full v1.1 DDL (authoritative source for all column names)

### New Files to Create

**Backend:**
- `orchestration/api/routes/data.py` — 4 new read-only endpoints

**Frontend (Vite project root: `orchestration/ui/`):**
- `orchestration/ui/package.json`
- `orchestration/ui/vite.config.ts`
- `orchestration/ui/tailwind.config.ts`
- `orchestration/ui/tsconfig.json`
- `orchestration/ui/index.html`
- `orchestration/ui/src/main.tsx`
- `orchestration/ui/src/App.tsx`
- `orchestration/ui/src/types/agnes.ts`
- `orchestration/ui/src/lib/api.ts`
- `orchestration/ui/src/lib/extractAnswer.ts`
- `orchestration/ui/src/store/runStore.ts`
- `orchestration/ui/src/hooks/useAgnesVoice.ts`
- `orchestration/ui/src/hooks/useRunStream.ts`
- `orchestration/ui/src/hooks/useData.ts`
- `orchestration/ui/src/components/ui/orb.tsx` (CLI-installed)
- `orchestration/ui/src/components/VoiceOrb.tsx`
- `orchestration/ui/src/components/DagPanel.tsx`
- `orchestration/ui/src/components/NodeCard.tsx`
- `orchestration/ui/src/components/ConfidenceBar.tsx`
- `orchestration/ui/src/components/PipelineBadge.tsx`
- `orchestration/ui/src/components/DataExplorer.tsx`
- `orchestration/ui/src/components/tabs/OpportunitiesTab.tsx`
- `orchestration/ui/src/components/tabs/IngredientsTab.tsx`
- `orchestration/ui/src/components/tabs/ComplianceTab.tsx`
- `orchestration/ui/src/components/tabs/ProposalsTab.tsx`
- `orchestration/ui/src/components/tabs/RunsTab.tsx`
- `orchestration/ui/src/env.d.ts`
- `orchestration/ui/.env`

### Relevant Documentation — READ BEFORE IMPLEMENTING

- [ElevenLabs Orb UI Docs](https://ui.elevenlabs.io/docs/components/orb)
  - Orb props, installation, visual state demos
  - Why: Canonical source for orb.tsx props that will be installed via CLI
- [ElevenLabs TTS API](https://elevenlabs.io/docs/api-reference/text-to-speech)
  - POST /v1/text-to-speech/{voiceId}/stream endpoint
  - Why: TTS synthesis in `useAgnesVoice.ts`
- [Zustand Docs](https://zustand.pmnd.rs/)
  - `create()` with TypeScript, `devtools` middleware
  - Why: `runStore.ts` pattern
- [TanStack Query v5](https://tanstack.com/query/v5/docs/react/overview)
  - `useQuery` hook signature (changed from v4)
  - Why: All data fetch hooks in `useData.ts`
- [Vite Proxy Config](https://vitejs.dev/config/server-options#server-proxy)
  - `server.proxy` option for `/api` → localhost:8000
  - Why: Dev-mode API calls without CORS issues

### Patterns to Follow

**Naming Conventions:**
- Components: PascalCase (`VoiceOrb.tsx`, `DagPanel.tsx`)
- Hooks: camelCase prefixed with `use` (`useAgnesVoice`, `useRunStream`)
- Types: PascalCase in `types/agnes.ts`
- API functions: camelCase in `lib/api.ts`
- CSS: Tailwind utility classes only; no CSS modules

**State Management:**
```typescript
// runStore.ts — Zustand pattern
import { create } from 'zustand'

interface RunStore {
  activeRunId: string | null
  nodeStates: Record<string, NodeState>
  pipelineGraph: PipelineGraph | null
  setActiveRun: (runId: string) => void
  updateNode: (nodeId: string, state: Partial<NodeState>) => void
  setPipelineGraph: (graph: PipelineGraph) => void
  reset: () => void
}
```

**SSE Hook Pattern** (from `REF-ELEVENLABS-VOICE-PIPELINE-INTEGRATION.md §1.4`):
```typescript
// useRunStream.ts
useEffect(() => {
  if (!runId) return
  const es = new EventSource(`${API_BASE}/runs/${runId}/stream`)
  es.onmessage = (e) => {
    const event = JSON.parse(e.data) as PipelineEvent
    // dispatch to runStore
    if (event.event_type === 'stream_closed') es.close()
  }
  return () => es.close()
}, [runId])
```

**React Query Pattern:**
```typescript
// useData.ts
export function useOpportunities() {
  return useQuery({
    queryKey: ['opportunities'],
    queryFn: () => api.getOpportunities(),
    staleTime: 30_000,
  })
}
```

**Pipeline Color Map** (from PRD §6):
```typescript
export const PIPELINE_COLORS: Record<string, [string, string]> = {
  supplier_fallout:        ["#FEB2B2", "#FC8181"],
  proactive_consolidation: ["#9AE6B4", "#68D391"],
  new_ingredient_research: ["#D6BCFA", "#B794F4"],
  price_audit:             ["#FAF089", "#F6E05E"],
  substitution_discovery:  ["#FBD38D", "#F6AD55"],
  default:                 ["#CADCFC", "#A0B9D1"],
}
```

**Node State Color Scheme** (from `REF-DAG-CANVAS-ALPINEJS.md §7`):
```typescript
export const NODE_STATUS_COLORS = {
  pending:   { ring: 'ring-slate-600',  icon: '—',  text: 'text-slate-400' },
  started:   { ring: 'ring-blue-400',   icon: '●',  text: 'text-blue-300', pulse: true },
  completed: { ring: 'ring-green-400',  icon: '✓',  text: 'text-green-300' },
  failed:    { ring: 'ring-red-500',    icon: '✗',  text: 'text-red-300' },
  skipped:   { ring: 'ring-amber-500',  icon: '⊘',  text: 'text-amber-400' },
}
```

---

## IMPLEMENTATION PLAN

### Phase 1: FastAPI Data Endpoints + Vite Scaffold

**Goal:** Backend API ready; Vite project boots; no hardcoded data.

#### Task 1.1 — CREATE `orchestration/api/routes/data.py`

- **IMPLEMENT**: 4 read-only endpoints querying `db_enriched.sqlite`
- **GOTCHA**: `Consolidation_Opportunity` uses column `Consolidation_Score` NOT `Score`; `Ingredient_Canonical` uses `Name` NOT `DisplayName`; `Product_Compliance.Certification` NOT `cert_type`; `Finished_Good` table does not exist — use `Product JOIN Company`
- **GOTCHA**: Open `db_enriched.sqlite` in read-only mode with WAL: `sqlite3.connect(path, uri=True)` with `?mode=ro`
- **PATTERN**: Follow `orchestration/api/routes/chat.py` for router/response model structure

```python
import sqlite3
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/data", tags=["data"])

_DB = Path(__file__).parent.parent.parent.parent / "db_enriched.sqlite"

def get_db():
    conn = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

@router.get("/opportunities")
def opportunities():
    with get_db() as db:
        rows = db.execute("""
            SELECT co.Id as id, ic.Name as ingredient, ic.UNII_Code as unii,
                   ic.Grade_Flag as grade_flag, co.Company_Count as company_count,
                   co.Consolidation_Score as score,
                   co.Score_Formula_Component as score_formula_component,
                   co.Compliance_Feasible as compliance_feasible,
                   co.Proposal_Text as proposal_text
            FROM Consolidation_Opportunity co
            JOIN Ingredient_Canonical ic ON ic.Id = co.CanonicalIngredientId
            ORDER BY co.Consolidation_Score DESC
        """).fetchall()
    return {"opportunities": [dict(r) for r in rows], "count": len(rows)}

@router.get("/ingredients")
def ingredients(grade: str | None = None):
    with get_db() as db:
        query = """
            SELECT ic.Id as id, ic.Name as display_name, ic.UNII_Code as unii_code,
                   ic.CAS_Number as cas_number, ic.PubChem_CID as pubchem_cid,
                   ic.SMILES as smiles, ic.Grade_Flag as grade_flag,
                   ic.Confidence as match_score,
                   COUNT(DISTINCT s.IngredientBId) + COUNT(DISTINCT s.IngredientAId) as substitution_edges
            FROM Ingredient_Canonical ic
            LEFT JOIN Ingredient_Substitution s ON s.IngredientAId = ic.Id OR s.IngredientBId = ic.Id
        """
        params = []
        if grade:
            query += " WHERE ic.Grade_Flag = ?"
            params.append(grade)
        query += " GROUP BY ic.Id ORDER BY ic.Name"
        rows = db.execute(query, params).fetchall()
    return {"ingredients": [dict(r) for r in rows]}

@router.get("/compliance")
def compliance():
    with get_db() as db:
        rows = db.execute("""
            SELECT pc.ProductId as product_id, c.Name as company,
                   pc.Certification as cert_type, pc.Status as status,
                   pc.Source as cert_body, pc.Off_Market_Warning as off_market_warning
            FROM Product_Compliance pc
            JOIN Product p ON p.Id = pc.ProductId
            JOIN Company c ON c.Id = p.CompanyId
            ORDER BY c.Name, pc.Certification
        """).fetchall()
    return {"compliance": [dict(r) for r in rows]}

@router.get("/proposals")
def proposals():
    with get_db() as db:
        rows = db.execute("""
            SELECT ic.Name as ingredient, co.Company_Count as company_count,
                   co.Consolidation_Score as score, co.Proposal_Text as proposal_text,
                   co.Compliance_Feasible as compliance_feasible, ic.Grade_Flag as grade_flag
            FROM Consolidation_Opportunity co
            JOIN Ingredient_Canonical ic ON ic.Id = co.CanonicalIngredientId
            WHERE co.Proposal_Text IS NOT NULL
            ORDER BY co.Consolidation_Score DESC
        """).fetchall()
    return {"proposals": [dict(r) for r in rows]}
```

- **VALIDATE**: `curl http://localhost:8000/api/data/opportunities | python3 -m json.tool | head -30`

#### Task 1.2 — UPDATE `orchestration/api/main.py`

- **ADD**: `from orchestration.api.routes import data` import and `app.include_router(data.router)`
- **ADD**: `"Last-Event-ID"` to `allow_headers` in CORSMiddleware (required for SSE reconnect)
- **UPDATE**: Static files mount to serve from `dist/` after build:
```python
_UI_DIST = Path(__file__).parent.parent / "ui" / "dist"
_UI_DEV  = Path(__file__).parent.parent / "ui"
_SERVE   = _UI_DIST if _UI_DIST.exists() else _UI_DEV
if _SERVE.exists():
    app.mount("/ui", StaticFiles(directory=str(_SERVE), html=True), name="ui")
```
- **VALIDATE**: `curl http://localhost:8000/api/data/opportunities` returns 200 with `count: 129`

#### Task 1.3 — CREATE Vite project scaffold in `orchestration/ui/`

- **NOTE**: The existing `index.html` at `orchestration/ui/index.html` must be **backed up** first (rename to `index.html.bak`), then Vite will replace it
- **IMPLEMENT**: Initialize Vite+React+TS project

```bash
cd orchestration/ui
mv index.html index.html.bak
pnpm create vite . --template react-ts
pnpm add -D tailwindcss postcss autoprefixer
pnpm add zustand @tanstack/react-query
pnpm dlx tailwindcss init -p
pnpm install
```

- **CREATE** `orchestration/ui/.env`:
```
VITE_ELEVENLABS_API_KEY=sk-...
VITE_ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
VITE_AGNES_API_URL=http://localhost:8000
```

- **CREATE** `orchestration/ui/src/env.d.ts`:
```typescript
/// <reference types="vite/client" />
interface ImportMetaEnv {
  readonly VITE_ELEVENLABS_API_KEY: string
  readonly VITE_ELEVENLABS_VOICE_ID: string
  readonly VITE_AGNES_API_URL: string
}
```

- **CREATE** `orchestration/ui/vite.config.ts`:
```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: { aliases: { '@': path.resolve(__dirname, './src') } },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/chat': 'http://localhost:8000',
      '/pipelines': 'http://localhost:8000',
      '/runs': 'http://localhost:8000',
      '/proposals': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
  build: { outDir: 'dist' },
})
```

- **UPDATE** `orchestration/ui/tailwind.config.ts`:
```typescript
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: { extend: {} },
  plugins: [],
}
```

- **VALIDATE**: `cd orchestration/ui && pnpm dev` → browser shows Vite default page at `http://localhost:5173`

#### Task 1.4 — CREATE `orchestration/ui/src/types/agnes.ts`

All shared TypeScript types. Define all interfaces here; import from `@/types/agnes`.

```typescript
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
```

- **VALIDATE**: `cd orchestration/ui && pnpm tsc --noEmit` — zero errors

#### Task 1.5 — CREATE `orchestration/ui/src/lib/api.ts`

Typed fetch wrappers for all endpoints.

```typescript
const BASE = import.meta.env.VITE_AGNES_API_URL ?? ''

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`)
  return res.json()
}

export const api = {
  getOpportunities: () => fetchJSON<{ opportunities: Opportunity[]; count: number }>('/api/data/opportunities'),
  getIngredients: (grade?: string) => fetchJSON<{ ingredients: Ingredient[] }>(`/api/data/ingredients${grade ? `?grade=${grade}` : ''}`),
  getCompliance: () => fetchJSON<{ compliance: ComplianceRow[] }>('/api/data/compliance'),
  getProposals: () => fetchJSON<{ proposals: Proposal[] }>('/api/data/proposals'),
  getPipelines: () => fetchJSON<{ pipelines: string[] }>('/pipelines'),
  getRuns: (limit = 50) => fetchJSON<{ runs: PipelineRun[] }>(`/runs?limit=${limit}`),
  getRun: (id: string) => fetchJSON<PipelineRun & { events: any[] }>(`/runs/${id}`),
  getPipelineGraph: (name: string) => fetchJSON<PipelineGraph>(`/pipelines/${name}/graph`),
  chat: (message: string) => fetchJSON<{ run_id: string; pipeline: string; status: string; confidence: number }>('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, user_id: 'voice-user' }),
  }),
  runPipeline: (name: string, params: Record<string, string>) => fetchJSON<{ run_id: string }>(`/pipelines/run/${name}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ params }),
  }),
  getHealth: () => fetchJSON<{ status: string }>('/health'),
}
```

- **VALIDATE**: `pnpm tsc --noEmit` — zero errors

---

### Phase 2: Data Explorer Tabs

**Goal:** All 5 data tabs showing real SQLite data.

#### Task 2.1 — CREATE `orchestration/ui/src/hooks/useData.ts`

```typescript
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export const useOpportunities = () =>
  useQuery({ queryKey: ['opportunities'], queryFn: () => api.getOpportunities(), staleTime: 30_000 })

export const useIngredients = (grade?: string) =>
  useQuery({ queryKey: ['ingredients', grade], queryFn: () => api.getIngredients(grade), staleTime: 30_000 })

export const useCompliance = () =>
  useQuery({ queryKey: ['compliance'], queryFn: () => api.getCompliance(), staleTime: 30_000 })

export const useProposals = () =>
  useQuery({ queryKey: ['proposals'], queryFn: () => api.getProposals(), staleTime: 30_000 })

export const useRuns = () =>
  useQuery({ queryKey: ['runs'], queryFn: () => api.getRuns(), staleTime: 5_000, refetchInterval: 10_000 })

export const usePipelines = () =>
  useQuery({ queryKey: ['pipelines'], queryFn: () => api.getPipelines(), staleTime: 60_000 })

export const useHealth = () =>
  useQuery({ queryKey: ['health'], queryFn: () => api.getHealth(), refetchInterval: 30_000 })
```

#### Task 2.2 — CREATE `orchestration/ui/src/components/ConfidenceBar.tsx`

- **IMPLEMENT**: Score progress bar, green→yellow→red by bucket
```tsx
export function ConfidenceBar({ value, max = 1 }: { value: number; max?: number }) {
  const pct = Math.round((value / max) * 100)
  const color = pct >= 70 ? 'bg-green-500' : pct >= 40 ? 'bg-yellow-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 rounded-full bg-slate-700">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-slate-400">{value.toFixed(3)}</span>
    </div>
  )
}
```

#### Task 2.3 — CREATE `orchestration/ui/src/components/tabs/OpportunitiesTab.tsx`

- **IMPLEMENT**: Sortable table — columns: Rank, Ingredient, Companies, Score bar, BOM Coverage, Proposal Preview
- **IMPLEMENT**: Click row → expand to full Proposal_Text (or show "No proposal generated yet" if null)
- **GOTCHA**: `Proposal_Text` is NULL for all rows currently — empty state is critical
- **PATTERN**: Loading skeleton with `data?.opportunities ?? []`
- **SORT**: By Consolidation_Score DESC by default; allow toggle by Company_Count
- **VALIDATE**: Browser shows 129 rows sorted by score; top row is "Vitamin C" (or whichever ingredient has CanonicalIngredientId=10, Company_Count=33, Score=0.8929)

#### Task 2.4 — CREATE `orchestration/ui/src/components/tabs/IngredientsTab.tsx`

- **IMPLEMENT**: Filterable table by Grade_Flag (supplement/food/excipient/sweetener/flavor/unknown)
- **IMPLEMENT**: Slide-over panel on row click showing: full SMILES, all substitution pairs, PubChem CID, company usage count
- **GOTCHA**: SMILES can be very long (~80 chars) — truncate to 20 chars in table, show full in slide-over
- **VALIDATE**: Filter by "supplement" shows only supplement-grade ingredients; slide-over shows SMILES

#### Task 2.5 — CREATE `orchestration/ui/src/components/tabs/ComplianceTab.tsx`

- **IMPLEMENT**: Grid view — products as rows, cert types as columns, ✓/✗ cells
- **IMPLEMENT**: Filter by cert type
- **GOTCHA**: JOIN path is `Product_Compliance → Product → Company` (no `Finished_Good` table)
- **VALIDATE**: Grid shows 66 products with NSF/USP/Kosher/etc. columns

#### Task 2.6 — CREATE `orchestration/ui/src/components/tabs/ProposalsTab.tsx`

- **IMPLEMENT**: Card list per proposal; **empty state required** ("No proposals generated yet — run a pipeline with ANTHROPIC_API_KEY configured")
- **IMPLEMENT**: "Speak this" button per card → calls `onSpeak(proposal_text)` callback prop
- **VALIDATE**: Empty state message shows (0 proposals currently)

#### Task 2.7 — CREATE `orchestration/ui/src/components/tabs/RunsTab.tsx`

- **IMPLEMENT**: Run list with status badges (pending=slate, running=blue pulse, completed=green, failed=red)
- **IMPLEMENT**: Click row → call `onSelectRun(run)` callback to load DAG panel
- **VALIDATE**: Shows runs from orchestration.db; clicking triggers DAG load

#### Task 2.8 — CREATE `orchestration/ui/src/components/DataExplorer.tsx`

- **IMPLEMENT**: Tab shell with 5 tabs: Opportunities, Ingredients, Compliance, Proposals, Runs
- **PATTERN**: Simple state-driven tab switching with `useState<string>('opportunities')`
- **VALIDATE**: Tab switching shows correct content; all tabs load data

---

### Phase 3: DAG Panel + Run Streaming

**Goal:** Live pipeline execution visible; historical replays work.

#### Task 3.1 — CREATE `orchestration/ui/src/store/runStore.ts`

```typescript
import { create } from 'zustand'
import type { NodeState, PipelineGraph } from '@/types/agnes'

interface RunStore {
  activeRunId: string | null
  nodeStates: Record<string, NodeState>
  pipelineGraph: PipelineGraph | null
  activePipeline: string | null
  setActiveRun: (runId: string, pipeline: string) => void
  updateNode: (nodeId: string, state: Partial<NodeState>) => void
  setPipelineGraph: (graph: PipelineGraph) => void
  reset: () => void
}

export const useRunStore = create<RunStore>((set) => ({
  activeRunId: null,
  nodeStates: {},
  pipelineGraph: null,
  activePipeline: null,
  setActiveRun: (runId, pipeline) => set({ activeRunId: runId, activePipeline: pipeline, nodeStates: {} }),
  updateNode: (nodeId, state) => set((s) => ({
    nodeStates: { ...s.nodeStates, [nodeId]: { ...s.nodeStates[nodeId], ...state } },
  })),
  setPipelineGraph: (graph) => set({ pipelineGraph: graph }),
  reset: () => set({ activeRunId: null, nodeStates: {}, pipelineGraph: null, activePipeline: null }),
}))
```

#### Task 3.2 — CREATE `orchestration/ui/src/hooks/useRunStream.ts`

- **IMPLEMENT**: EventSource subscription; dispatch events to `runStore`
- **PATTERN**: From `REF-ELEVENLABS-VOICE-PIPELINE-INTEGRATION.md §1.4` and existing `index.html selectRun()`
- **GOTCHA**: Subscribe to `/runs/{runId}/stream` NOT `/pipeline/stream/{runId}` (Agnes uses different path than HappyRobot)

```typescript
import { useEffect } from 'react'
import { useRunStore } from '@/store/runStore'
import type { PipelineEvent } from '@/types/agnes'

export function useRunStream(runId: string | null) {
  const { updateNode } = useRunStore()
  useEffect(() => {
    if (!runId) return
    const es = new EventSource(`/runs/${runId}/stream`)
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
```

#### Task 3.3 — CREATE `orchestration/ui/src/components/NodeCard.tsx`

- **IMPLEMENT**: Card with state ring color, icon, elapsed time, error message
- **IMPLEMENT**: Click to expand `node_output` JSON in collapsible `<pre>`
- **PATTERN**: `NODE_STATUS_COLORS` from patterns section above
- **VALIDATE**: Completed node shows green ring + ✓ + elapsed ms; failed shows red + error

#### Task 3.4 — CREATE `orchestration/ui/src/components/DagPanel.tsx`

- **IMPLEMENT**: Horizontal layer layout (flex row with → separators)
- **IMPLEMENT**: Load `pipelineGraph` via `GET /pipelines/{name}/graph`; render NodeCards from layers
- **IMPLEMENT**: Historical event replay: fetch `GET /runs/{id}` events and apply to nodeStates
- **IMPLEMENT**: Manual trigger form: pipeline select + ingredient input + Run button
- **GOTCHA**: The `layers` field from `/pipelines/{name}/graph` is `string[][]` (array of arrays of node IDs)
- **VALIDATE**: Trigger supplier_fallout; watch nodes complete; click completed node shows JSON output

---

### Phase 4: ElevenLabs Orb + Voice Integration

**Goal:** Voice interface fully wired end-to-end.

#### Task 4.1 — INSTALL ElevenLabs Orb component

```bash
cd orchestration/ui
pnpm add three @react-three/fiber @react-three/drei
pnpm dlx @elevenlabs/cli@latest components add orb
```

- **RESULT**: Creates `src/components/ui/orb.tsx` (you own this file)
- **VALIDATE**: `pnpm tsc --noEmit` — zero errors after install

#### Task 4.2 — CREATE `orchestration/ui/src/lib/extractAnswer.ts`

- **PATTERN**: From `REF-ELEVENLABS-VOICE-PIPELINE-INTEGRATION.md §1.5`

```typescript
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
```

#### Task 4.3 — CREATE `orchestration/ui/src/hooks/useAgnesVoice.ts`

- **IMPLEMENT**: Complete voice hook from `REF-ELEVENLABS-VOICE-PIPELINE-INTEGRATION.md §1.6`
- **CRITICAL CHANGE**: Use `VITE_ELEVENLABS_API_KEY` (not `NEXT_PUBLIC_`); use `VITE_AGNES_API_URL`
- **IMPLEMENT**: TTS synthesis → AudioContext → output volume analyser → `outputVolumeRef`
- **IMPLEMENT**: Web Speech API STT → transcript → `runPipeline(transcript)`
- **IMPLEMENT**: SSE subscription for pipeline events → `extractAnswer()` → `speak()`
- **IMPLEMENT**: Also dispatch SSE events to `runStore` (so DAG panel updates during voice runs)
- **GOTCHA**: `speak()` function captures `agentState` via closure — use `useCallback` with correct deps
- **GOTCHA**: AudioContext requires user gesture to create — create it inside the `speak()` call, not at component mount

```typescript
// Key env var usage
const AGNES_API = import.meta.env.VITE_AGNES_API_URL ?? 'http://localhost:8000'
const ELEVENLABS_KEY = import.meta.env.VITE_ELEVENLABS_API_KEY ?? ''
const VOICE_ID = import.meta.env.VITE_ELEVENLABS_VOICE_ID ?? '21m00Tcm4TlvDq8ikWAM'
```

- **VALIDATE**: Speak "What are the top consolidation opportunities?" → Orb transitions listening→thinking→talking→idle

#### Task 4.4 — CREATE `orchestration/ui/src/components/PipelineBadge.tsx`

```tsx
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
```

#### Task 4.5 — CREATE `orchestration/ui/src/components/VoiceOrb.tsx`

- **IMPLEMENT**: Full wrapper using `useAgnesVoice()` hook
- **PATTERN**: `REF-ELEVENLABS-VOICE-PIPELINE-INTEGRATION.md §1.7` (`AgnesVoiceOrb` component)
- **IMPLEMENT**: Circular container, tap handler, state label, transcript bubble, pipeline badge
- **IMPLEMENT**: Transcript fade-out after 8s using `setTimeout` clearing

```tsx
import { Orb } from '@/components/ui/orb'
import { useAgnesVoice } from '@/hooks/useAgnesVoice'
import { PIPELINE_COLORS } from '@/types/agnes'
import { PipelineBadge } from './PipelineBadge'

const LABELS = {
  null: 'Tap to speak',
  listening: 'Listening...',
  thinking: (p: string) => `Running ${p.replace(/_/g, ' ')}...`,
  talking: 'Agnes responding...',
}

export function VoiceOrb({ onSpeak }: { onSpeak?: (text: string) => void }) {
  const { agentState, lastPipeline, transcript, inputVolumeRef, outputVolumeRef, startListening } = useAgnesVoice()
  const colors = PIPELINE_COLORS[lastPipeline ?? 'default'] ?? PIPELINE_COLORS.default
  // ... full implementation
}
```

- **VALIDATE**: Orb renders in browser; tap triggers mic request; colors change per pipeline

---

### Phase 5: App Shell + Build

**Goal:** Full layout assembled; production build works; served from FastAPI.

#### Task 5.1 — CREATE `orchestration/ui/src/App.tsx`

- **IMPLEMENT**: Two-column layout: left panel (Orb + trigger form), right panel (DAG + Data Explorer)
- **IMPLEMENT**: Header with "SPHERECAST · Agnes" title + health dot
- **IMPLEMENT**: Health dot: polls `GET /health` every 30s via `useHealth()` hook
- **IMPLEMENT**: `QueryClientProvider` wrapping (from `@tanstack/react-query`)
- **IMPLEMENT**: Wire `VoiceOrb` `onSpeak` → `ProposalsTab` "Speak this" → TTS

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { VoiceOrb } from '@/components/VoiceOrb'
import { DagPanel } from '@/components/DagPanel'
import { DataExplorer } from '@/components/DataExplorer'
import { useHealth } from '@/hooks/useData'

const qc = new QueryClient()

function Header() {
  const { data } = useHealth()
  const ok = data?.status === 'ok'
  return (
    <header className="flex items-center justify-between px-6 py-3 border-b border-slate-700 bg-slate-900">
      <h1 className="font-mono text-lg font-semibold text-slate-100">SPHERECAST · Agnes</h1>
      <div className="flex items-center gap-2 text-xs text-slate-400">
        <span className={`text-base ${ok ? 'text-green-400' : 'text-red-400'}`}>●</span>
        {ok ? 'API Online' : 'API Offline'}
      </div>
    </header>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <div className="min-h-screen bg-[#0f1117] text-slate-100 flex flex-col">
        <Header />
        <main className="flex flex-1 overflow-hidden">
          <aside className="w-80 flex-shrink-0 flex flex-col items-center gap-6 p-6 border-r border-slate-700">
            <VoiceOrb />
            <DagPanel />
          </aside>
          <section className="flex-1 overflow-auto p-6">
            <DataExplorer />
          </section>
        </main>
      </div>
    </QueryClientProvider>
  )
}
```

#### Task 5.2 — ADD error boundaries

- **IMPLEMENT**: Wrap `VoiceOrb` (Three.js) in `<ErrorBoundary fallback={<CssOrbFallback />}>`
- **IMPLEMENT**: CSS fallback: simple pulsing circle `animate-pulse bg-slate-700 rounded-full h-48 w-48`

#### Task 5.3 — ADD loading skeletons

- **IMPLEMENT**: Each data tab shows skeleton rows while `isLoading` is true
- **IMPLEMENT**: Simple `<div className="h-4 bg-slate-700 rounded animate-pulse" />` skeleton rows

#### Task 5.4 — BUILD and serve from FastAPI

```bash
cd orchestration/ui
pnpm build
```

- **VALIDATE**: `orchestration/ui/dist/` directory created with `index.html` and assets
- **VALIDATE**: `PYTHONPATH=. uvicorn orchestration.api.main:app --port 8000` → `http://localhost:8000/ui` loads full React app

---

## STEP-BY-STEP TASKS (Dependency Order)

| # | Task | File | Validate |
|---|---|---|---|
| 1 | CREATE data.py + 4 endpoints | `orchestration/api/routes/data.py` | `curl /api/data/opportunities | python3 -m json.tool` |
| 2 | UPDATE main.py (add data router + CORS header) | `orchestration/api/main.py` | 200 from /api/data/opportunities |
| 3 | BACKUP index.html; scaffold Vite | `orchestration/ui/` | `pnpm dev` runs |
| 4 | CREATE types/agnes.ts | `src/types/agnes.ts` | `pnpm tsc --noEmit` |
| 5 | CREATE lib/api.ts | `src/lib/api.ts` | `pnpm tsc --noEmit` |
| 6 | CREATE hooks/useData.ts | `src/hooks/useData.ts` | `pnpm tsc --noEmit` |
| 7 | CREATE ConfidenceBar.tsx | `src/components/ConfidenceBar.tsx` | renders in Storybook or inline |
| 8 | CREATE OpportunitiesTab.tsx | `src/components/tabs/OpportunitiesTab.tsx` | 129 rows visible |
| 9 | CREATE IngredientsTab.tsx | `src/components/tabs/IngredientsTab.tsx` | 250 ingredients; filter works |
| 10 | CREATE ComplianceTab.tsx | `src/components/tabs/ComplianceTab.tsx` | compliance grid renders |
| 11 | CREATE ProposalsTab.tsx | `src/components/tabs/ProposalsTab.tsx` | empty state shows |
| 12 | CREATE RunsTab.tsx | `src/components/tabs/RunsTab.tsx` | runs list shows |
| 13 | CREATE DataExplorer.tsx | `src/components/DataExplorer.tsx` | all 5 tabs switch |
| 14 | CREATE store/runStore.ts | `src/store/runStore.ts` | `pnpm tsc --noEmit` |
| 15 | CREATE hooks/useRunStream.ts | `src/hooks/useRunStream.ts` | `pnpm tsc --noEmit` |
| 16 | CREATE NodeCard.tsx | `src/components/NodeCard.tsx` | renders all states |
| 17 | CREATE DagPanel.tsx | `src/components/DagPanel.tsx` | trigger pipeline; nodes update |
| 18 | INSTALL Orb + deps | `src/components/ui/orb.tsx` | `pnpm tsc --noEmit` |
| 19 | CREATE lib/extractAnswer.ts | `src/lib/extractAnswer.ts` | `pnpm tsc --noEmit` |
| 20 | CREATE hooks/useAgnesVoice.ts | `src/hooks/useAgnesVoice.ts` | voice loop works |
| 21 | CREATE PipelineBadge.tsx | `src/components/PipelineBadge.tsx` | renders badge |
| 22 | CREATE VoiceOrb.tsx | `src/components/VoiceOrb.tsx` | Orb renders; tap works |
| 23 | CREATE App.tsx | `src/App.tsx` | full layout assembles |
| 24 | ADD error boundaries + skeletons | `App.tsx` + tab components | graceful fallbacks |
| 25 | `pnpm build` | `orchestration/ui/dist/` | build succeeds |
| 26 | UPDATE main.py static mount | `orchestration/api/main.py` | /ui serves React app |

---

## TESTING STRATEGY

### E2E Validation with agent-browser Skill

After each phase, invoke the `agent-browser` skill to validate the UI. The skill automates browser interactions (navigation, screenshots, form filling).

**How to invoke:**
```
/agent-browser
```

**Phase validation scripts for agent-browser:**

**Phase 1-2 validation (data tabs):**
> Navigate to http://localhost:5173. Take a screenshot. Click the "Opportunities" tab and verify at least 129 rows are visible. Click the top row to expand it and verify a "No proposal generated yet" message appears (since all proposals are null). Click "Ingredients" and verify a filter dropdown exists. Take a final screenshot.

**Phase 3 validation (DAG panel):**
> Navigate to http://localhost:5173. In the "Run Pipeline" form, select "supplier_fallout" and enter "Vitamin C" in the ingredient field. Click "Run Pipeline". Take a screenshot of the DAG panel and verify nodes are visible. Wait 10 seconds and take another screenshot to confirm at least one node has completed (green).

**Phase 4 validation (voice):**
> Navigate to http://localhost:5173. Take a screenshot of the Orb. Verify the circular orb container is visible and shows "Tap to speak" label. Verify the pipeline colors match the PIPELINE_COLORS spec.

**Phase 5 validation (built app):**
> Navigate to http://localhost:8000/ui. Verify the full React app loads (not the old vanilla JS monitor). Take a screenshot and verify header shows "SPHERECAST · Agnes" and a green health dot.

### Self-Iterating Validation Loop

To create a continuous validation loop that auto-corrects issues, use the `loop` skill:

**Invocation pattern during development:**
```
/loop 2m /agent-browser Navigate to http://localhost:5173, verify Opportunities tab shows 129 rows, verify no console errors, take a screenshot and report any visual issues
```

This runs the browser check every 2 minutes. When an issue is found (e.g., broken layout, missing data), stop the loop, fix the code, restart the dev server, and resume.

**Acceptance loop (final validation):**
```
/loop
```
Then describe the self-paced loop: check each acceptance criterion in order, report pass/fail, and stop when all pass.

### Unit Tests

No test framework is pre-configured. Add Vitest if time permits:

```bash
pnpm add -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

Priority tests:
- `extractAnswer()` — test with mock events from each pipeline type
- `ConfidenceBar` — test score-to-color mapping at 0, 0.4, 0.7, 1.0
- `useRunStore` — test `updateNode()` state transitions

### Edge Cases to Test

- `Proposal_Text = NULL` for all opportunities → ProposalsTab shows empty state, OpportunitiesTab expand shows fallback message
- Orb when WebGL not supported → ErrorBoundary shows CSS fallback circle
- `VITE_ELEVENLABS_API_KEY` absent → TTS silently skips (no error thrown); Orb still animates
- Web Speech API unavailable (non-Chrome) → `startListening()` catches error; Orb returns to idle
- FastAPI offline → health dot turns red; data queries show error state (not blank screen)
- SSE stream disconnects mid-run → `EventSource` auto-reconnects; DAG state preserved via Zustand

---

## VALIDATION COMMANDS

### Level 1: Type Safety
```bash
cd orchestration/ui && pnpm tsc --noEmit
```

### Level 2: Backend API
```bash
PYTHONPATH=. uvicorn orchestration.api.main:app --port 8000 &
curl -s http://localhost:8000/api/data/opportunities | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'count={d[\"count\"]}, top={d[\"opportunities\"][0][\"ingredient\"]}')"
# Expected: count=129, top=<ingredient with score 0.8929>
curl -s http://localhost:8000/api/data/ingredients | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'ingredients={len(d[\"ingredients\"])}')"
# Expected: ingredients=250
curl -s http://localhost:8000/api/data/compliance | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'rows={len(d[\"compliance\"])}')"
# Expected: rows=126
curl -s http://localhost:8000/api/data/proposals | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'proposals={len(d[\"proposals\"])}')"
# Expected: proposals=0 (no proposals yet)
```

### Level 3: Frontend Dev Server
```bash
cd orchestration/ui && pnpm dev
# Browser: http://localhost:5173 — verify React app loads
```

### Level 4: Pipeline Trigger E2E
```bash
# Start backend if not running
PYTHONPATH=. uvicorn orchestration.api.main:app --port 8000
# Trigger a pipeline
curl -s -X POST http://localhost:8000/pipelines/run/supplier_fallout \
  -H "Content-Type: application/json" \
  -d '{"params": {"ingredient_name": "Vitamin C"}}' | python3 -m json.tool
# Copy run_id from response, then stream events:
# curl -N http://localhost:8000/runs/{run_id}/stream
```

### Level 5: Production Build
```bash
cd orchestration/ui && pnpm build
PYTHONPATH=. uvicorn orchestration.api.main:app --port 8000
# Browser: http://localhost:8000/ui
```

### Level 6: agent-browser E2E (invoke via skill)
```
/agent-browser
```
> Navigate to http://localhost:8000/ui, take a screenshot, verify: (1) header shows "SPHERECAST · Agnes", (2) Orb is visible as a circular dark container, (3) Opportunities tab is visible and shows a table, (4) health dot is green.

---

## ACCEPTANCE CRITERIA

- [ ] `GET /api/data/opportunities` returns 129 rows sorted by `Consolidation_Score DESC`
- [ ] `GET /api/data/ingredients` returns 250 rows; grade filter works
- [ ] `GET /api/data/compliance` returns 126 rows with company names
- [ ] `GET /api/data/proposals` returns empty array with empty state message in UI
- [ ] Vite dev server starts on port 5173 with proxy to 8000
- [ ] `pnpm tsc --noEmit` passes with zero errors
- [ ] Opportunities tab shows 129 rows; top row has Score ≈ 0.893; expand shows empty state for proposal
- [ ] Ingredients tab filterable by grade; slide-over shows SMILES (or "N/A" if null)
- [ ] Compliance tab shows grid with company names and cert types
- [ ] Proposals tab shows empty state message (no proposal text exists yet)
- [ ] Runs tab shows historical runs with status badges
- [ ] Manual pipeline trigger form works; selecting pipeline + entering ingredient + clicking Run starts execution
- [ ] DAG panel updates in real time as pipeline runs (SSE streaming)
- [ ] NodeCard shows elapsed time on completion; error on failure
- [ ] Orb component renders (WebGL sphere) in Chrome; fallback CSS circle in non-WebGL browser
- [ ] Orb state transitions: null → listening → thinking → talking → null
- [ ] Orb color changes per active pipeline (PIPELINE_COLORS map)
- [ ] Voice: speaking triggers STT → POST /chat → SSE stream → TTS response
- [ ] Health dot green when FastAPI is up; red when unreachable
- [ ] `pnpm build` succeeds; `http://localhost:8000/ui` serves the React app
- [ ] No console errors on golden path (data load, tab switch, pipeline trigger)

---

## COMPLETION CHECKLIST

- [ ] All 26 tasks completed in dependency order
- [ ] Each task validated immediately after completion
- [ ] `pnpm tsc --noEmit` passes at all stages
- [ ] Backend data endpoints return correct row counts
- [ ] All 5 data tabs load real SQLite data
- [ ] DAG panel renders and updates via SSE
- [ ] ElevenLabs Orb renders and voice loop works
- [ ] `pnpm build` produces `/dist` directory
- [ ] `/ui` endpoint serves React SPA
- [ ] agent-browser E2E validation passes
- [ ] No regressions: old vanilla pipeline monitor backed up as `index.html.bak`

---

## NOTES

**Schema discrepancies from PRD are fixed in this plan.** The PRD SQL queries use `co.Score`, `ic.DisplayName`, `Finished_Good` — none of these exist. The correct names are `Consolidation_Score`, `Name`, and `Product` respectively. The data.py implementation above uses corrected names.

**No proposals exist yet.** `Proposal_Text IS NULL` for all 129 `Consolidation_Opportunity` rows. The ANTHROPIC_API_KEY must be set and Phase 4 re-run to generate proposals. Design the Proposals tab with empty state as first-class UX.

**Voice is optional for hackathon demo.** If ElevenLabs API key is missing, TTS silently skips and the Orb still animates through states. STT via Web Speech API only works in Chrome/Edge. Design the UI so the manual pipeline trigger is always visible as a fallback.

**The existing `orchestration/ui/index.html`** must be preserved as `index.html.bak` before Vite replaces it. Vite's scaffold will create a new `index.html`.

**FastAPI static mount:** The current mount (`orchestration/ui/` directory) will serve the Vite `index.html` in dev mode. After `pnpm build`, update to mount `orchestration/ui/dist/`. The Task 1.2 `main.py` update handles this by checking for `dist/` first.

**agent-browser + loop workflow:** After each phase, use `/agent-browser` to do visual verification. If a tab shows wrong data or layout breaks, use `/loop` to create a continuous check-fix-verify cycle. This is the fastest path to a working demo — visual feedback beats reading code.
