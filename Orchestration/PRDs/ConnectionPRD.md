# Agnes — Connection PRD: Binding All Pieces Into a Winning Product

**Version:** 1.0  
**Date:** 2026-04-18  
**Status:** Ready for Planning  
**Scope:** Data execution, display fixes, compliance intelligence, missing UI features, hackathon-critical features

---

## 1. Executive Summary

Agnes is a multi-agent AI procurement intelligence platform built for the Spherecast hackathon. Across multiple development sessions, a sophisticated architecture has been assembled: 7 DAG pipelines, 17+ API endpoints, 9 AI agents (Claude + Gemini), a real-time DAG visualization frontend, voice interface via ElevenLabs, and a 250-ingredient enriched SQLite database spanning FDA IID limits, OpenFDA adverse events, compliance certifications, substitution graphs, and regulatory drift monitoring.

The problem: the architecture is built, but **the data is not populated** and **several critical display issues** make the system look broken despite the underlying intelligence being correct. The compliance matrix shows internal SKU codes instead of product names. The Ingredients tab surfaces IUPAC chemical names instead of common ingredient names. The Suppliers and Proposals tabs show EmptyState because enrichment backfills have not been run. The compliance hierarchy is incomplete — a Vegan-certified product does not automatically show as Vegetarian. Three judge-critical features (citation ledger, refusal panel, red-team agent) are either missing or invisible in the UI.

This PRD defines the work needed to **connect all the pieces**: execute the data pipeline, fix the display layer, implement compliance intelligence, add the three missing UI tabs (Regulatory Alerts, Refusal Panel, the notifications badge), and build the two hackathon-defining features (citation ledger + refusal visibility) that directly address the judging criteria.

**MVP goal:** Agnes should be demo-able as a coherent, end-to-end system where every tab shows real data, every compliance claim is justified, every proposal is grounded in citations, and every refusal is explained — matching the Spherecast judging criteria on reasoning quality, trustworthiness, and evidence trails.

---

## 2. Mission

**Agnes is the reasoning-first AI supply chain advisor that replaces weeks of fragmented sourcing research with minutes of evidence-grounded, auditable decisions.**

### Core Principles

1. **Evidence-first**: Every claim Agnes makes must trace to a source row — FDA IID, DSLD label, PubChem entry, or supplier search result. Unsubstantiated claims are refused, not hallucinated.
2. **Explicit uncertainty**: When Agnes doesn't know, it says so. The refusal engine is as important as the recommendation engine. Confidence scores, data gaps, and stale data are always surfaced.
3. **Compounding intelligence**: Each pipeline run enriches the database. Each enrichment improves the next reasoning pass. Supplier wiki grows, substitution graph expands, regulatory alerts accumulate.
4. **Auditable decisions**: Every sourcing proposal includes an evidence trail. Judges and users can trace from recommendation → claim → source row → external citation.
5. **Correct by hierarchy**: Compliance inference follows real-world certification hierarchies (Vegan ⊇ Vegetarian; Organic → NonGMO implication; USP grade ≻ food grade).

---

## 3. Target Users

### Primary User Persona: Supply Chain Analyst / Procurement Manager

- Works at a CPG supplement manufacturer or procurement intelligence firm
- Manages sourcing for 50–500 raw material SKUs across multiple product lines
- Does NOT manually monitor FDA.gov, supplier websites, or certification databases
- Needs defensible decisions they can present to legal, quality, and finance teams
- **Pain points**: fragmented supplier data, compliance uncertainty on substitutions, no proactive regulatory monitoring, no consolidated sourcing view across the portfolio

### Secondary Persona: Hackathon Judge

- Expert in AI, supply chain, or CPG with 30 seconds to form an impression
- Looking for: reasoning quality, evidence trails, hallucination control, practical usefulness
- Will ask: "How do you know this?" and "What if this is wrong?"
- Impressed by systems that argue with themselves (red-team), cite their sources, and refuse when they should

### Technical Comfort

- Primary user: moderate — uses dashboards, not code
- The system must be operable via voice ("Find consolidation opportunities for Vitamin C") and via the UI without touching the terminal

---

## 4. MVP Scope

### In Scope

**Data Execution**
- ✅ Run `reasoning/proposal_generator.py` to populate all 123 `Proposal_Text` rows
- ✅ Run `enrichment/backfill_supplier_web.py` to populate `Supplier_Commercial` via Google Search
- ✅ Trigger `regulatory_drift_alert` pipeline to populate drift flags and narrative
- ✅ Trigger `price_monitor` pipeline twice to establish baselines and generate first alerts

**Display Name Fixes**
- ✅ Enrich `Product` table with real display names (from iHerb product IDs)
- ✅ Ingredient canonical name cleanup — DSLD common name override for technical IUPAC names
- ✅ Compliance view shows meaningful product names, not `FG-iherb-10421`

