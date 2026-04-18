# Agnes UI — Product Requirements Document

> **Reference files:** This PRD integrates and extends:
> - `Orchestration/References/Tech/General/REF-ELEVENLABS-ORB-UI.md` — Orb component props, palettes, container patterns
> - `Orchestration/References/Tech/Orchestration/REF-ELEVENLABS-VOICE-PIPELINE-INTEGRATION.md` — STT→/chat→SSE→TTS state machine, `useAgnesVoice` hook
> - `Orchestration/References/Tech/Orchestration/REF-YAML-PIPELINE-SCHEMA.md` — Pipeline YAML schema, node field rules
> - `Orchestration/References/Tech/Orchestration/REF-DAG-CANVAS-ALPINEJS.md` — DAG canvas rendering patterns
> - `Orchestration/References/Tech/General/REF-FASTAPI-BACKEND.md` — FastAPI backend patterns
> - `Orchestration/References/Tech/General/REF-SSE-STREAMING-FASTAPI.md` — SSE streaming implementation

---

## 1. Executive Summary

Agnes is an AI-powered supply chain intelligence system for CPG supplement companies. It ingests bills of materials from multiple companies, enriches ingredients with public databases (PubChem, DSLD, Molport), scores consolidation opportunities, and orchestrates multi-agent pipelines to produce auditable sourcing proposals. The data pipeline and orchestration backend are complete; this PRD covers **Stage 4 — Frontend & Visualization**.

The Agnes UI serves as both a decision-support dashboard and a voice-first interface. Procurement analysts can browse scored consolidation opportunities, inspect ingredient compliance, review AI-generated proposals, and monitor live pipeline execution — all in a single dark-themed React application. At the center of the UI sits an ElevenLabs Orb: the voice interface through which users speak natural-language queries ("Vitamin D3 supplier just went offline — what are our options?") that trigger the correct backend pipeline and receive spoken answers.

**MVP goal:** A Vite + React + TypeScript single-page app served by the existing FastAPI server that wraps the Orb voice interface, a live DAG monitor, and an SQLite data explorer — deployable with zero additional infrastructure.

---

## 2. Mission

**Agnes UI exists to make supply chain intelligence visible, auditable, and conversational.**

### Core Principles

1. **Evidence everywhere** — Every data point shows its confidence score and source API. No silent failures or unexplained recommendations.
2. **Voice-first, data-always** — The Orb is the primary interaction surface, but every spoken insight is also visible in the data tables below.
3. **Live pipeline transparency** — Users see nodes start, complete, and skip in real time. The system is not a black box.
4. **No separate infrastructure** — The UI is a static build served from the existing FastAPI server. One `uvicorn` command runs everything.
5. **Spherecast branding** — Dark slate theme with pipeline-keyed accent colors; the Orb color shifts per active pipeline context.

---

## 3. Target Users

### Primary: Procurement Analyst / Supply Chain Manager
- Domain expert in CPG supplement sourcing; not necessarily technical
- Comfort level: comfortable with dashboards and spreadsheets; unfamiliar with agent logs
- **Needs:** Quickly understand which ingredients to consolidate, which proposals are actionable, which suppliers pass compliance
- **Pain points:** Currently switching between spreadsheets and email; no cross-company visibility; no live system status

### Secondary: Hackathon Judge / Technical Evaluator
- Evaluates reasoning quality, evidence trails, and system architecture
- Comfort level: highly technical; will inspect agent outputs and DAG event logs
- **Needs:** See the full reasoning chain: which nodes ran, what each node returned, how the proposal was derived
- **Pain points:** Black-box AI outputs with no traceability

### Technical User (Builder / Operator)
- Runs pipelines manually, monitors for failures, inspects raw event logs
- **Needs:** Manual pipeline trigger, run history, node-level error inspection

---

## 4. MVP Scope

### Core Functionality
- ✅ ElevenLabs Orb voice interface (center of UI)
- ✅ Natural language → `/chat` → pipeline routing → SSE stream → TTS response
- ✅ Orb color changes per active pipeline
- ✅ Orb `agentState` transitions: idle → listening → thinking → talking
- ✅ Transcript display under the Orb
- ✅ Live DAG panel: node-by-node state updates via SSE
- ✅ Data explorer with 5 tabs: Opportunities, Ingredients, Compliance, Proposals, Runs
- ✅ Opportunities table ranked by Score (top-line KPI: "Vitamin C — 33 companies, score 0.893")
- ✅ Ingredient detail: SMILES, UNII, Grade_Flag, substitution edges, coverage
- ✅ Compliance grid: cert types per product
- ✅ Proposals viewer: full proposal text with pipeline attribution
- ✅ Run history: click any run to expand DAG + event log
- ✅ Manual pipeline trigger (select pipeline, enter ingredient name, run)
- ✅ API health indicator in header

### Technical
- ✅ Vite + React 18 + TypeScript
- ✅ ElevenLabs Orb component (Three.js) via `@elevenlabs/cli`
- ✅ Web Speech API for STT (no additional API key)
- ✅ ElevenLabs TTS REST API for spoken responses
- ✅ `EventSource` for SSE stream consumption
- ✅ New FastAPI data endpoints: `GET /api/data/opportunities`, `/ingredients`, `/compliance`, `/proposals`
- ✅ Static build served from FastAPI at `/ui`
- ✅ Dark theme — Tailwind CSS

### Out of Scope (Post-MVP)
- ❌ ElevenLabs Conversational AI agent (Option 2) — requires ngrok/public URL
- ❌ User authentication / multi-user sessions
- ❌ Mobile responsive layout
- ❌ Export to CSV / PDF
- ❌ Ingredient substitution graph visualization (force-directed graph)
- ❌ Supplier map / geographic visualization
- ❌ Real-time alerts / push notifications
- ❌ Wiki page editor / knowledge base management
- ❌ RxNorm / FDC integration UI
- ❌ Proposal approval workflow (approval gate nodes)

---

## 5. User Stories

### US-1: Voice Query to Pipeline Result
> As a procurement analyst, I want to speak a natural language question and hear a spoken answer so that I don't have to navigate menus or write queries.

**Example:** "Which suppliers can replace our Vitamin C source?" → Orb turns red (supplier_fallout), pipeline runs, Orb speaks: "Three certified alternatives found: BASF, DSM, and Lonza. Full RFQ template attached."

### US-2: Live Pipeline Monitoring
> As a technical user, I want to watch pipeline nodes complete in real time so that I understand what the agent is doing and catch failures immediately.

**Example:** DAG panel shows `find-alternatives [✓ 1.2s]` → `gate-qualify [●]` → `write-proposal [...]` with elapsed times.

### US-3: Consolidation Opportunity Browser
> As a supply chain manager, I want to see a ranked list of ingredients where I can save money by consolidating suppliers across our portfolio companies.

**Example:** Opportunities tab shows "Vitamin C — 33 companies, Score 0.893, $—" with a click-to-expand proposal.

### US-4: Ingredient Deep Dive
> As an analyst, I want to click an ingredient and see its full profile — SMILES structure, UNII, grade, compliance certs, and which companies use it — so I can evaluate substitution feasibility.

### US-5: Manual Pipeline Trigger
> As a builder testing the system, I want to select a pipeline by name, enter parameters, and run it manually without speaking, so I can test agent behavior.

### US-6: Proposal Review
> As a procurement manager, I want to read AI-generated sourcing proposals with full evidence trails (which nodes ran, what data they used) so I can present defensible recommendations to stakeholders.

### US-7: Run Audit
> As a technical evaluator (hackathon judge), I want to click any historical run and see every node's input context, output JSON, and elapsed time so I can verify the reasoning chain.

### US-8: Orb Pipeline Context
> As any user, I want the Orb's color to indicate which pipeline is active so I know at a glance what type of analysis is running.

---

## 6. Core Architecture & Patterns

### High-Level Architecture

```
Browser (Vite + React SPA)
    │
    ├── ElevenLabs Orb (Three.js WebGL)
    │   └── useAgnesVoice hook
    │       ├── Web Speech API → transcript
    │       ├── POST /chat → run_id
    │       ├── EventSource /runs/{run_id}/stream → node events
    │       └── ElevenLabs TTS REST → AudioContext playback
    │
    ├── Data Explorer (React Query + fetch)
    │   ├── GET /api/data/opportunities → db_enriched.sqlite
    │   ├── GET /api/data/ingredients
    │   ├── GET /api/data/compliance
    │   └── GET /api/data/proposals
    │
    └── DAG Monitor (EventSource + Zustand store)
        └── GET /runs/{run_id}/stream → node state map
                │
        FastAPI (uvicorn port 8000)
                │
        ├── orchestration.db (run log + events)
        ├── db_enriched.sqlite (supply chain data)
        └── 5 YAML pipelines + agent registry
```