**Compliance Intelligence**
- ✅ Certification hierarchy inference: Vegan → Vegetarian (implied), Organic → NonGMO (implied)
- ✅ Add "Vegetarian" as a derived certification type in the API compliance pivot
- ✅ Status display: distinguish "confirmed" vs "implied" more clearly in the UI
- ✅ Compliance API returns hierarchically-expanded certification set

**Missing UI Tabs & Components**
- ✅ Regulatory Alerts tab in Sidebar (backend API already exists)
- ✅ Regulatory Alerts view component with severity badges and before/after MDE comparison
- ✅ TopBar notification badge for unread price alerts (hook + count endpoint already exist)
- ✅ Refusal Panel — surface RefusalEngine outcomes as a first-class UI view

**Hackathon-Critical Features**
- ✅ Citation Ledger (`Claim_Citation` table + proposal writer emitting citations)
- ✅ Per-proposal citation viewer: each claim links to a source row
- ✅ Unsubstantiated claims auto-labeled "unverified" in the UI

**Demo Setup**
- ✅ Demo traps seeded: 4 adversarial test cases Agnes should catch
- ✅ All tabs showing real data for the demo walk-through
- ✅ Voice pipeline end-to-end: STT → chat → SSE stream → TTS response

### Out of Scope

**Architecture / Infrastructure**
- ❌ Multi-tenant isolation (each company's data isolated)
- ❌ Production deploy / Docker / CI-CD pipeline
- ❌ Authentication / role-based access control
- ❌ Real email/Slack dispatch for alerts (RFQ and alert notification stubs only)

**Advanced Reasoning**
- ❌ ReEvalDaemon (drains Re_Eval_Queue — deferred; needs Re_Eval_Queue migration first)
- ❌ Calibrator / Critic agent (design phase not complete)
- ❌ RedTeamAgent full implementation (can demo conceptually via seeded traps)
- ❌ Dual-model compliance gate (Claude + GPT-4 disagreement escalation)
- ❌ Role vector distribution (role distribution instead of single role label)

**Enrichment**
- ❌ Multimodal label/SDS ingestion (vision model PDF/image parsing)
- ❌ Certification registry scraper (USDA Organic, Non-GMO Project, Kosher public listings)
- ❌ Wayback Machine fallback for supplier 404s
- ❌ Generalized supplier landing-page reader (Playwright-based extraction)
- ❌ Molport live integration (API key pending)

**Business Features**
- ❌ Savings dashboard (projected vs. realized cost savings)
- ❌ Change-order JSON export (SAP/Oracle integration)
- ❌ CSV → BOM uploader (bring-your-own data)
- ❌ Multi-run price trend chart (time-series cost trajectory)

---

## 5. User Stories

### US-1: Real Product Names in Compliance Matrix
**As a** procurement analyst,  
**I want to** see real product names (e.g., "Solgar Vitamin D3 2000 IU") instead of internal iHerb codes (`FG-iherb-14689`) in the compliance matrix,  
**so that** I can quickly identify which products have which certifications without needing to look up internal IDs.

*Acceptance:* Compliance view shows company brand name + human-readable product name. If iHerb name is unavailable, show Company + product ID in a readable format.

### US-2: Vegan Implies Vegetarian
**As a** compliance manager reviewing a Vegan-certified product,  
**I want to** see Vegetarian also marked as "implied" in the compliance matrix,  
**so that** I can confidently propose this product's ingredients in formulations requiring either certification without re-verifying.

*Acceptance:* API pivot applies hierarchy rules: Vegan product → Vegetarian implied; Organic product → NonGMO implied. Frontend matrix shows derived certs with a distinct "derived" visual treatment (e.g., lighter shade than "implied").

### US-3: Ingredient Search Returns Common Names
**As a** sourcing analyst searching for "Vitamin C",  
**I want to** find "Ascorbic Acid" and "L-Ascorbic Acid" in ingredient search results,  
**so that** I can work with familiar ingredient names rather than IUPAC chemical nomenclature like `(2S)-2-[(1S)-1,2-dihydroxyethyl]-4-hydroxy-5-oxo-2H-furan-3-olate`.

*Acceptance:* Ingredients API returns `display_name` as common name (DSLD override when available), IUPAC name in separate `iupac_name` field shown only in detail drawer.

### US-4: Proposals with Cited Evidence
**As a** procurement manager reviewing Agnes's consolidation proposal for Vitamin C,  
**I want to** see each claim in the proposal linked to a specific source (FDA IID row, PubChem CID, compliance cert, supplier commercial row),  
**so that** I can verify Agnes's reasoning and present a defensible recommendation to legal and quality teams.

*Acceptance:* Proposal cards show a "Citations" expandable section. Each citation shows: claim text, source type (FDA/PubChem/DSLD/Supplier), source identifier, confidence score.

### US-5: Refusal Panel Visibility
**As a** procurement analyst,  
**I want to** see when Agnes explicitly refuses a substitution recommendation and understand why,  
**so that** I understand the limits of what Agnes can confidently recommend and know what additional information would unblock the decision.

*Acceptance:* A "Refusals" section appears in the Proposals tab (or dedicated tab) showing: what was asked, why Agnes refused (confidence below floor, missing jurisdiction cert, grade mismatch), and what data would unblock it.

### US-6: Regulatory Alerts Tab
**As a** supply chain analyst,  
**I want to** see a dedicated Regulatory Alerts tab showing FDA IID changes affecting our portfolio ingredients,  
**so that** I can proactively address formulation or compliance risks before they become violations.

*Acceptance:* Sidebar shows "Regulatory" tab. View shows alert cards with: ingredient name, change type (C/D/R), severity badge (HIGH/MEDIUM/LOW), before/after MDE comparison, and which products are affected.

### US-7: Live Price Intelligence
**As a** procurement manager,  
**I want to** see Agnes's price alert notifications in the top bar and a dedicated alerts view,  
**so that** I don't miss significant market price movements (≥15% changes) that represent sourcing opportunities or cost risks.

*Acceptance:* TopBar shows unread alert count badge. Price Alerts tab shows cards with ingredient, direction arrow, % change, severity, Gemini narrative, and dismiss button.

### US-8: Voice-Triggered Pipeline Execution
**As a** procurement manager in a meeting,  
**I want to** say "Find me consolidation opportunities for Magnesium" and see Agnes execute the pipeline in real time with the DAG graph rendering,  
**so that** I can demo the system's full reasoning chain without touching a keyboard.

*Acceptance:* STT captures utterance → RouterAgent classifies → `proactive_consolidation` pipeline triggers → DAG graph renders live with node status updates → TTS reads back the top proposal.

---

## 6. Core Architecture & Patterns

### System Architecture

```
┌─────────────────────────────────────────────────────┐
│                 React SPA (Lovable)                  │
│  Tabs: Agnes | Opps | Ingredients | Compliance |    │
│  Proposals | Runs | Suppliers | Alerts | Regulatory │
│  TopBar badge | OrbHero (ElevenLabs) | DagGraphView │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP + SSE (port 8001)
┌──────────────────────▼──────────────────────────────┐
│              FastAPI Orchestration API               │
│  /chat → RouterAgent (Claude Haiku)                 │
│  /pipelines/run/{name} → DAGExecutor                │
│  /api/data/* → SQLite read-only                     │
│  /api/alerts/* → Price_Change_Alert CRUD            │
│  /api/scoring/* → Supplier scoring weights           │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│              DAG Pipeline Engine                     │
│  7 pipelines (YAML) → topological layer execution   │
│  Agents: Claude Haiku/Sonnet + Gemini 2.5 Flash     │
│  Tools: deterministic SQL + computation tools        │
│  Conditions: named guards gate node execution        │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│           db_enriched.sqlite (WAL mode)              │
│  250 canonical ingredients | 7 companies            │
│  66 products | 123 opportunities | 126 compliance   │
│  9,067 FDA IID rows | 187 change log rows           │
│  32 substitution edges | 515 BOM quantities         │
└─────────────────────────────────────────────────────┘
```

### Key Design Patterns

**DAG Executor pattern**: YAML pipeline → `pipeline_loader.py` → topological sort → asyncio.gather() per layer → SSE publish → DB event log. Agents are async, tools are sync. Node outputs stored in `AgnesContext.node_outputs[node_id]`.

**Agent registry pattern**: All agents/tools are registered by class name string in `agent_registry.py`. DAG executor resolves `agent_class` / `tool_class` at runtime via import. New agents/tools just need a `run(ctx: AgnesContext) -> dict` function.

**Condition guard pattern**: YAML `when: condition_name` fields gate node execution. Conditions are pure functions `(ctx: AgnesContext) -> bool` registered in `conditions.py`. Guards read upstream node output via `ctx.get("node-id", {})`.

**Read-only SQLite**: All read endpoints use `sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)` + WAL journal mode. Write endpoints use writable connection. Prevents concurrent write conflicts with enrichment scripts.

**Evidence chain**: Every enrichment write includes a confidence score (0.0–1.0) and source tag. Downstream reasoning agents receive confidence-weighted context. RefusalEngine applies `CONFIDENCE_FLOOR=0.50`.

---

## 7. Feature Specifications

### F1: Product Display Name Enrichment

**Problem**: `Product.SKU` = `FG-iherb-10421` — no human-readable name in DB.  
**Solution**: Two-pass approach.

**Pass A — Company + ID format** (immediate fix, no API calls):
- Compliance API returns `f"{company} Product #{product_id}"` when no display name exists
- Strips `FG-iherb-` prefix, shows just the number
- Shows company brand name prominently (already correct and real)

**Pass B — iHerb product name lookup** (enrichment script):
- `enrichment/sources/iherb.py`: `get_product_name(iherb_id: str) -> str | None`
- HTTP GET to iHerb product page, extract `<title>` or structured data product name
- Cache in new `Product.DisplayName` column (migration required)
- `enrichment/backfill_product_names.py`: runs for all `FG-iherb-*` products

### F2: Compliance Hierarchy Inference

**Problem**: Vegan → Vegetarian not inferred. Organic → NonGMO not inferred.  
**Solution**: Apply implication rules in the API pivot function, not in the DB.

**Hierarchy rules** (one-directional implications):
```python
CERT_IMPLICATIONS = {
    "Vegan": ["Vegetarian"],          # All vegan products are vegetarian
    "Organic": ["NonGMO"],            # Organic certification typically implies NonGMO
    "NSF": ["cGMP"],                  # NSF certification includes GMP compliance
    "InformedSport": ["cGMP"],        # Informed Sport requires GMP compliance
    "USP": ["cGMP"],                  # USP verified includes GMP verification
}
```

**Status for derived certs**: `"derived"` (new status type, shown as lighter shade in matrix)  
**API change**: compliance pivot runs implication rules after loading from DB, adds derived certs with status="derived"  
**Frontend change**: Add "Derived" to compliance Legend. Cell style: faint green / dashed border

### F3: Ingredient Display Name Cleanup

**Problem**: `ic.Name` can be IUPAC, FDA uppercase, or common name inconsistently.  
**Solution**: 
- Add `DisplayName TEXT` column to `Ingredient_Canonical` via migration
- Populate from: (1) DSLD common name where available, (2) PubChem preferred name, (3) fallback to `ic.Name` with `title()` case fix
- API returns `display_name` from new column, `iupac_name` from existing `Name` column
- Frontend IngredientsView card shows `display_name`; detail drawer shows both

**Immediate fix** (no migration needed): apply `title()` case normalization on the API layer for all-uppercase names like `ASCORBYL PALMITATE` → `Ascorbyl Palmitate`.

### F4: Regulatory Alerts Tab

**Status**: Backend 100% complete (API, DB, pipeline). Frontend: 0%.  
**Work needed**:
- Add `"regulatory"` to `TabKey` union in `Sidebar.tsx`
- Add sidebar entry: `{ key: "regulatory", label: "Regulatory", icon: ShieldAlert }`
- Add to `TAB_TITLES` in `Index.tsx`
- Add tab render: `tab === "regulatory" ? <RegulatoryAlertsView />`
- Create `RegulatoryAlertsView.tsx` component

**View design**:
- Filter bar: by status (C/D/R), severity (HIGH/MEDIUM/LOW)
- Alert card: ingredient name (canonical), status badge, severity badge, route/form, before/after MDE comparison, affected opportunity link
- "Run Pipeline" CTA button → triggers `POST /pipelines/run/regulatory_drift_alert`
- Empty state: "No regulatory alerts. Run the regulatory_drift_alert pipeline to scan for FDA IID changes."

### F5: TopBar Price Alert Badge

**Status**: API exists (`GET /api/alerts/count`). Frontend: 0% (hook never created).  
**Work needed**:
- Create `orchestration/ui/src/hooks/usePriceAlerts.ts`:
  ```typescript
  export function usePriceAlertCount() {
    return useQuery({
      queryKey: ["alert-count"],
      queryFn: () => agnesApi.alertCount(),
      refetchInterval: 60_000, // refresh every minute
    });
  }
  ```
- In `TopBar.tsx`: import hook, show badge on a Bell icon if `count > 0`
- Badge style: red dot with count, pulse animation for new alerts

### F6: Citation Ledger

**Status**: Not built. Highest-impact missing feature for judging criteria #2 (evidence trails).

**Schema addition**:
```sql
CREATE TABLE IF NOT EXISTS Claim_Citation (
    Id              INTEGER PRIMARY KEY AUTOINCREMENT,
    OpportunityId   INTEGER NOT NULL,
    ClaimText       TEXT NOT NULL,
    SourceType      TEXT NOT NULL,  -- 'fda_iid'|'pubchem'|'dsld'|'supplier'|'openfda'|'compliance'
    SourceId        TEXT,           -- row ID or external identifier
    SourceUrl       TEXT,
    SourceSnippet   TEXT,           -- excerpt from source
    Confidence      REAL,
    CreatedAt       TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (OpportunityId) REFERENCES Consolidation_Opportunity(Id)
);
```

**Proposal writer change**: When writing `Proposal_Text`, also emit a JSON array of citations. The `proposal_generator.py` LLM prompt is augmented to request structured citation output alongside the narrative. Citations are parsed and written to `Claim_Citation`.

**API addition**: `GET /api/data/proposals/{id}/citations` → returns citation list for a proposal  
**Frontend**: Proposals view shows expandable "Evidence" section per proposal. Each citation shows type icon + snippet + confidence bar.

### F7: Refusal Panel

**Status**: `refusal_engine.py` is complete. Zero UI visibility.

**Approach**: Surface refusals as a view within the Proposals tab (not a separate tab — less effort, still impactful).

**Schema**: `Compliance_Outcome_4State` likely already written by `compliance_reasoner_tool.py`. Verify columns include `decision TEXT` (recommend/refuse/defer_human_review/insufficient_evidence).

**API addition**: `GET /api/data/refusals` → returns rows where `decision = 'refuse'` or `decision = 'defer_human_review'`, joined with canonical ingredient name and justification.

**Frontend**: In Proposals tab, below the opportunity list, a collapsible "Refused & Deferred" section. Each refusal card shows:
- What was evaluated (ingredient + context)
- Decision: `Refused` or `Deferred to Human Review`
- Reason: justification text
- What would unblock it: missing cert, low confidence, grade mismatch
- Confidence score

### F8: Demo Trap Fixtures

Four adversarial cases seeded in the DB that Agnes should correctly handle:

**Trap 1 — Vegan constraint**: Product `FG-iherb-71022` (Ultima Replenisher, Vegan certified). Magnesium Stearate from a bovine-source supplier. Agnes should refuse this substitution citing vegan constraint conflict.

**Trap 2 — Grade mismatch**: A cheaper supplier offers Vitamin E at 95% purity. BOM requires ≥99% USP grade. Agnes should flag grade downshift and refuse or defer.

**Trap 3 — Geographic compliance divergence**: An ingredient approved in US FDA IID but flagged in EU REACH. Proposal for a company selling in both jurisdictions should produce a jurisdiction-split recommendation.

**Trap 4 — Stale supplier data**: A supplier in `Supplier_Commercial` with `Last_Updated > 180 days`. Agnes should downgrade confidence and explicitly note staleness in the proposal narrative.

---

## 8. Technology Stack

### Backend
- **Python 3.12** — FastAPI 0.115+, asyncio, uvicorn
- **SQLite 3.45** — WAL journal mode, read-only URI connections for safety
- **Google ADK** — LlmAgent + InMemoryRunner + search_sub_agent (Gemini 2.5 Flash)
- **Anthropic SDK** — Claude Haiku (router, compliance), Claude Sonnet (proposals)
- **rapidfuzz** — fuzzy ingredient name matching (substitution graph, IID changelog)
- **dotenv** — environment variable management

### Frontend
- **React 18** + **TypeScript** + **Vite** (Bun build)
- **TanStack Query v5** — server state, cache invalidation
- **Tailwind CSS** + **shadcn/ui** — component library
- **Lucide React** — icon set
- **ElevenLabs SDK** — WebGL orb + TTS (voice pipeline)
- **EventSource** — SSE streaming for DAG node updates

### Database
- **SQLite** (`db_enriched.sqlite`) — 22 tables, WAL mode, ~50MB
- **orchestration.db** — separate SQLite for pipeline run state, event log, Agent_Log

### External APIs
| API | Use | Key |
|---|---|---|
| Anthropic | Proposals, compliance, routing | `ANTHROPIC_API_KEY` |
| Google (ADK) | Search sub-agent, Gemini agents | `GOOGLE_API_KEY` |
| ElevenLabs | TTS voice output | `VITE_ELEVENLABS_API_KEY` |
| NIH DSLD v9 | Ingredient enrichment | `DSLD_API_KEY` |
| PubChem PUG REST | CID/SMILES lookup | No key |
| OpenFDA | Adverse event counts | No key |

---

## 9. Configuration

### Environment Variables (`.env`)
```bash
# Backend (root .env)
ANTHROPIC_API_KEY=sk-...
GOOGLE_API_KEY=AIza...
DSLD_API_KEY=...
FDC_API_KEY=...
MOLPORT_API_KEY=...  # optional — Supplier_Commercial falls back to web search

# Frontend (orchestration/ui/.env)
VITE_AGNES_API_URL=http://95.216.146.149:8001  # remote server; use localhost:8000 for local dev
VITE_ELEVENLABS_API_KEY=sk_...
VITE_ELEVENLABS_VOICE_ID=EXAVITQu4vr4xnSDxMaL
```

### Port Note
The CLAUDE.md says start the server on `--port 8000`. The frontend `.env` currently points to `http://95.216.146.149:8001` (remote server). For local dev, set `VITE_AGNES_API_URL=http://localhost:8000` before building. The remote server configuration suggests a deployed instance exists — confirm this is still accessible for demo purposes.

### Security Scope
- In scope: Read-only SQLite connections for all GET endpoints; writable connections only for write paths
- In scope: CORS configured for `*` (dev mode; acceptable for hackathon)
- Out of scope: Auth, rate limiting, HTTPS termination

---

## 10. API Specification

### New/Missing Endpoints to Add

#### GET /api/data/regulatory-alerts *(exists in backend, needs Sidebar entry)*
```json
{
  "alerts": [{
    "change_id": 12,
    "ingredient_name": "Glycerin",
    "status": "C",
    "severity": "HIGH",
    "route": "ORAL",
    "dosage_form": "TABLET",
    "canonical_id": "23",
    "snapshots": [
      {"snapshot_date": "Q1 2026", "max_daily_exposure": "1600", "mde_uom": "mg"},
      {"snapshot_date": "Q2 2026", "max_daily_exposure": "1080", "mde_uom": "mg"}
    ]
  }],
  "count": 27
}
```

#### GET /api/data/proposals/{id}/citations *(new)*
```json
{
  "opportunity_id": 45,
  "citations": [{
    "claim_text": "Vitamin C MDE is 1,200 mg/day via oral route",
    "source_type": "fda_iid",
    "source_id": "7423",
    "source_snippet": "MaxDailyExposure: 1200, Unit: mg, Route: ORAL",
    "confidence": 0.92
  }],
  "count": 8
}
```

#### GET /api/data/refusals *(new)*
```json
{
  "refusals": [{
    "canonical_id": 55,
    "ingredient_name": "Magnesium Stearate",
    "decision": "refuse",
    "justification": "Bovine-source supplier conflicts with Vegan certification on 3 affected products",
    "confidence": 0.85,
    "blocking_factors": ["vegan_constraint_violation"],
    "unblock_hint": "Source plant-derived Magnesium Stearate supplier"
  }],
  "count": 12
}
```

#### Updated GET /api/data/compliance *(hierarchy expansion)*
```json
{
  "products": [{
    "product_id": "3",
    "product_name": "Ultima Replenisher Electrolyte Powder",
    "company": "Ultima Replenisher",
    "off_market": false,
    "certifications": {
      "Vegan": "implied",
      "Vegetarian": "derived",
      "NonGMO": "implied",
      "GlutenFree": "implied"
    }
  }]
}
```

---

## 11. Success Criteria

### MVP Definition
Agnes is demo-ready when a judge can navigate the UI for 5 minutes without seeing EmptyState, broken product names, or missing data — and when asked "How do you know?" can click through to source citations.

### Functional Requirements
- ✅ All 8 existing tabs show real data (no EmptyState in Opportunities, Ingredients, Compliance, Proposals, Suppliers, Alerts)
- ✅ Compliance matrix shows real company and product names, not iHerb SKU codes
- ✅ Vegan-certified products show Vegetarian as derived cert in compliance matrix
- ✅ Ingredient search returns common names, not IUPAC chemical names
- ✅ Proposals tab shows at least 10 proposals with `Proposal_Text` populated
- ✅ Regulatory Alerts tab exists in sidebar and shows FDA IID change alerts
- ✅ TopBar shows price alert badge count (0 = no badge; N>0 = red badge)
- ✅ Proposals include an expandable Citations/Evidence section
- ✅ Refused substitutions are visible in a Refusals panel
- ✅ Voice pipeline: speak → pipeline triggers → DAG renders → TTS responds
- ✅ All 7 pipelines runnable via API (no import errors, no registration gaps)

### Quality Indicators
- No TypeScript build errors (`bun run build` passes clean)
- No Python import errors for any registered agent/tool
- FastAPI health endpoint returns `{"status": "ok"}`
- SQLite integrity check passes on `db_enriched.sqlite`
- At minimum 10 proposals with citations and 5 refusal records for demo

### User Experience Goals
- A judge can find a consolidation proposal and trace a claim to a source in under 60 seconds
- A judge can ask Agnes via voice and see the DAG graph render in real time
- A judge can see Agnes refuse a bad substitution and explain why

---

## 12. Implementation Phases

### Phase 1: Data Execution (Day 1, ~2 hours)
**Goal**: Fill all empty tabs with real data.

Deliverables:
- ✅ Run `PYTHONPATH=. python3 reasoning/proposal_generator.py` → 123 proposal texts
- ✅ Run `PYTHONPATH=. python3 enrichment/backfill_supplier_web.py` → Supplier_Commercial populated
- ✅ Trigger `regulatory_drift_alert` pipeline via API → drift flags + narrative
- ✅ Trigger `price_monitor` pipeline twice → establishes price baselines
- ✅ Verify all tabs show data: Opportunities, Proposals, Suppliers, Alerts, Regulatory

Validation:
```bash
python3 -c "
import sqlite3
c = sqlite3.connect('db_enriched.sqlite')
print('Proposals:', c.execute('SELECT COUNT(*) FROM Consolidation_Opportunity WHERE Proposal_Text IS NOT NULL').fetchone()[0])
print('Suppliers:', c.execute('SELECT COUNT(*) FROM Supplier_Commercial').fetchone()[0])
print('Reg alerts:', c.execute('SELECT COUNT(*) FROM FDA_IID_Change_Log WHERE CanonicalIngredientId IS NOT NULL').fetchone()[0])
"
```

### Phase 2: Display Fixes (Day 1, ~3 hours)
**Goal**: All user-facing names are human-readable and correct.

Deliverables:
- ✅ Compliance API pivot applies certification hierarchy (Vegan→Vegetarian, Organic→NonGMO, NSF→cGMP, etc.)
- ✅ Compliance view Legend updated to show "Derived" status
- ✅ Ingredient API returns title-cased display names (all-caps FDA names normalized)
- ✅ `Product.DisplayName` column added; iHerb product name backfill script created and run
- ✅ Compliance view shows company + product display name instead of SKU code
- ✅ IngredientsView `display_name` updated to use normalized name

Validation:
- Compliance matrix: no `FG-iherb-*` visible
- Vegan products have Vegetarian = "derived" in API response
- No all-caps names in ingredient grid

### Phase 3: Missing UI + Notifications (Day 1-2, ~3 hours)
**Goal**: All built backend features have UI representation.

Deliverables:
- ✅ Regulatory Alerts tab added to Sidebar + Index.tsx
- ✅ `RegulatoryAlertsView.tsx` created with severity filter, before/after MDE, pipeline trigger CTA
- ✅ `usePriceAlerts.ts` hook created
- ✅ TopBar notification badge for price alerts wired
- ✅ Frontend built cleanly (`bun run build` passes)

Validation:
- Navigate to Regulatory tab: shows alerts grouped by severity
- TopBar shows badge if unread alerts exist
- `bun run build` exits 0

### Phase 4: Hackathon Features (Day 2, ~4 hours)
**Goal**: Add the three features that directly win on judging criteria.

Deliverables:
- ✅ `Claim_Citation` DB table migration created and run
- ✅ Proposal generator emits structured citations alongside narrative
- ✅ `GET /api/data/proposals/{id}/citations` endpoint added
- ✅ Proposals view shows expandable Evidence/Citations section per proposal
- ✅ `GET /api/data/refusals` endpoint returns compliance outcome refusals
- ✅ Refusals panel in Proposals tab shows refused substitutions with blocking factors
- ✅ 4 demo traps seeded as fixture data in the DB
- ✅ One end-to-end demo walk-through verified (voice → pipeline → DAG → TTS → proposal → citations)

Validation:
- Open Proposals tab: click any proposal, expand "Evidence" → see ≥3 citations
- Refusals panel: shows ≥1 refused recommendation with reason
- Voice: "Find consolidation opportunities for Vitamin C" → pipeline runs, DAG renders

---

## 13. Future Considerations

### Post-MVP Enhancements

**Red-team worker (S2 from Winningtools)**: Every proposal gets adversarially attacked before display. `red_team.py` (385 lines) exists in `local-dev/reasoning/` — needs migration + DAG wiring. Highest-impact post-MVP feature. Could be added during Phase 4 if time permits.

**Multimodal label/SDS ingestion (S1)**: Upload a product label image → Claude Vision extracts certification claims, allergen statements, CAS numbers → feeds into compliance reasoner. Needs vision model API key and `pdfplumber`. Huge demo moment for judges.

**Case memory + accept/reject learning (C4)**: `record_case()` writes accepted/rejected proposals to a `Case_Memory` table. Future proposals retrieve nearest-neighbor past decisions via RAG. The "improves over time" criterion made concrete.

**ReEvalDaemon**: Drains `Re_Eval_Queue`, supports 8 trigger classes (cert_expiring, price_shift, demand_shift, etc.). Full implementation exists in `local-dev/Orchestration/reeval_daemon.py`. Needs `Re_Eval_Queue` migration + async refactor + scheduling.

**Pareto tradeoff card (C1)**: Instead of ranking proposals by $ alone, show each on 4–5 axes (price Δ, lead time Δ, compliance risk, supplier concentration risk, geo-risk). Highlight Pareto-dominant choices. Pure data model change — no ML.

### Integration Opportunities

**Molport live integration**: `commercial_enricher.py` already has the wiring. When `MOLPORT_API_KEY` is available, Molport prices (Confidence=0.70) supplement Google Search prices (Confidence=0.65). No code change needed — just the key.

**Slack/email alert push**: Price alert and regulatory alert endpoints exist. A Make.com scenario or FastAPI background task on alert creation posts to Slack webhook or sends email summary. The dismiss endpoint is the natural counterpart.

**Certification registry scrapers**: USDA Organic Integrity Database, Non-GMO Project lookup, Kosher (OU/OK/Star-K) public cert listings. Per cert, cache last-checked date and expiry. Hooks into compliance reasoner as additional evidence sources.

---

## 14. Risks & Mitigations

### Risk 1: GOOGLE_API_KEY Not Available for Backfills
**Risk**: `backfill_supplier_web.py` and all Google Search-dependent pipelines fail if `GOOGLE_API_KEY` is absent.  
**Mitigation**: Check `.env` before starting Phase 1. If key is absent, the `supplier_fallback` demo mode exists — show the scoring UI with a smaller dataset. Label it clearly as demo data in the UI.

### Risk 2: iHerb Product Name Lookup Rate Limits
**Risk**: Scraping iHerb product names for 66 products may get rate-limited or blocked.  
**Mitigation**: Phase 2 "Pass A" (Company + ID format) is the immediate fallback that requires zero external calls. iHerb lookup is a nice-to-have, not blocking. If scraping fails, the company name is already real and readable.

### Risk 3: Proposal Generator LLM Cost / Time
**Risk**: `proposal_generator.py` makes Claude API calls for 123 opportunities. Could be slow (~10 min) or costly.  
**Mitigation**: Run top-50 only first (`--limit 50` flag if available). The top opportunities by Consolidation_Score are the ones shown in the demo. Verify `ANTHROPIC_API_KEY` is set before starting.

### Risk 4: Citation Ledger Requires Proposal Generator Rewrite
**Risk**: Adding structured citation output to `proposal_generator.py` changes the LLM prompt significantly. Could degrade proposal narrative quality.  
**Mitigation**: Implement citations as a post-processing pass: after the narrative is written, run a second Claude call that extracts claims from the narrative and matches them to DB source rows. This is additive and doesn't touch the existing prompt.

### Risk 5: Remote Server Port Mismatch
**Risk**: Frontend `.env` points to `http://95.216.146.149:8001` but CLAUDE.md says start on `--port 8000`. If the remote server is down or the port is wrong, the UI falls back to demo mode silently.  
**Mitigation**: Verify the remote server is running at port 8001. For local dev, rebuild the frontend with `VITE_AGNES_API_URL=http://localhost:8000`. Document the demo setup clearly — confirm which server (local vs. remote) will be used for the presentation.

---

## 15. Appendix

### Related Documents
- `Orchestration/To-Do/Winningtools.md` — Tier S/A/B/C/D feature ranking for hackathon
- `Orchestration/To-Do/missing-tools.md` — 5 missing DAG tools (ComputeLaneCost, QualifyCandidate, SupplierScorer, SendRfq, MapLogistics)
- `Orchestration/To-Do/missing-workers.md` — 3 missing agents (RedTeamAgent, ReEvalDaemon, Calibrator)
- `Orchestration/To-Do/session-summary-price-intelligence-and-product-vision.md` — Full prior session context
- `Orchestration/Plans/regulatory-drift-alerting-pipeline.md` — Detailed implementation plan (all code done)
- `Orchestration/Plans/supplier-price-intelligence-web-enrichment-monitor-alerts.md` — Detailed implementation plan (all code done)
- `Orchestration/Data/Spherecast/Overview.md` — Hackathon brief and judging criteria
- `CLAUDE.md` — Agent working reference: current system state, schema, arcs

### Current Pipeline Registry (7 pipelines)
```
supplier_fallout           — react to supplier disruption
proactive_consolidation    — find redundant suppliers + proposals
price_audit                — flag pricing outliers in portfolio
substitution_discovery     — search Molport/PubChem for alternatives
new_ingredient_research    — regulatory sweep for new ingredients
price_monitor              — fetch fresh prices, detect changes ≥15%
regulatory_drift_alert     — scan FDA IID change log, generate alerts
```

### Current Agent Registry (9 agents)
```
RouterAgent                — Claude Haiku: classifies chat → pipeline
ReactiveAgent              — Claude: responds to direct questions
ProactiveAgent             — Gemini: consolidation narrative
ResearchAgent              — Gemini: supplier discovery via Google Search
ProposalWriter             — Claude Sonnet: sourcing proposal text
PriceFetchAgent            — Python: compares prices, writes alerts
PriceAlertWriter           — Gemini: price change narrative
RegulatoryDriftAgent       — Gemini: FDA drift narrative
RegulatoryResearchAgent    — Gemini: live FDA change log search
```

### Data State at PRD Creation (2026-04-18)
```
Ingredient_Canonical:    250 rows
Consolidation_Opportunity: 123 rows (0 with Proposal_Text)
Product_Compliance:      126 rows (all Status='implied')
Supplier_Commercial:     0 rows (backfill not run)
Price_Change_Alert:      0 rows (pipeline not triggered)
FDA_Inactive_Ingredient: 9,067 rows (1,150 matched to canonicals)
FDA_IID_Change_Log:      187 rows (27 matched to canonicals)
Ingredient_Substitution: 32 edges
BOM_Component_Quantity:  515 rows
```

### Demo Checklist (Pre-Presentation)
```bash
# 1. Verify server is running
curl -s http://95.216.146.149:8001/health

# 2. Verify proposals populated
python3 -c "import sqlite3; c=sqlite3.connect('db_enriched.sqlite'); print(c.execute('SELECT COUNT(*) FROM Consolidation_Opportunity WHERE Proposal_Text IS NOT NULL').fetchone())"

# 3. Verify suppliers populated  
python3 -c "import sqlite3; c=sqlite3.connect('db_enriched.sqlite'); print(c.execute('SELECT COUNT(*) FROM Supplier_Commercial').fetchone())"

# 4. Test voice pipeline
# Open UI → Talk to Agnes tab → Say "Find consolidation opportunities for Vitamin C"

# 5. Verify DAG renders
# Should see the proactive_consolidation pipeline execute with live node status updates

# 6. Verify compliance matrix
# Navigate to Compliance → Verify Ultima Replenisher shows Vegetarian as derived cert
```