### Directory Structure

```
orchestration/
└── ui/
    ├── index.html              # Vite entry point
    ├── vite.config.ts
    ├── tailwind.config.ts
    ├── tsconfig.json
    ├── package.json
    └── src/
        ├── main.tsx
        ├── App.tsx             # Layout shell
        ├── components/
        │   ├── ui/
        │   │   └── orb.tsx     # ElevenLabs Orb (CLI-installed)
        │   ├── VoiceOrb.tsx    # Orb wrapper + label + transcript
        │   ├── DagPanel.tsx    # Live DAG visualization
        │   ├── DataExplorer.tsx # Tabs shell
        │   ├── tabs/
        │   │   ├── OpportunitiesTab.tsx
        │   │   ├── IngredientsTab.tsx
        │   │   ├── ComplianceTab.tsx
        │   │   ├── ProposalsTab.tsx
        │   │   └── RunsTab.tsx
        │   ├── NodeCard.tsx    # DAG node with state badge
        │   ├── ConfidenceBar.tsx
        │   └── PipelineBadge.tsx
        ├── hooks/
        │   ├── useAgnesVoice.ts  # Full STT→/chat→SSE→TTS hook
        │   ├── useRunStream.ts   # SSE EventSource hook
        │   └── useData.ts        # Data fetch hooks (React Query)
        ├── store/
        │   └── runStore.ts       # Zustand: activeRunId, nodeStates
        ├── lib/
        │   ├── api.ts            # Typed fetch wrappers for all endpoints
        │   └── extractAnswer.ts  # Extract spoken text from SSE events
        └── types/
            └── agnes.ts          # All shared TypeScript types
```

### Key Design Patterns

**Pattern 1: SSE → Zustand Store → DAG Re-render**
```
EventSource message → parse JSON → dispatch to runStore
runStore.nodeStates[node_id] = { state, elapsed, error, output }
→ DagPanel reads store → re-renders NodeCards
```
See `REF-SSE-STREAMING-FASTAPI.md` for FastAPI SSE implementation.

**Pattern 2: Orb Color Keying**
```typescript
// From REF-ELEVENLABS-ORB-UI.md
const PIPELINE_COLORS: Record<string, [string, string]> = {
  supplier_fallout:        ["#FEB2B2", "#FC8181"],  // red — urgency
  proactive_consolidation: ["#9AE6B4", "#68D391"],  // green — opportunity
  new_ingredient_research: ["#D6BCFA", "#B794F4"],  // purple — exploration
  price_audit:             ["#FAF089", "#F6E05E"],  // yellow — financial
  substitution_discovery:  ["#FBD38D", "#F6AD55"],  // orange — discovery
  default:                 ["#CADCFC", "#A0B9D1"],  // blue-grey — idle
}
```

**Pattern 3: Voice State Machine**
```
null (idle) → "listening" → "thinking" → "talking" → null
      ↑                                                 │
      └─────────────────────────────────────────────────┘
```
Full hook implementation in `REF-ELEVENLABS-VOICE-PIPELINE-INTEGRATION.md §useAgnesVoice`.

**Pattern 4: Node Narration**
```typescript
const NODE_NARRATION: Record<string, string> = {
  "find-alternatives":  "Finding alternative suppliers...",
  "gate-qualify":       "Checking compliance requirements...",
  "bom-impact":         "Analyzing affected products...",
  "format-rfqs":        "Preparing supplier quotes...",
  "write-proposal":     "Writing the final recommendation...",
  "scan-opportunities": "Scanning consolidation opportunities...",
  "benchmark-prices":   "Benchmarking current pricing...",
  "walk-substitutions": "Exploring ingredient substitutions...",
}
```

---

## 7. Features — Detailed Specification

### 7.1 Voice Orb (VoiceOrb.tsx)

The Orb occupies the left panel (~320px) and is the primary UI surface.

**Visual states:**
| `agentState` | Color | Animation | Label |
|---|---|---|---|
| `null` | Pipeline-keyed or default blue-grey | Slow undulation | "Tap to speak" |
| `"listening"` | Active pipeline color | Input volume pulse | "Listening..." |
| `"thinking"` | Active pipeline color | Fast complex shader | "Running {pipeline}..." |
| `"talking"` | Active pipeline color | Output volume pulse | "Agnes responding..." |

**Subcomponents:**
- `Orb` (Three.js) — from `REF-ELEVENLABS-ORB-UI.md`, props: `colors`, `agentState`, `seed=42`, `inputVolumeRef`, `outputVolumeRef`
- Transcript bubble: last spoken transcript in italic, max 2 lines, fades after 8s
- Pipeline badge: e.g. `● supplier_fallout` with matching color dot

**Container:**
```tsx
<div className="relative h-48 w-48 rounded-full p-2 bg-[#0f1117]
    shadow-[inset_0_2px_12px_rgba(0,0,0,0.6)] cursor-pointer">
  <div className="h-full w-full overflow-hidden rounded-full">
    <Orb colors={colors} agentState={agentState} seed={42}
         inputVolumeRef={inputVolRef} outputVolumeRef={outputVolRef} />
  </div>
</div>
```

**Interaction:**
- Single tap/click when idle → start listening
- Auto-stops on speech recognition result
- Error state: flash red, reset to idle after 2s

### 7.2 Live DAG Panel (DagPanel.tsx)

Appears below the data explorer when a run is active (or selected from history). Uses the existing `GET /pipelines/{name}/graph` + `GET /runs/{run_id}/stream` SSE.

**Layout:** Horizontal layers separated by `→` arrows, matching existing `index.html` pattern but polished.

**NodeCard states:**
| State | Ring color | Icon | Shows |
|---|---|---|---|
| `pending` | slate-600 | — | node ID, class name |
| `started` | blue-400 pulse | ● | + "running..." |
| `completed` | green-400 | ✓ | + elapsed ms, output preview |
| `failed` | red-500 | ✗ | + error message |
| `skipped` | amber-500 | ⊘ | + condition name |

**Click to expand:** Shows full `node_output` JSON in a collapsible code block.

### 7.3 Data Explorer (DataExplorer.tsx)

Five tabs. All data fetched from new `/api/data/*` endpoints that query `db_enriched.sqlite`.

#### Tab 1: Opportunities
- **Source:** `Consolidation_Opportunity JOIN Ingredient_Canonical`
- **Columns:** Rank, Ingredient, Companies, Score (progress bar), BOM Coverage, Proposal Preview (truncated 120 chars)
- **Score bar:** colored green→yellow→red by score bucket
- **Click row:** Expand to full Proposal_Text + source formula breakdown
- **Sort:** By Score (default), by Company Count, by Ingredient name
- **Key query:**
```sql
SELECT co.CanonicalIngredientId, ic.DisplayName, ic.UNII_Code, ic.Grade_Flag,
       co.Company_Count, co.Score, co.Score_Formula_Component,
       co.Proposal_Text, co.Compliance_Feasible
FROM Consolidation_Opportunity co
JOIN Ingredient_Canonical ic ON ic.Id = co.CanonicalIngredientId
ORDER BY co.Score DESC NULLS LAST
```

#### Tab 2: Ingredients
- **Source:** `Ingredient_Canonical LEFT JOIN Ingredient_Substitution`
- **Columns:** Name, UNII, CAS, Grade, SMILES (truncated), Substitution edges, Match confidence
- **Click row:** Slide-over detail panel — full SMILES, all substitution pairs, PubChem CID, company usage count
- **Filter:** By Grade_Flag (supplement / food / excipient / sweetener / flavor / unknown)

#### Tab 3: Compliance
- **Source:** `Product_Compliance JOIN Finished_Good`
- **Columns:** Product, Company, Cert Type, Cert Body, Expiry, Status, Off Market Warning
- **Grid view:** products as rows, cert types as columns, ✓/✗ cells
- **Filter:** By cert type (NSF, USP, Informed Sport, etc.)

#### Tab 4: Proposals
- **Source:** `Consolidation_Opportunity WHERE Proposal_Text IS NOT NULL`
- **List view:** Card per proposal — ingredient name, company count, score badge, full proposal text
- **"Speak this" button:** Sends proposal text to ElevenLabs TTS, Orb transitions to "talking"

#### Tab 5: Runs
- **Source:** `GET /runs` (orchestration.db)
- **Columns:** Pipeline, Status badge, Started, Duration, Run ID
- **Click row:** Expand DAG panel with historical events (replays via `GET /runs/{id}` events array)
- **Status badges:** pending (slate), running (blue pulse), completed (green), failed (red)

### 7.4 Manual Pipeline Trigger

Accessible via a "Run Pipeline" button in the left panel below the Orb.

```
┌────────────────────────────┐
│ Pipeline: [▼ supplier_fallout]
│ Ingredient: [Vitamin C     ]
│            [  Run Pipeline ]
└────────────────────────────┘
```

Calls `POST /pipelines/run/{name}` with `{ params: { ingredient_name } }`, sets `activeRunId`, SSE stream auto-starts.

### 7.5 Header

```
SPHERECAST · Agnes          ● API Online    [Health dot]
```

- Title: "SPHERECAST · Agnes" — bold, slate-100, monospaced feel
- Health dot: polls `GET /health` every 30s — green (ok), red (unreachable), gray (checking)
- No logo asset (none exists) — text-only branding

---

## 8. Technology Stack

### Frontend
| Technology | Version | Purpose |
|---|---|---|
| Vite | 5.x | Build tooling, HMR dev server |
| React | 18.x | UI framework |
| TypeScript | 5.x | Type safety |
| Tailwind CSS | 3.x | Utility-first styling |
| Three.js | latest | 3D WebGL (Orb dependency) |
| @react-three/fiber | latest | React renderer for Three.js |
| @react-three/drei | latest | Three.js helpers |
| Zustand | 4.x | Lightweight state (run store) |
| @tanstack/react-query | 5.x | Data fetching, caching, refresh |
| @elevenlabs/cli | latest | Orb component installer |

### ElevenLabs Voice
| Component | Implementation |
|---|---|
| STT | Web Speech API (`webkitSpeechRecognition`) — no API key |
| TTS | ElevenLabs REST `POST /v1/text-to-speech/{voiceId}/stream` |
| Voice model | `eleven_turbo_v2_5` (lowest latency) |
| Voice ID | `21m00Tcm4TlvDq8ikWAM` (Rachel — professional) |
| Orb | `@/components/ui/orb.tsx` (CLI-copied, not node_modules) |

See `REF-ELEVENLABS-VOICE-PIPELINE-INTEGRATION.md` for full integration patterns.

### Backend Additions (FastAPI)
New data endpoints added to `orchestration/api/routes/data.py`:
```python
GET /api/data/opportunities   # Consolidation_Opportunity ranked
GET /api/data/ingredients     # Ingredient_Canonical with substitutions
GET /api/data/compliance      # Product_Compliance grid
GET /api/data/proposals       # Proposals with full text
```
All read `db_enriched.sqlite` (read-only). See `REF-FASTAPI-BACKEND.md` for patterns.

### Build & Serve
```
orchestration/ui/              # Vite project root
vite build → dist/             # Static output
FastAPI: app.mount("/ui", StaticFiles(directory="orchestration/ui/dist"))
```

---

## 9. Security & Configuration

### Environment Variables
```bash
# Frontend (.env in orchestration/ui/)
VITE_ELEVENLABS_API_KEY=sk-...           # ElevenLabs TTS
VITE_ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
VITE_AGNES_API_URL=http://localhost:8000  # Backend URL

# Backend (root .env — already configured)
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...
DSLD_API_KEY=...
```

### Security Scope
- ✅ CORS already configured (`*`) on FastAPI — no change needed for local
- ❌ No auth (out of scope — hackathon MVP)
- ❌ API key never sent to browser for backend calls (TTS key is client-side — acceptable for demo)
- ✅ All DB reads are SELECT-only (data endpoints are read-only)
- ✅ `db_enriched.sqlite` opened read-only in data routes

---

## 10. API Specification

### Existing Endpoints (consumed by UI)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/chat` | Natural language → pipeline routing + execution |
| `POST` | `/pipelines/run/{name}` | Manual pipeline trigger |
| `GET` | `/pipelines` | List pipeline names |
| `GET` | `/pipelines/{name}/graph` | DAG topology (layers + nodes) |
| `GET` | `/runs` | Recent run list (limit param) |
| `GET` | `/runs/{run_id}` | Run status + full event log |
| `GET` | `/runs/{run_id}/stream` | SSE stream of live events |
| `GET` | `/proposals` | Proposal list |
| `GET` | `/health` | API health check |

See full request/response shapes in agent research output or `orchestration/api/routes/`.

### New Data Endpoints (to add)

#### `GET /api/data/opportunities`
```json
{
  "opportunities": [
    {
      "id": 1,
      "ingredient": "Vitamin C",
      "unii": "PQ6CK8PD0R",
      "grade_flag": "supplement",
      "company_count": 33,
      "score": 0.893,
      "score_formula_component": 0.85,
      "compliance_feasible": true,
      "proposal_text": "Twelve companies currently source Vitamin C..."
    }
  ],
  "count": 129
}
```

#### `GET /api/data/ingredients?grade=supplement`
```json
{
  "ingredients": [
    {
      "id": 1,
      "display_name": "Vitamin C",
      "unii_code": "PQ6CK8PD0R",
      "cas_number": "50-81-7",
      "pubchem_cid": 54670067,
      "smiles": "OC[C@H](O)[C@@H](O)[C@H](O)[C@H](O)C=O",
      "grade_flag": "supplement",
      "match_score": 0.95,
      "substitution_edges": 3
    }
  ]
}
```

#### `GET /api/data/compliance`
```json
{
  "compliance": [
    {
      "product_id": "SKU-123",
      "company": "NutriCo",
      "cert_type": "NSF",
      "cert_body": "NSF International",
      "status": "implied",
      "off_market_warning": null
    }
  ]
}
```

#### `GET /api/data/proposals`
```json
{
  "proposals": [
    {
      "ingredient": "Vitamin C",
      "company_count": 33,
      "score": 0.893,
      "proposal_text": "Full narrative...",
      "compliance_feasible": true,
      "grade_flag": "supplement"
    }
  ]
}
```

---

## 11. Success Criteria

### MVP Success Definition
Agnes UI is successful when a non-technical user can speak a supply chain question and receive a spoken, data-backed answer — and a technical evaluator can trace every reasoning step from voice input to proposal output.

### Functional Requirements
- ✅ Voice query routes to correct pipeline with >80% accuracy (RouterAgent)
- ✅ Orb state transitions match voice lifecycle (no stuck states)
- ✅ Orb color matches active pipeline
- ✅ DAG panel shows node completions within 1s of SSE event receipt
- ✅ All 5 data tabs load in <2s from SQLite
- ✅ Opportunities tab shows all 129 scored rows sorted by Score
- ✅ Proposals tab shows all rows with non-null `Proposal_Text`
- ✅ Manual pipeline trigger works for all 5 pipelines
- ✅ Run history loads last 50 runs; clicking any replays DAG
- ✅ Health indicator reflects actual API availability

### Quality Indicators
- No stuck Orb states (always returns to idle after pipeline completion or error)
- Node expand shows valid JSON output (not undefined or empty)
- Confidence bars render for all rows (handle NULL gracefully as 0)
- No console errors in happy path

### User Experience Goals
- Analyst can find top consolidation opportunity in <15 seconds without instructions
- Judge can trace full reasoning chain for any run in <30 seconds

---

## 12. Implementation Phases

### Phase 1: Scaffold + Data Explorer (Day 1)
**Goal:** Vite+React project running, all 5 data tabs showing real SQLite data.

Deliverables:
- ✅ `orchestration/ui/` Vite+React+TS+Tailwind project scaffold
- ✅ `vite.config.ts` with proxy to FastAPI (`/api` → `localhost:8000`)
- ✅ FastAPI routes: `orchestration/api/routes/data.py` with 4 new endpoints
- ✅ `api.ts` typed fetch wrappers for all 9 existing + 4 new endpoints
- ✅ `DataExplorer.tsx` with 5 tabs (static layout, real data)
- ✅ `OpportunitiesTab.tsx` — sorted table, score bars, expand row
- ✅ `IngredientsTab.tsx` — filterable by grade, slide-over detail
- ✅ `ComplianceTab.tsx` — cert grid
- ✅ `ProposalsTab.tsx` — proposal cards
- ✅ `RunsTab.tsx` — run list with status badges
- ✅ Header with health dot

**Validation:** All tabs show real data from `db_enriched.sqlite`. No hardcoded fixtures.

---

### Phase 2: DAG Monitor + Run Streaming (Day 1–2)
**Goal:** Live pipeline execution visible in the UI.

Deliverables:
- ✅ `useRunStream.ts` hook — EventSource, parse events, dispatch to Zustand store
- ✅ `runStore.ts` — Zustand store: `activeRunId`, `nodeStates`, `pipelineGraph`
- ✅ `DagPanel.tsx` — horizontal layer layout, `NodeCard` per node
- ✅ `NodeCard.tsx` — state badge, elapsed time, error message, expand-to-JSON
- ✅ Historical event replay (load from `GET /runs/{id}.events` on click)
- ✅ Manual pipeline trigger form (select + text input + run button)
- ✅ Auto-open DAG panel when run starts

**Validation:** Trigger `supplier_fallout` pipeline, watch all 4 nodes complete with elapsed times. Click historical run, DAG replays correctly.

---

### Phase 3: ElevenLabs Orb + Voice (Day 2)
**Goal:** Voice interface fully wired.

Deliverables:
- ✅ Install ElevenLabs Orb: `pnpm dlx @elevenlabs/cli@latest components add orb`
- ✅ Install peer deps: `pnpm add three @react-three/fiber @react-three/drei`
- ✅ `useAgnesVoice.ts` hook (from `REF-ELEVENLABS-VOICE-PIPELINE-INTEGRATION.md`)
- ✅ `VoiceOrb.tsx` — Orb wrapper, tap handler, state labels, transcript bubble
- ✅ Pipeline color keying (PIPELINE_COLORS map)
- ✅ ElevenLabs TTS: synthesize + play via AudioContext
- ✅ Output volume analyser → `outputVolumeRef` → Orb pulse
- ✅ "Speak this" button on Proposals tab
- ✅ Node narration map (optional: speak node name during thinking)

**Validation:** Speak "What happens if our Vitamin C supplier goes offline?" → Orb turns red, pipeline runs, Orb speaks proposal, returns to idle.

---

### Phase 4: Polish + Build (Day 2–3)
**Goal:** Production-ready static build served from FastAPI.

Deliverables:
- ✅ `vite build` outputs to `orchestration/ui/dist/`
- ✅ FastAPI: `app.mount("/ui", StaticFiles(directory="orchestration/ui/dist", html=True))`
- ✅ Error boundary on Orb (WebGL not supported fallback)
- ✅ Loading skeletons on all data tabs
- ✅ Empty state messages (no proposals yet, etc.)
- ✅ Responsive minimum: 1280px desktop, readable at 1024px
- ✅ README update: `cd orchestration/ui && pnpm install && pnpm build`

**Validation:** `uvicorn orchestration.api.main:app --port 8000` → browser → `http://localhost:8000/ui` → full UI loads. Voice works end-to-end.

---

## 13. Future Considerations

### Post-MVP Enhancements
- **ElevenLabs Conversational AI (Option 2):** Full turn-based conversation with memory; requires public endpoint (ngrok/Cloudflare Tunnel). See `REF-ELEVENLABS-VOICE-PIPELINE-INTEGRATION.md §Option 2`.
- **Substitution graph visualization:** Force-directed graph (D3.js or Cytoscape) showing ingredient equivalence edges.
- **Supplier map:** Geographic map of supplier locations for affected ingredients.
- **Proposal approval flow:** "Approve" / "Reject" buttons write back to `Consolidation_Opportunity`, trigger `approval` gate nodes.
- **Mobile responsive:** Orb stacks above data explorer on small screens.
- **Export:** Download proposals as PDF or CSV for stakeholder presentations.

### Integration Opportunities
- **ElevenLabs Conversational AI agent:** Tool-calling agent calls `/chat` directly, enabling multi-turn conversations.
- **Slack / Email notifications:** Pipeline completion webhooks.
- **Molport real pricing:** When `MOLPORT_API_KEY` is set, surface real pricing in the Opportunities tab.
- **RxNorm / FDC data:** Additional data tabs for drug-class ingredients and food-grade materials.

### Advanced Features
- **Confidence drift alerts:** Flag ingredients where `MatchScore` dropped between enrichment runs.
- **Proposal comparison:** Side-by-side view of two pipeline runs for the same ingredient.
- **Wiki page viewer:** Render `Orchestration/Wiki/` markdown pages in-app.

---

## 14. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **WebGL not supported** in judge's browser | Low | High | Error boundary with graceful fallback to CSS-animated orb substitute |
| **Web Speech API** unavailable (non-Chrome) | Medium | Medium | Fallback text input field; voice is enhancement not blocker |
| **ElevenLabs API key missing** | Low | Medium | TTS silently degrades to text-only mode; Orb still animates |
| **RouterAgent misclassifies** voice query | Medium | Low | Show pipeline + confidence in UI; manual override trigger always available |
| **SQLite read contention** (enrichment re-run during UI) | Low | Low | Open `db_enriched.sqlite` in WAL mode read-only; all data endpoints are SELECT-only |

---

## 15. Appendix

### Related Documents
| Document | Location | Purpose |
|---|---|---|
| ElevenLabs Orb UI Reference | `Orchestration/References/Tech/General/REF-ELEVENLABS-ORB-UI.md` | Orb props, palettes, container patterns |
| ElevenLabs Voice Pipeline Integration | `Orchestration/References/Tech/Orchestration/REF-ELEVENLABS-VOICE-PIPELINE-INTEGRATION.md` | `useAgnesVoice` hook, STT/TTS patterns, Option 1 & 2 |
| YAML Pipeline Schema | `Orchestration/References/Tech/Orchestration/REF-YAML-PIPELINE-SCHEMA.md` | Pipeline YAML field rules, conditions |
| DAG Canvas AlpineJS | `Orchestration/References/Tech/Orchestration/REF-DAG-CANVAS-ALPINEJS.md` | DAG rendering patterns |
| FastAPI Backend Reference | `Orchestration/References/Tech/General/REF-FASTAPI-BACKEND.md` | FastAPI patterns for new data endpoints |
| SSE Streaming Reference | `Orchestration/References/Tech/General/REF-SSE-STREAMING-FASTAPI.md` | SSE implementation on FastAPI + EventSource client |
| Orchestration PRD | `Orchestration/PRDs/4Orchestration.md` | Agent layer requirements |
| Orchestration Status | `Orchestration/PRDs/5. OrchestrationLayerStatus.md` | What is built vs. pending |
| Plan 7 Handover | `Orchestration/Briefings by Agents for Agents/plan-7-handover.md` | Last session handover notes |
| Spherecast Challenge Overview | `Orchestration/Data/Spherecast/Overview.md` | Business problem statement, judging criteria |
| CLAUDE.md | `CLAUDE.md` | Agent self-maintained state; current DB row counts |

### Key Database Tables (db_enriched.sqlite)
| Table | Rows | UI Surface |
|---|---|---|
| `Consolidation_Opportunity` | 129 | Opportunities tab, Proposals tab |
| `Ingredient_Canonical` | ~250 | Ingredients tab |
| `SKU_To_Canonical` | 854 | Ingredient detail slide-over |
| `BOM_Component_Quantity` | 515 | Ingredient detail |
| `Product_Compliance` | 126 | Compliance tab |
| `Supplier_Commercial` | ~40 | Future: supplier detail |
| `Ingredient_Substitution` | 30 edges | Ingredient detail, future graph |

### Key Database Tables (orchestration.db)
| Table | UI Surface |
|---|---|
| `pipeline_runs` | Runs tab, DAG panel |
| `pipeline_events` | DAG panel node states, event log |

### FastAPI Start Command
```bash
PYTHONPATH=. uvicorn orchestration.api.main:app --reload --port 8000
```

### Frontend Dev Command (once scaffolded)
```bash
cd orchestration/ui
pnpm install
pnpm dev   # Vite dev server with proxy to port 8000
```
