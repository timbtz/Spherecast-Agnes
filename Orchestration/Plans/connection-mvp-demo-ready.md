# Feature: Connection — MVP Demo-Ready

> **Status as of 2026-04-18**: All code tasks (Tasks 4–17) are **complete** — all modified files are in git working tree. The remaining work is **data execution** (Tasks 1–3) and a **frontend rebuild** (Task 19). Read the Current Status section before starting.

---

## Current Status — What's Done vs. What's Remaining

### ✅ COMPLETE (code already in working tree)

| Task | What | File |
|---|---|---|
| Task 4 | Compliance hierarchy + product name fix | `data.py` lines 70–121 |
| Task 5 | Ingredient title-case `_normalize_name()` | `data.py` lines 42–67 |
| Task 6 | TypeScript types: Citation, Refusal, RegulatoryAlert | `types/agnes.ts` |
| Task 7 | API client: `proposalCitations()`, `refusals()`, `regulatoryAlerts()` | `agnesApi.ts` |
| Task 8 | Sidebar "regulatory" tab + ShieldAlert icon | `Sidebar.tsx` |
| Task 9 | Index.tsx TAB_TITLES + tab render dispatch | `Index.tsx` |
| Task 10 | RegulatoryAlertsView component | `RegulatoryAlertsView.tsx` (new file) |
| Task 11 | `usePriceAlertCount()` hook | `usePriceAlerts.ts` (new file) |
| Task 12 | TopBar Bell badge with alert count | `TopBar.tsx` |
| Task 13 | DB migration Claim_Citation + Refusal_Log + demo traps | `db_migrate_citation_refusal.py` (new file, already run) |
| Task 14 | compliance_reasoner_tool persists refusals to DB | `compliance_reasoner_tool.py` |
| Task 15 | `/api/data/proposals/{id}/citations` + `/api/data/refusals` endpoints | `data.py` lines 237–285 |
| Task 16 | Proposal generator extracts + stores citations | `proposal_generator.py` |
| Task 17 | ProposalsView: expandable Citations + Refusals panel | `ProposalsView.tsx` |

### 🔴 REMAINING (must complete before demo)

| Task | What | Blocker |
|---|---|---|
| Task 0 | Rebuild frontend (`bun run build`) | All new components need dist rebuild |
| Task 1 | Run `proposal_generator.py` | 0 proposals with text; citations need data |
| Task 2 | Run `backfill_supplier_web.py` | 0 Supplier_Commercial rows |
| Task 3 | Trigger `regulatory_drift_alert` + `price_monitor` pipelines | 0 Price_Change_Alert rows; drift flags unset |

**Correct execution order**: `bun run build` → `db_migrate_citation_refusal.py` (idempotent verify) → `proposal_generator.py` → `backfill_supplier_web.py` → trigger pipelines.

---

## Feature Description

Connect all architectural pieces of Agnes into a coherent, demo-ready product. The backend pipelines, 17 API endpoints, 9 agents, and enriched SQLite database are built but the data is not populated and several critical display issues make the system look broken. This plan executes the data pipeline, fixes product/ingredient display names, adds the Regulatory Alerts UI tab, wires the TopBar price badge, implements the Citation Ledger (hackathon judging criterion #2), and surfaces the Refusal Panel — so every tab shows real data and every claim is traceable.

## User Story

As a hackathon judge,  
I want to navigate Agnes for 5 minutes without seeing EmptyState or broken product names, click through to source citations from any proposal, and see Agnes refuse bad substitutions with explanations,  
So that I can validate Agnes's reasoning quality, evidence trails, and trustworthiness.

## Problem Statement

Agnes has all the intelligence but none of the demo readiness: 0 proposals generated, 0 supplier rows, all-caps ingredient names, compliance matrix showing `FG-iherb-10421` codes, no Regulatory tab in the UI, no citation ledger, and refusal engine outputs go nowhere visible.

## Solution Statement

Four sequential phases: (1) run existing scripts to populate real data; (2) fix display layer in the API without schema changes; (3) wire three missing UI surfaces (regulatory tab, price badge, refusal panel); (4) build citation ledger as the hackathon-defining evidence-trail feature.

## Feature Metadata

**Feature Type**: Enhancement + New Capability  
**Estimated Complexity**: Medium  
**Primary Systems Affected**: `orchestration/api/routes/data.py`, `reasoning/proposal_generator.py`, `orchestration/tools/compliance_reasoner_tool.py`, `orchestration/ui/src/` (Sidebar, TopBar, ProposalsView, new views/hooks)  
**Dependencies**: `ANTHROPIC_API_KEY` (proposals), `GOOGLE_API_KEY` (supplier backfill), Python 3.12, Bun

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ BEFORE IMPLEMENTING

- `orchestration/api/routes/data.py` (lines 1–207) — All read endpoints; `get_db()` pattern (lines 14–18) uses read-only URI; compliance pivot (lines 64–93) is the target for hierarchy expansion; ingredients endpoint (lines 42–61) is target for title-case fix; product name label at line 84 needs company+id fallback
- `orchestration/ui/src/components/layout/Sidebar.tsx` (lines 1–61) — `TabKey` union on line 5, `ITEMS` array on lines 7–16; add "regulatory" entry with `ShieldAlert` icon; `ShieldCheck` already imported, `ShieldAlert` is not
- `orchestration/ui/src/pages/Index.tsx` (lines 1–112) — `TAB_TITLES` dict lines 16–25; tab render dispatch lines 56–103; import block lines 1–14 for new view import
- `orchestration/ui/src/components/layout/TopBar.tsx` (lines 1–45) — no badge currently; needs Bell icon + count badge from hook
- `orchestration/ui/src/components/views/AlertsView.tsx` (lines 1–145) — **mirror this pattern** for `RegulatoryAlertsView.tsx`: useQuery + severity badges + empty state + card layout
- `orchestration/ui/src/components/views/ProposalsView.tsx` (lines 1–89) — proposal card layout; add expandable Citations + Refusals sections after footer
- `orchestration/ui/src/lib/agnesApi.ts` (lines 60–224) — `safeFetch<T>()` pattern (lines 41–58); add new methods following existing signatures at lines 140–187
- `orchestration/ui/src/types/agnes.ts` (lines 1–161) — `CertStatus` union on line 38; `ComplianceProduct` on lines 39–45; add "derived" to `CertStatus`, add `RegulatoryAlert`, `Citation`, `Refusal` interfaces
- `orchestration/ui/src/hooks/useApiHealth.ts` (lines 1–36) — hook pattern: `useEffect` + `setInterval` + `agnesStore`; mirror for `usePriceAlerts.ts`
- `reasoning/proposal_generator.py` (lines 137–216) — `_generate_proposal()` is the LLM call (lines 177–195); `_store_proposal()` at lines 197–216 writes to `Consolidation_Opportunity.Proposal_JSON` — add citation extraction as a **second Claude call** after the narrative
- `reasoning/refusal_engine.py` (lines 1–119) — `_persist()` is no-op'd (lines 46–55); decisions are `refuse_gate_fail`, `refuse_compliance`, `refuse_low_confidence`, `defer_human_review`, `recommend`
- `orchestration/tools/compliance_reasoner_tool.py` (lines 28–135) — `run(ctx)` returns structured dict with `outcome`, `compound_confidence`, `qualified`, `canonical_id`, `ingredient_name`; add DB persistence here for `refuse`/`defer_human_review` outcomes

### New Files to Create

- `enrichment/db_migrate_citation_refusal.py` — Migration: `Claim_Citation` table + `Refusal_Log` table + 4 demo trap seeds
- `orchestration/ui/src/components/views/RegulatoryAlertsView.tsx` — Regulatory alerts tab (modeled on AlertsView.tsx)
- `orchestration/ui/src/hooks/usePriceAlerts.ts` — Hook: polls `/api/alerts/count` every 60s

### Patterns to Follow

**Backend read endpoint pattern** (`data.py`):
```python
@router.get("/my-endpoint")
def my_endpoint():
    with get_db() as db:
        rows = db.execute("SELECT ... FROM ... WHERE ...").fetchall()
    return {"items": [dict(r) for r in rows], "count": len(rows)}
```

**React query hook pattern** (`useApiHealth.ts` mirror):
```typescript
export function usePriceAlertCount() {
  return useQuery({
    queryKey: ["alert-count"],
    queryFn: () => agnesApi.alertCount(),
    refetchInterval: 60_000,
  });
}
```

**Frontend view component pattern** (`AlertsView.tsx` mirror):
```typescript
export function RegulatoryAlertsView() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["regulatory-alerts"],
    queryFn: () => agnesApi.regulatoryAlerts(),
  });
  if (isLoading) return <LoadingState label="Loading alerts…" />;
  if (error) return <ErrorState message="Failed to load regulatory alerts." />;
  if (!data?.alerts?.length) return <EmptyState ... />;
  return <div className="space-y-3">...</div>;
}
```

**Compliance hierarchy rule application** (apply after the pivot loop in `data.py:compliance()`):
```python
CERT_IMPLICATIONS = {
    "Vegan": ["Vegetarian"],
    "Organic": ["NonGMO"],
    "NSF": ["cGMP"],
    "InformedSport": ["cGMP"],
    "USP": ["cGMP"],
}
for prod in products.values():
    certs = prod["certifications"]
    for source_cert, implied_certs in CERT_IMPLICATIONS.items():
        if source_cert in certs:
            for implied in implied_certs:
                if implied not in certs:
                    certs[implied] = "derived"
```

**Product name display (no iHerb scraping needed)**:
```python
# In compliance pivot, replace line 84:
sku = r["product_name"] or ""
if sku.startswith("FG-iherb-"):
    product_id_num = sku.replace("FG-iherb-", "")
    display = f"{r['company']} #{product_id_num}"
else:
    display = sku or f"{r['company']} Product {pid}"
```

**Ingredient title-case fix** (in `data.py:ingredients()`, line 46):
```python
raw_name = r["display_name"] or ""
display_name = raw_name.title() if raw_name.isupper() else raw_name
```

---

## IMPLEMENTATION PLAN

### Phase 1: Data Execution

Run the existing enrichment scripts to populate all empty tabs with real data.

**Tasks:**
- Run proposal generator (123 proposals, top-50 first)
- Run supplier web backfill (requires GOOGLE_API_KEY)
- Trigger regulatory drift pipeline via API
- Trigger price monitor pipeline twice (establish baselines then detect changes)

### Phase 2: Backend Display Fixes

Fix product names, ingredient names, and compliance hierarchy in the API layer — no DB migrations.

**Tasks:**
- Apply product name fallback (`company #id` format) in compliance pivot
- Apply CERT_IMPLICATIONS dict after compliance pivot
- Apply title-case normalization for all-caps ingredient names
- Add `"derived"` to `CertStatus` union in `agnes.ts`

### Phase 3: Missing UI + Notifications

Wire the three missing frontend surfaces.

**Tasks:**
- Add "regulatory" tab to Sidebar + Index (TabKey, ITEMS, TAB_TITLES, render dispatch)
- Create `RegulatoryAlertsView.tsx`
- Create `usePriceAlerts.ts` hook
- Add Bell + badge to TopBar

### Phase 4: Hackathon Features

Citation Ledger + Refusal Panel + demo traps.

**Tasks:**
- DB migration for `Claim_Citation` + `Refusal_Log` + demo trap seeds
- Update `proposal_generator.py` with citation extraction (second Claude call)
- Update `compliance_reasoner_tool.py` to persist refusals to `Refusal_Log`
- Add `/api/data/proposals/{id}/citations` endpoint
- Add `/api/data/refusals` endpoint
- Update `agnesApi.ts` with new methods + types
- Update `ProposalsView.tsx` with expandable Citations + Refusals sections
- Run migration + proposal generator for citations

---

## STEP-BY-STEP TASKS

### TASK 1 — Run proposal generator

- **IMPLEMENT**: Generate top-50 proposals. Run from project root.
- **VALIDATE**: `PYTHONPATH=. python3 reasoning/proposal_generator.py`
- **CHECK**: `python3 -c "import sqlite3; c=sqlite3.connect('db_enriched.sqlite'); print(c.execute('SELECT COUNT(*) FROM Consolidation_Opportunity WHERE Proposal_Text IS NOT NULL').fetchone())"`
- **EXPECTED**: `(50,)` or more

---

### TASK 2 — Run supplier web backfill

- **IMPLEMENT**: Populate `Supplier_Commercial` via Google Search agent.
- **GOTCHA**: Requires `GOOGLE_API_KEY` in `.env`. If absent, skip and note in demo.
- **VALIDATE**: `PYTHONPATH=. python3 enrichment/backfill_supplier_web.py`
- **CHECK**: `python3 -c "import sqlite3; c=sqlite3.connect('db_enriched.sqlite'); print(c.execute('SELECT COUNT(*) FROM Supplier_Commercial').fetchone())"`

---

### TASK 3 — Trigger regulatory and price pipelines

- **IMPLEMENT**: Trigger via FastAPI (server must be running on port 8000).
- **VALIDATE**:
  ```bash
  curl -s -X POST http://localhost:8000/pipelines/run/regulatory_drift_alert | python3 -m json.tool
  curl -s -X POST http://localhost:8000/pipelines/run/price_monitor | python3 -m json.tool
  sleep 30
  curl -s -X POST http://localhost:8000/pipelines/run/price_monitor | python3 -m json.tool
  ```

---

### TASK 4 — UPDATE `orchestration/api/routes/data.py` — compliance hierarchy + product name fix

- **PATTERN**: `data.py:64–93` — compliance pivot function
- **IMPLEMENT**: Three changes to the `compliance()` function:
  1. After line 90 (`cert_status = ...`), change product_name assignment to use company+id fallback for FG-iherb-* SKUs
  2. After the `for r in rows` loop (after line 91), apply CERT_IMPLICATIONS
  3. Change return from `list(products.values())` to wrap in `{"products": ..., "count": ...}`

Exact change to `data.py`:

**Replace** lines 64–93 with:
```python
CERT_IMPLICATIONS = {
    "Vegan": ["Vegetarian"],
    "Organic": ["NonGMO"],
    "NSF": ["cGMP"],
    "InformedSport": ["cGMP"],
    "USP": ["cGMP"],
}

@router.get("/compliance")
def compliance():
    with get_db() as db:
        rows = db.execute("""
            SELECT pc.ProductId as product_id, p.SKU as product_name, c.Name as company,
                   pc.Certification as cert_type, pc.Status as status,
                   pc.Off_Market_Warning as off_market_warning
            FROM Product_Compliance pc
            JOIN Product p ON p.Id = pc.ProductId
            JOIN Company c ON c.Id = p.CompanyId
            ORDER BY c.Name, p.SKU
        """).fetchall()

    products: dict[int, dict] = {}
    for r in rows:
        pid = r["product_id"]
        if pid not in products:
            sku = r["product_name"] or ""
            if sku.startswith("FG-iherb-"):
                display = f"{r['company']} #{sku.replace('FG-iherb-', '')}"
            else:
                display = sku or f"{r['company']} Product {pid}"
            products[pid] = {
                "product_id": str(pid),
                "product_name": display,
                "company": r["company"],
                "off_market": bool(r["off_market_warning"]),
                "certifications": {},
            }
        status = r["status"] or "implied"
        cert_status = "certified" if status == "confirmed" else status if status == "derived" else "implied"
        products[pid]["certifications"][r["cert_type"]] = cert_status

    # Apply hierarchy implications
    for prod in products.values():
        certs = prod["certifications"]
        for source_cert, implied_certs in CERT_IMPLICATIONS.items():
            if source_cert in certs:
                for implied in implied_certs:
                    if implied not in certs:
                        certs[implied] = "derived"

    result = list(products.values())
    return {"products": result, "count": len(result)}
```

- **GOTCHA**: `agnesApi.ts:compliance()` line 146 already handles both array and `{products: ...}` responses — no change needed there
- **VALIDATE**: `curl -s http://localhost:8000/api/data/compliance | python3 -c "import sys,json; d=json.load(sys.stdin); p=d['products'][0]; print(p['product_name'], p['certifications'])"`

---

### TASK 5 — UPDATE `orchestration/api/routes/data.py` — ingredient title-case

- **PATTERN**: `data.py:42–61` — ingredients endpoint
- **IMPLEMENT**: In the list comprehension at line 61, normalize all-caps names using `.title()`.

Replace the return at line 61:
```python
def _normalize_name(name: str | None) -> str:
    if not name:
        return ""
    return name.title() if name.isupper() else name

# In the return:
return [{**dict(r), "display_name": _normalize_name(r["display_name"])} for r in rows]
```

Add `_normalize_name` as a module-level helper before the router endpoints (after line 18).

- **VALIDATE**: `curl -s "http://localhost:8000/api/data/ingredients" | python3 -c "import sys,json; d=json.load(sys.stdin); print([x['display_name'] for x in d[:5]])"`
- **EXPECTED**: No all-caps names like `ASCORBYL PALMITATE`

---

### TASK 6 — UPDATE `orchestration/ui/src/types/agnes.ts` — add new types

- **PATTERN**: `agnes.ts:38` — existing `CertStatus` union
- **IMPLEMENT**: Add "derived" to CertStatus; add `RegulatoryAlert`, `Citation`, `Refusal` interfaces

Replace line 38:
```typescript
export type CertStatus = "certified" | "implied" | "derived" | "none";
```

Add after line 161 (end of file):
```typescript
export interface RegulatoryAlert {
  change_id: number;
  ingredient_name: string;
  status: string;
  route: string | null;
  dosage_form: string | null;
  canonical_id: string;
  grade: string | null;
  opportunity_id: string | null;
  consolidation_score: number | null;
  regulatory_drift_flag: boolean;
  regulatory_drift_reason: string | null;
  snapshots: Array<{
    snapshot_date: string;
    max_potency: number | null;
    max_daily_exposure: number | null;
    mde_uom: string | null;
  }>;
}

export interface Citation {
  id: number;
  opportunity_id: number;
  claim_text: string;
  source_type: string;
  source_id: string | null;
  source_url: string | null;
  source_snippet: string | null;
  confidence: number | null;
  created_at: string;
}

export interface Refusal {
  id: number;
  canonical_id: number;
  ingredient_name: string;
  decision: string;
  justification: string;
  confidence: number;
  blocking_factors: string[];
  unblock_hint: string;
  created_at: string;
}
```

- **VALIDATE**: `cd orchestration/ui && bun run tsc --noEmit 2>&1 | head -20`

---

### TASK 7 — UPDATE `orchestration/ui/src/lib/agnesApi.ts` — add new API methods

- **PATTERN**: `agnesApi.ts:178–187` — existing `alertCount()` and `listAlerts()` methods
- **ADD** three new methods after `dismissAlert()` (line 187):

```typescript
async regulatoryAlerts(): Promise<{ alerts: RegulatoryAlert[]; count: number }> {
  return safeFetch<{ alerts: RegulatoryAlert[]; count: number }>("/api/data/regulatory-alerts", undefined, { alerts: [], count: 0 });
},

async proposalCitations(opportunityId: string): Promise<{ citations: Citation[]; count: number }> {
  return safeFetch<{ citations: Citation[]; count: number }>(`/api/data/proposals/${opportunityId}/citations`, undefined, { citations: [], count: 0 });
},

async refusals(): Promise<{ refusals: Refusal[]; count: number }> {
  return safeFetch<{ refusals: Refusal[]; count: number }>("/api/data/refusals", undefined, { refusals: [], count: 0 });
},
```

- **ADD** import at top of file: `import type { ..., RegulatoryAlert, Citation, Refusal } from "@/types/agnes";`
- **VALIDATE**: `cd orchestration/ui && bun run tsc --noEmit 2>&1 | head -20`

---

### TASK 8 — UPDATE `orchestration/ui/src/components/layout/Sidebar.tsx` — regulatory tab

- **PATTERN**: `Sidebar.tsx:1–16` — TabKey union, imports, ITEMS array
- **IMPLEMENT**: Three changes:
  1. Add `ShieldAlert` to lucide-react import on line 1
  2. Add `"regulatory"` to `TabKey` union on line 5
  3. Add regulatory entry to `ITEMS` array after "alerts" (line 15)

Replace line 1:
```typescript
import { TrendingUp, FlaskConical, ShieldCheck, ShieldAlert, FileText, Workflow, Mic, Package, Bell } from "lucide-react";
```

Replace line 5:
```typescript
export type TabKey = "agnes" | "opportunities" | "ingredients" | "compliance" | "proposals" | "runs" | "suppliers" | "alerts" | "regulatory";
```

After line 15 (`{ key: "alerts", label: "Price Alerts", icon: Bell },`), add:
```typescript
  { key: "regulatory", label: "Regulatory", icon: ShieldAlert },
```

- **VALIDATE**: `cd orchestration/ui && bun run tsc --noEmit 2>&1 | head -20`

---

### TASK 9 — UPDATE `orchestration/ui/src/pages/Index.tsx` — wire regulatory tab

- **PATTERN**: `Index.tsx:1–25` — imports, TAB_TITLES
- **IMPLEMENT**: Three changes:
  1. Add import for `RegulatoryAlertsView` after line 12
  2. Add "regulatory" to `TAB_TITLES` after "alerts" entry (line 24)
  3. Add tab render case after line 102

Add to imports (after line 12):
```typescript
import { RegulatoryAlertsView } from "@/components/views/RegulatoryAlertsView";
```

Add to TAB_TITLES (after "alerts" entry on line 24):
```typescript
  regulatory: { title: "Regulatory Alerts", subtitle: "FDA IID changes affecting portfolio ingredients — proactive compliance risk monitoring." },
```

Replace line 102 (`  : tab === "runs" ? <PipelineRunsView />`):
```typescript
              : tab === "runs" ? <PipelineRunsView />
              : tab === "regulatory" ? <RegulatoryAlertsView />
```

- **VALIDATE**: `cd orchestration/ui && bun run tsc --noEmit 2>&1 | head -20`

---

### TASK 10 — CREATE `orchestration/ui/src/components/views/RegulatoryAlertsView.tsx`

- **PATTERN**: Mirror `AlertsView.tsx` structure (lines 1–145) for severity badges, query, empty state, card layout
- **IMPLEMENT**:

```typescript
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ShieldAlert, TriangleAlert, ChevronDown, ChevronUp } from "lucide-react";
import { agnesApi } from "@/lib/agnesApi";
import type { RegulatoryAlert } from "@/types/agnes";
import { LoadingState, EmptyState, ErrorState } from "@/components/shared/States";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const SEVERITY_STYLES = {
  HIGH: "bg-red-500/10 border-red-500/30 text-red-500",
  MEDIUM: "bg-amber-500/10 border-amber-500/30 text-amber-500",
  LOW: "bg-blue-500/10 border-blue-500/30 text-blue-500",
};

function getSeverity(alert: RegulatoryAlert): "HIGH" | "MEDIUM" | "LOW" {
  if (alert.status === "D") return "HIGH";
  const snapshots = alert.snapshots;
  if (snapshots.length >= 2) {
    const latest = snapshots[snapshots.length - 1].max_daily_exposure;
    const prior = snapshots[0].max_daily_exposure;
    if (latest != null && prior != null && prior > 0) {
      const drop = (prior - latest) / prior;
      if (drop > 0.3) return "HIGH";
      if (drop > 0.1) return "MEDIUM";
    }
  }
  return "LOW";
}

export function RegulatoryAlertsView() {
  const [severityFilter, setSeverityFilter] = useState<string>("ALL");
  const qc = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ["regulatory-alerts"],
    queryFn: () => agnesApi.regulatoryAlerts(),
  });

  const runPipeline = useMutation({
    mutationFn: () => agnesApi.runPipeline("regulatory_drift_alert" as any),
    onSuccess: () => {
      setTimeout(() => qc.invalidateQueries({ queryKey: ["regulatory-alerts"] }), 5000);
    },
  });

  if (isLoading) return <LoadingState label="Loading regulatory alerts…" />;
  if (error) return <ErrorState message="Failed to load regulatory alerts." />;

  if (!data?.alerts?.length) {
    return (
      <EmptyState
        icon={<ShieldAlert className="size-4" />}
        title="No regulatory alerts"
        body="Run the regulatory_drift_alert pipeline to scan for FDA IID changes."
      >
        <Button size="sm" onClick={() => runPipeline.mutate()} disabled={runPipeline.isPending}>
          {runPipeline.isPending ? "Running…" : "Run Pipeline"}
        </Button>
      </EmptyState>
    );
  }

  const filtered = severityFilter === "ALL"
    ? data.alerts
    : data.alerts.filter(a => getSeverity(a) === severityFilter);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-[12px] text-muted-foreground">{data.count} alert{data.count !== 1 ? "s" : ""}</p>
        <div className="flex items-center gap-2">
          {["ALL", "HIGH", "MEDIUM", "LOW"].map(s => (
            <button
              key={s}
              onClick={() => setSeverityFilter(s)}
              className={cn(
                "text-[11px] px-2 py-0.5 rounded font-medium border transition-colors",
                severityFilter === s ? "bg-primary text-primary-foreground border-primary" : "border-border text-muted-foreground hover:border-foreground/30"
              )}
            >{s}</button>
          ))}
          <Button size="sm" variant="outline" onClick={() => runPipeline.mutate()} disabled={runPipeline.isPending}>
            {runPipeline.isPending ? "Running…" : "Refresh"}
          </Button>
        </div>
      </div>

      {filtered.map(alert => (
        <RegulatoryAlertCard key={`${alert.change_id}-${alert.route}`} alert={alert} severity={getSeverity(alert)} />
      ))}
    </div>
  );
}

function RegulatoryAlertCard({ alert, severity }: { alert: RegulatoryAlert; severity: "HIGH" | "MEDIUM" | "LOW" }) {
  const [expanded, setExpanded] = useState(false);
  const statusLabel = alert.status === "C" ? "Corrected" : alert.status === "D" ? "Deleted" : "Revised";
  const snapshots = alert.snapshots;

  return (
    <div className={cn("rounded-lg border p-4 space-y-2", SEVERITY_STYLES[severity])}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[13px] font-semibold">{alert.ingredient_name}</span>
            <span className={cn("text-[10px] uppercase px-1.5 py-0.5 rounded font-semibold border", SEVERITY_STYLES[severity])}>
              {severity}
            </span>
            <span className="text-[10px] uppercase px-1.5 py-0.5 rounded border border-border text-muted-foreground">
              {statusLabel}
            </span>
          </div>
          {alert.route && (
            <p className="text-[11px] text-muted-foreground mt-0.5 font-mono">
              {alert.route} · {alert.dosage_form}
            </p>
          )}
        </div>
        <button onClick={() => setExpanded(e => !e)} className="text-muted-foreground hover:text-foreground shrink-0">
          {expanded ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
        </button>
      </div>

      {snapshots.length >= 2 && (
        <div className="flex items-center gap-3 text-[12px] font-mono">
          <span className="text-muted-foreground">{snapshots[0].snapshot_date}:</span>
          <span>{snapshots[0].max_daily_exposure ?? "–"} {snapshots[0].mde_uom}</span>
          <span className="text-muted-foreground">→</span>
          <span className="text-muted-foreground">{snapshots[snapshots.length - 1].snapshot_date}:</span>
          <span>{snapshots[snapshots.length - 1].max_daily_exposure ?? "–"} {snapshots[snapshots.length - 1].mde_uom}</span>
        </div>
      )}

      {expanded && alert.regulatory_drift_reason && (
        <p className="text-[12px] text-foreground/80 leading-relaxed border-t border-inherit pt-2 mt-2">
          {alert.regulatory_drift_reason}
        </p>
      )}
    </div>
  );
}
```

- **GOTCHA**: `EmptyState` component may not accept children — check `orchestration/ui/src/components/shared/States.tsx` first. If it doesn't, use a wrapper div with button after the EmptyState.
- **VALIDATE**: `cd orchestration/ui && bun run tsc --noEmit 2>&1 | head -20`

---

### TASK 11 — CREATE `orchestration/ui/src/hooks/usePriceAlerts.ts`

- **PATTERN**: `useApiHealth.ts:1–36` — hook pattern with useQuery
- **IMPLEMENT**:

```typescript
import { useQuery } from "@tanstack/react-query";
import { agnesApi } from "@/lib/agnesApi";

export function usePriceAlertCount() {
  return useQuery({
    queryKey: ["alert-count"],
    queryFn: () => agnesApi.alertCount(),
    refetchInterval: 60_000,
  });
}
```

- **VALIDATE**: `cd orchestration/ui && bun run tsc --noEmit 2>&1 | head -20`

---

### TASK 12 — UPDATE `orchestration/ui/src/components/layout/TopBar.tsx` — price alert badge

- **PATTERN**: `TopBar.tsx:1–45` — import block + component body
- **IMPLEMENT**: Add Bell icon with badge count

Replace the entire file with:
```typescript
import { useQuery } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { useApiHealth } from "@/hooks/useApiHealth";
import { agnesApi } from "@/lib/agnesApi";
import { SpherecastWordmark } from "@/components/brand/SpherecastMark";
import { cn } from "@/lib/utils";

export function TopBar() {
  const { apiOnline, mode, toggleMode } = useApiHealth();
  const { data: alertData } = useQuery({
    queryKey: ["alert-count"],
    queryFn: () => agnesApi.alertCount(),
    refetchInterval: 60_000,
    enabled: apiOnline,
  });
  const alertCount = alertData?.count ?? 0;

  return (
    <header className="h-12 shrink-0 border-b border-border flex items-center justify-between px-5 bg-background/80 backdrop-blur-sm relative z-20">
      <div className="flex items-center gap-2.5">
        <SpherecastWordmark height={20} className="text-foreground" />
        <span className="text-muted-foreground text-[13px] mx-1">/</span>
        <span className="text-muted-foreground text-[13px] font-medium">Agnes</span>
      </div>

      <div className="flex items-center gap-3">
        {alertCount > 0 && (
          <div className="relative">
            <Bell className="size-4 text-muted-foreground animate-status-pulse" strokeWidth={2} />
            <span className="absolute -top-1.5 -right-1.5 size-4 rounded-full bg-red-500 text-white text-[9px] font-bold flex items-center justify-center leading-none">
              {alertCount > 9 ? "9+" : alertCount}
            </span>
          </div>
        )}

        <button
          onClick={toggleMode}
          className={cn(
            "pill border transition-colors",
            mode === "live"
              ? "bg-status-completed/10 text-status-completed border-status-completed/20 hover:bg-status-completed/15"
              : "bg-status-skipped/10 text-status-skipped border-status-skipped/30 hover:bg-status-skipped/20",
          )}
          title="Toggle live ↔ demo data"
        >
          {mode === "live" ? "Live data" : "Demo mode"}
        </button>

        <div className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
          <span
            className={cn(
              "size-1.5 rounded-full",
              apiOnline ? "bg-status-completed animate-status-pulse" : "bg-status-failed",
            )}
          />
          <span>Agnes API</span>
          <span className="text-muted-foreground/60 font-mono text-[11px] ml-1">
            {new URL(agnesApi.apiUrl).host}
          </span>
        </div>
      </div>
    </header>
  );
}
```

- **VALIDATE**: `cd orchestration/ui && bun run tsc --noEmit 2>&1 | head -20`

---

### TASK 13 — CREATE `enrichment/db_migrate_citation_refusal.py` — new tables + demo traps

- **PATTERN**: `enrichment/db_migrate_fda_scoring.py` — idempotent migration with `IF NOT EXISTS`
- **IMPLEMENT**:

```python
"""Idempotent migration: Claim_Citation + Refusal_Log tables + 4 demo trap seeds."""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB = ROOT / "db_enriched.sqlite"


def migrate(db_path: Path = DB) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS Claim_Citation (
            Id              INTEGER PRIMARY KEY AUTOINCREMENT,
            OpportunityId   INTEGER NOT NULL,
            ClaimText       TEXT NOT NULL,
            SourceType      TEXT NOT NULL,
            SourceId        TEXT,
            SourceUrl       TEXT,
            SourceSnippet   TEXT,
            Confidence      REAL,
            CreatedAt       TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (OpportunityId) REFERENCES Consolidation_Opportunity(Id)
        );

        CREATE TABLE IF NOT EXISTS Refusal_Log (
            Id              INTEGER PRIMARY KEY AUTOINCREMENT,
            CanonicalId     INTEGER NOT NULL,
            IngredientName  TEXT NOT NULL,
            Decision        TEXT NOT NULL,
            Justification   TEXT,
            Confidence      REAL,
            BlockingFactors TEXT,
            UnblockHint     TEXT,
            RunId           TEXT,
            CreatedAt       TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_claim_citation_opp ON Claim_Citation(OpportunityId);
        CREATE INDEX IF NOT EXISTS idx_refusal_canonical ON Refusal_Log(CanonicalId);
    """)

    # Seed 4 demo traps (idempotent — only insert if no rows exist)
    existing = conn.execute("SELECT COUNT(*) FROM Refusal_Log").fetchone()[0]
    if existing == 0:
        traps = [
            # Trap 1: Vegan constraint — Magnesium Stearate bovine source
            (None, "Magnesium Stearate", "refuse",
             "Bovine-source Magnesium Stearate conflicts with Vegan certification on 3 affected products (Ultima Replenisher product line). Supplier's animal-derived origin cannot satisfy vegan constraint.",
             0.91, '["vegan_constraint_violation"]',
             "Source plant-derived Magnesium Stearate (e.g. palm-free vegetable grade). Verify supplier origin documentation before substitution.", None),
            # Trap 2: Grade mismatch — Vitamin E purity
            (None, "Vitamin E", "refuse",
             "Proposed supplier offers 95% purity Vitamin E. BOM specifies ≥99% USP grade. Grade downshift cannot be accepted without reformulation review by quality team.",
             0.87, '["grade_mismatch","purity_below_spec"]',
             "Source USP-verified Vitamin E at ≥99% purity. Obtain certificate of analysis confirming USP compliance before resubmitting.", None),
            # Trap 3: Geographic compliance divergence — ingredient approved US but flagged EU
            (None, "Titanium Dioxide", "defer_human_review",
             "Ingredient approved under US FDA IID (oral route). EU REACH restriction RE-2022/63 flags nano-form Titanium Dioxide in food-grade applications. Companies with EU market exposure require jurisdiction-specific review.",
             0.72, '["jurisdiction_divergence","eu_reach_flag"]',
             "Obtain EU-compliant non-nano grade with particle size certification. Human review required to confirm EU market exposure for affected product lines.", None),
            # Trap 4: Stale supplier data
            (None, "Ascorbic Acid", "defer_human_review",
             "Primary recommended supplier last updated 247 days ago (exceeds 180-day staleness threshold). Pricing confidence downgraded to 0.45. Proposal narrative should not rely on stale price as a savings estimate.",
             0.45, '["stale_supplier_data"]',
             "Re-run price_monitor pipeline to refresh supplier pricing. Confidence will restore to 0.65+ after successful web price fetch.", None),
        ]
        # Find canonical IDs for the trap ingredients
        name_to_id = {}
        for (_, ing_name, *_rest) in traps:
            row = conn.execute(
                "SELECT Id FROM Ingredient_Canonical WHERE Name LIKE ? LIMIT 1",
                (f"%{ing_name.split()[0]}%",)
            ).fetchone()
            if row:
                name_to_id[ing_name] = row[0]

        for (can_id, ing_name, decision, justification, confidence, blocking, unblock, run_id) in traps:
            resolved_id = name_to_id.get(ing_name) or can_id or 1
            conn.execute(
                """INSERT INTO Refusal_Log
                   (CanonicalId, IngredientName, Decision, Justification, Confidence,
                    BlockingFactors, UnblockHint, RunId)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (resolved_id, ing_name, decision, justification, confidence, blocking, unblock, run_id)
            )
        print(f"Seeded {len(traps)} demo trap refusals")

    conn.commit()
    conn.close()
    print("Migration complete: Claim_Citation + Refusal_Log")


if __name__ == "__main__":
    migrate()
```

- **VALIDATE**: `PYTHONPATH=. python3 enrichment/db_migrate_citation_refusal.py`
- **CHECK**: `python3 -c "import sqlite3; c=sqlite3.connect('db_enriched.sqlite'); print('Citations:', c.execute('SELECT COUNT(*) FROM Claim_Citation').fetchone()); print('Refusals:', c.execute('SELECT COUNT(*) FROM Refusal_Log').fetchone())"`
- **EXPECTED**: `Citations: (0,)  Refusals: (4,)`

---

### TASK 14 — UPDATE `orchestration/tools/compliance_reasoner_tool.py` — persist refusals

- **PATTERN**: `compliance_reasoner_tool.py:121–135` — return block at the end of `run()`
- **IMPLEMENT**: Before the `return` block (after line 119), add persistence for refuse/defer decisions:

After line 119 (`logger.warning(...)` inside except), before `return`:
```python
    # Persist refuse/defer decisions to Refusal_Log for UI visibility
    if outcome in ("refuse", "human-review") or not above_floor:
        decision_label = (
            "refuse" if outcome == "refuse" else
            "defer_human_review" if outcome == "human-review" else
            "refuse_low_confidence"
        )
        try:
            wconn = sqlite3.connect(str(ctx.enriched_db_path))
            justification = (comp_result.result or {}).get("reason", "Compliance check failed")
            blocking = []
            if outcome == "refuse":
                blocking.append("compliance_refuse")
            if not above_floor:
                blocking.append(f"low_confidence:{comp_confidence:.2f}")
            wconn.execute(
                """INSERT OR IGNORE INTO Refusal_Log
                   (CanonicalId, IngredientName, Decision, Justification,
                    Confidence, BlockingFactors, UnblockHint, RunId)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    canonical_id, ingredient_name, decision_label, justification,
                    comp_confidence, str(blocking),
                    "Provide missing compliance data or run with updated certifications.",
                    getattr(ctx, "run_id", None),
                )
            )
            wconn.commit()
            wconn.close()
        except Exception as persist_err:
            logger.warning(f"Refusal persistence failed: {persist_err}")
```

- **GOTCHA**: The `Refusal_Log` table must exist before this runs — run TASK 13 first
- **VALIDATE**: `PYTHONPATH=. python3 -c "from orchestration.tools import compliance_reasoner_tool; print('import ok')"`

---

### TASK 15 — UPDATE `orchestration/api/routes/data.py` — add 3 new endpoints

Add after the existing `get_regulatory_alerts()` endpoint (after line 206):

```python
@router.get("/proposals/{opportunity_id}/citations")
def proposal_citations(opportunity_id: int):
    with get_db() as db:
        rows = db.execute(
            """SELECT Id as id, OpportunityId as opportunity_id,
                      ClaimText as claim_text, SourceType as source_type,
                      SourceId as source_id, SourceUrl as source_url,
                      SourceSnippet as source_snippet, Confidence as confidence,
                      CreatedAt as created_at
               FROM Claim_Citation
               WHERE OpportunityId = ?
               ORDER BY Id""",
            (opportunity_id,),
        ).fetchall()
    return {"opportunity_id": opportunity_id, "citations": [dict(r) for r in rows], "count": len(rows)}


@router.get("/refusals")
def get_refusals():
    with get_db() as db:
        rows = db.execute(
            """SELECT Id as id, CanonicalId as canonical_id,
                      IngredientName as ingredient_name, Decision as decision,
                      Justification as justification, Confidence as confidence,
                      BlockingFactors as blocking_factors_raw,
                      UnblockHint as unblock_hint, CreatedAt as created_at
               FROM Refusal_Log
               WHERE Decision IN ('refuse', 'refuse_gate_fail', 'refuse_compliance',
                                   'refuse_low_confidence', 'defer_human_review')
               ORDER BY Confidence DESC
               LIMIT 100""",
        ).fetchall()
    import json
    result = []
    for r in rows:
        row = dict(r)
        try:
            row["blocking_factors"] = json.loads(row.pop("blocking_factors_raw") or "[]")
        except (json.JSONDecodeError, TypeError):
            row["blocking_factors"] = []
            row.pop("blocking_factors_raw", None)
        result.append(row)
    return {"refusals": result, "count": len(result)}
```

- **VALIDATE**: 
  ```bash
  curl -s http://localhost:8000/api/data/refusals | python3 -m json.tool | head -30
  curl -s http://localhost:8000/api/data/proposals/1/citations | python3 -m json.tool
  ```

---

### TASK 16 — UPDATE `reasoning/proposal_generator.py` — citation extraction

- **PATTERN**: `proposal_generator.py:197–216` — `_store_proposal()` method
- **IMPLEMENT**: Add citation extraction as a second Claude call in `_store_proposal()`. Extract structured citations from the `Proposal_JSON` and write to `Claim_Citation`.

Add a new method `_extract_and_store_citations()` after `_store_proposal()` (after line 216):

```python
def _extract_and_store_citations(self, client, opportunity_id: int, proposal: dict) -> None:
    """Post-process: extract claims from proposal narrative and match to DB sources."""
    import anthropic
    narrative = proposal.get("proposal_narrative", "")
    sources = proposal.get("sources", [])
    if not narrative:
        return

    extraction_prompt = f"""Extract verifiable claims from this procurement proposal and map each claim to a source.

PROPOSAL:
{narrative}

CONTEXT SOURCES AVAILABLE: {sources}

Return a JSON array of citations. Each element:
{{
  "claim_text": "exact short claim from proposal",
  "source_type": "fda_iid|pubchem|dsld|supplier|openfda|compliance",
  "source_id": "row ID or external identifier if known, else null",
  "source_snippet": "brief excerpt or data point that supports this claim",
  "confidence": 0.0-1.0
}}

Return only the JSON array, no other text. Maximum 8 citations."""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            messages=[{"role": "user", "content": extraction_prompt}],
        )
        raw = response.content[0].text.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        citations = json.loads(raw)
        if not isinstance(citations, list):
            return
        conn = sqlite3.connect(self.db_path)
        for cit in citations[:8]:
            conn.execute(
                """INSERT INTO Claim_Citation
                   (OpportunityId, ClaimText, SourceType, SourceId, SourceSnippet, Confidence)
                   VALUES (?,?,?,?,?,?)""",
                (
                    opportunity_id,
                    cit.get("claim_text", "")[:500],
                    cit.get("source_type", "unknown"),
                    str(cit.get("source_id")) if cit.get("source_id") else None,
                    cit.get("source_snippet", "")[:500],
                    float(cit.get("confidence", 0.7)),
                )
            )
        conn.commit()
        conn.close()
        logger.info(f"Stored {len(citations)} citations for opportunity {opportunity_id}")
    except Exception as e:
        logger.warning(f"Citation extraction failed for opportunity {opportunity_id}: {e}")
```

Then in `run()`, add call after `self._store_proposal(opp["id"], proposal)` (line 37):
```python
            self._extract_and_store_citations(client, opp["id"], proposal)
```

- **GOTCHA**: `Claim_Citation` table must exist before running — TASK 13 must be done first
- **VALIDATE**: After running proposal generator for 1 proposal, check: `python3 -c "import sqlite3; c=sqlite3.connect('db_enriched.sqlite'); print(c.execute('SELECT COUNT(*) FROM Claim_Citation').fetchone())"`

---

### TASK 17 — UPDATE `orchestration/ui/src/components/views/ProposalsView.tsx` — Citations + Refusals

- **PATTERN**: `ProposalsView.tsx:60–88` — proposal card footer area; `AlertsView.tsx:68–145` — card component pattern
- **IMPLEMENT**: Two additions: (1) expandable Citations section per proposal card; (2) Refusals panel below the grid.

Replace the entire file:

```typescript
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileText, ShieldCheck, ShieldAlert, Volume2, Users, ChevronDown, ChevronUp, BookOpen, XCircle } from "lucide-react";
import { agnesApi } from "@/lib/agnesApi";
import type { Proposal, Citation, Refusal } from "@/types/agnes";
import { useAgnes } from "@/hooks/useAgnes";
import { isElevenLabsConfigured } from "@/lib/elevenlabs";
import { GradePill } from "@/components/shared/GradePill";
import { ScoreBar } from "@/components/shared/ScoreBar";
import { EmptyState, ErrorState, LoadingState } from "@/components/shared/States";
import { cn } from "@/lib/utils";

const SOURCE_COLORS: Record<string, string> = {
  fda_iid: "text-blue-400",
  pubchem: "text-emerald-400",
  dsld: "text-violet-400",
  supplier: "text-amber-400",
  openfda: "text-red-400",
  compliance: "text-cyan-400",
};

function CitationRow({ cit }: { cit: Citation }) {
  return (
    <div className="flex items-start gap-2 text-[11px] py-1 border-b border-border last:border-0">
      <span className={cn("font-mono font-semibold uppercase shrink-0", SOURCE_COLORS[cit.source_type] ?? "text-muted-foreground")}>
        {cit.source_type.replace("_", " ")}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-foreground/90">{cit.claim_text}</p>
        {cit.source_snippet && (
          <p className="text-muted-foreground mt-0.5 line-clamp-2">{cit.source_snippet}</p>
        )}
      </div>
      {cit.confidence != null && (
        <span className="shrink-0 font-mono text-muted-foreground">{(cit.confidence * 100).toFixed(0)}%</span>
      )}
    </div>
  );
}

function ProposalCard({ p }: { p: Proposal }) {
  const [showCitations, setShowCitations] = useState(false);
  const { speak } = useAgnes();
  const ttsOk = isElevenLabsConfigured();

  const { data: citData } = useQuery({
    queryKey: ["citations", p.id],
    queryFn: () => agnesApi.proposalCitations(p.id),
    enabled: showCitations,
  });

  return (
    <article className="rounded-xl border border-border bg-background p-5 hover:shadow-sm transition-shadow flex flex-col">
      <header className="flex items-start justify-between gap-3 mb-3 pb-3 border-b border-border">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-[15px] font-semibold text-foreground">{p.ingredient_name}</h3>
            <GradePill grade={p.grade} />
          </div>
          <p className="text-[11px] text-muted-foreground mt-1 font-mono">
            {new Date(p.created_at).toLocaleString()}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Score</p>
          <p className="text-[18px] font-mono tabular-nums font-semibold text-foreground leading-none mt-0.5">
            {(p.consolidation_score * 100).toFixed(0)}
          </p>
        </div>
      </header>

      <p className="text-[13px] text-foreground/90 leading-[1.65] whitespace-pre-wrap flex-1">
        {p.proposal_text}
      </p>

      <footer className="mt-4 pt-3 border-t border-border flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 text-[11.5px] text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <Users className="size-3" /> {p.company_count} suppliers
          </span>
          {p.compliance_feasible ? (
            <span className="inline-flex items-center gap-1 text-status-completed">
              <ShieldCheck className="size-3" /> Compliance feasible
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-status-skipped">
              <ShieldAlert className="size-3" /> Review required
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowCitations(v => !v)}
            className="inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"
          >
            <BookOpen className="size-3" />
            Evidence
            {showCitations ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
          </button>
          {ttsOk && (
            <button
              onClick={() => void speak(p.proposal_text)}
              className="inline-flex items-center gap-1.5 text-[12px] font-medium text-primary hover:underline"
            >
              <Volume2 className="size-3.5" /> Read aloud
            </button>
          )}
        </div>
      </footer>

      {showCitations && (
        <div className="mt-3 pt-3 border-t border-border">
          {citData?.citations?.length ? (
            <div className="space-y-0">
              {citData.citations.map(cit => <CitationRow key={cit.id} cit={cit} />)}
            </div>
          ) : (
            <p className="text-[11px] text-muted-foreground">No citations available for this proposal. Re-run proposal generator to extract evidence.</p>
          )}
        </div>
      )}

      <ScoreBar score={p.consolidation_score} className="mt-3" showValue={false} />
    </article>
  );
}

function RefusalsPanel() {
  const [open, setOpen] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["refusals"],
    queryFn: () => agnesApi.refusals(),
    enabled: open,
  });

  return (
    <div className="mt-8 rounded-xl border border-border bg-background">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-5 py-3 text-left hover:bg-surface-subtle/40 transition-colors rounded-xl"
      >
        <div className="flex items-center gap-2">
          <XCircle className="size-4 text-red-400" strokeWidth={2} />
          <span className="text-[14px] font-semibold text-foreground">Refused & Deferred</span>
          <span className="text-[11px] text-muted-foreground">Substitutions Agnes cannot confidently recommend</span>
        </div>
        {open ? <ChevronUp className="size-4 text-muted-foreground" /> : <ChevronDown className="size-4 text-muted-foreground" />}
      </button>

      {open && (
        <div className="px-5 pb-5 space-y-3 border-t border-border pt-4">
          {isLoading && <p className="text-[12px] text-muted-foreground">Loading refusals…</p>}
          {data?.refusals?.map(r => (
            <div key={r.id} className="rounded-lg border border-red-500/20 bg-red-500/5 p-3 space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-[13px] font-semibold">{r.ingredient_name}</span>
                <span className={cn(
                  "text-[10px] uppercase px-1.5 py-0.5 rounded font-semibold",
                  r.decision.startsWith("defer") ? "bg-amber-500/10 text-amber-400 border border-amber-500/20" : "bg-red-500/10 text-red-400 border border-red-500/20"
                )}>
                  {r.decision.startsWith("defer") ? "Deferred" : "Refused"}
                </span>
                <span className="text-[10px] font-mono text-muted-foreground ml-auto">{(r.confidence * 100).toFixed(0)}% confidence</span>
              </div>
              <p className="text-[12px] text-foreground/80">{r.justification}</p>
              {r.unblock_hint && (
                <p className="text-[11px] text-muted-foreground border-t border-red-500/10 pt-1 mt-1">
                  <span className="font-medium text-foreground/70">To unblock: </span>{r.unblock_hint}
                </p>
              )}
            </div>
          ))}
          {data?.refusals?.length === 0 && !isLoading && (
            <p className="text-[12px] text-muted-foreground">No refusals recorded yet. Run compliance pipelines to populate.</p>
          )}
        </div>
      )}
    </div>
  );
}

export function ProposalsView() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["proposals"],
    queryFn: () => agnesApi.proposals(),
  });

  if (isLoading) return <LoadingState label="Loading proposals" />;
  if (error) return <ErrorState message="Could not load proposals." onRetry={() => refetch()} />;

  if (!data?.length) {
    return (
      <EmptyState
        icon={<FileText className="size-4" />}
        title="No proposals yet"
        body="Agnes generates these by running the proactive_consolidation or supplier_fallout pipelines."
      />
    );
  }

  return (
    <div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {data.map((p) => <ProposalCard key={p.id} p={p} />)}
      </div>
      <RefusalsPanel />
    </div>
  );
}
```

- **VALIDATE**: `cd orchestration/ui && bun run tsc --noEmit 2>&1 | head -30`

---

### TASK 18 — Run migration and regenerate proposals with citations

- **IMPLEMENT**: Run migration then re-run proposal generator so citations are extracted.
- **VALIDATE**:
  ```bash
  PYTHONPATH=. python3 enrichment/db_migrate_citation_refusal.py
  PYTHONPATH=. python3 reasoning/proposal_generator.py
  python3 -c "import sqlite3; c=sqlite3.connect('db_enriched.sqlite'); print('Citations:', c.execute('SELECT COUNT(*) FROM Claim_Citation').fetchone()); print('Refusals:', c.execute('SELECT COUNT(*) FROM Refusal_Log').fetchone())"
  ```

---

### TASK 19 — Build frontend and verify

- **VALIDATE**: 
  ```bash
  cd orchestration/ui && bun run build 2>&1 | tail -20
  ```
- **EXPECTED**: Exit code 0, no TypeScript errors, `dist/` updated

---

## TESTING STRATEGY

### Unit Tests
No test files exist in this project — validation is done via curl and manual UI testing.

### Integration Tests (Manual)

1. **Compliance tab**: Navigate → verify product names show as "Brand #ID" or real name, no `FG-iherb-` prefixes. Verify Vegan products show "Vegetarian" as a derived (lighter) cert.
2. **Ingredients tab**: Search — verify no all-caps chemical names like `ASCORBYL PALMITATE`.
3. **Regulatory tab**: Sidebar shows "Regulatory" entry → navigate → see alert cards with severity badges and before/after MDE.
4. **TopBar badge**: If price alerts exist, Bell icon with count badge is visible.
5. **Proposals tab**: Open a proposal card → expand "Evidence" → see ≥1 citation with source type and snippet.
6. **Refusals panel**: Scroll to bottom of Proposals → expand "Refused & Deferred" → see 4 demo trap refusals (Magnesium Stearate, Vitamin E, Titanium Dioxide, Ascorbic Acid).

### Edge Cases
- If Refusal_Log table doesn't exist yet, the `/api/data/refusals` endpoint must not crash — wrap in try/except returning `{"refusals": [], "count": 0}`
- If Claim_Citation table doesn't exist, same pattern
- If alertCount API returns null, badge must not render (badge only when `count > 0`)

---

## VALIDATION COMMANDS

### Level 1: TypeScript build
```bash
cd orchestration/ui && bun run tsc --noEmit 2>&1 | head -30
cd orchestration/ui && bun run build 2>&1 | tail -20
```

### Level 2: Backend import check
```bash
PYTHONPATH=. python3 -c "from orchestration.api.routes.data import router; print('data routes ok')"
PYTHONPATH=. python3 -c "from orchestration.tools.compliance_reasoner_tool import run; print('compliance tool ok')"
PYTHONPATH=. python3 -c "from reasoning.proposal_generator import ProposalGenerator; print('proposal gen ok')"
PYTHONPATH=. python3 -c "from enrichment.db_migrate_citation_refusal import migrate; print('migration ok')"
```

### Level 3: API endpoint validation
```bash
# Start server: PYTHONPATH=. uvicorn orchestration.api.main:app --reload --port 8000
curl -s http://localhost:8000/health
curl -s http://localhost:8000/api/data/compliance | python3 -c "import sys,json; d=json.load(sys.stdin); p=d['products'][0]; print('Name:', p['product_name'][:50], '| Certs:', list(p['certifications'].keys())[:5])"
curl -s http://localhost:8000/api/data/ingredients | python3 -c "import sys,json; d=json.load(sys.stdin); print([x['display_name'] for x in d[:5]])"
curl -s http://localhost:8000/api/data/regulatory-alerts | python3 -c "import sys,json; d=json.load(sys.stdin); print('Alerts:', d['count'])"
curl -s http://localhost:8000/api/data/refusals | python3 -c "import sys,json; d=json.load(sys.stdin); print('Refusals:', d['count'], [r['ingredient_name'] for r in d['refusals'][:3]])"
curl -s "http://localhost:8000/api/data/proposals/1/citations" | python3 -m json.tool | head -20
```

### Level 4: DB state check
```bash
python3 -c "
import sqlite3
c = sqlite3.connect('db_enriched.sqlite')
print('Proposals:', c.execute('SELECT COUNT(*) FROM Consolidation_Opportunity WHERE Proposal_Text IS NOT NULL').fetchone()[0])
print('Suppliers:', c.execute('SELECT COUNT(*) FROM Supplier_Commercial').fetchone()[0])
print('Citations:', c.execute('SELECT COUNT(*) FROM Claim_Citation').fetchone()[0])
print('Refusals:', c.execute('SELECT COUNT(*) FROM Refusal_Log').fetchone()[0])
print('Reg alerts:', c.execute('SELECT COUNT(*) FROM FDA_IID_Change_Log WHERE CanonicalIngredientId IS NOT NULL').fetchone()[0])
"
```

### Level 5: Demo walk-through
```bash
# Pre-demo checklist
curl -s http://localhost:8000/health
# Open UI at http://localhost:5173 (or rebuilt dist via FastAPI)
# 1. Compliance tab → no FG-iherb- codes, Vegan products show Vegetarian
# 2. Ingredients tab → no all-caps names
# 3. Regulatory tab → alert cards visible
# 4. Proposals tab → click proposal → expand Evidence → see citations
# 5. Proposals tab → scroll down → expand Refused & Deferred → 4 traps visible
# 6. TopBar → Bell badge if price alerts exist
```

---

## ACCEPTANCE CRITERIA

- [ ] Compliance matrix shows "Brand #ID" format, no raw `FG-iherb-*` codes
- [ ] Vegan-certified products show "Vegetarian" as derived cert in compliance matrix
- [ ] No all-caps ingredient names in Ingredients tab
- [ ] Sidebar has "Regulatory" tab with `ShieldAlert` icon
- [ ] RegulatoryAlertsView renders alert cards with severity badges and MDE comparison
- [ ] TopBar shows Bell badge with count when price alerts exist
- [ ] Proposals tab shows expandable "Evidence" section with citations per proposal
- [ ] "Refused & Deferred" collapsible panel in Proposals tab shows ≥4 entries (demo traps)
- [ ] `GET /api/data/proposals/{id}/citations` returns citation list
- [ ] `GET /api/data/refusals` returns refusal records with ingredient name + justification
- [ ] `bun run build` exits 0 with no TypeScript errors
- [ ] FastAPI server starts without import errors

---

## COMPLETION CHECKLIST

- [x] TASK 4–5: Backend display fixes applied (`data.py` updated)
- [x] TASK 6–7: TypeScript types and API client updated (`agnes.ts`, `agnesApi.ts`)
- [x] TASK 8–12: Sidebar, Index, RegulatoryAlertsView, usePriceAlerts, TopBar done
- [x] TASK 13: Migration created + run, 4 demo traps seeded
- [x] TASK 14: compliance_reasoner_tool persists refusals
- [x] TASK 15: 3 new endpoints in data.py
- [x] TASK 16: Proposal generator extracts citations
- [x] TASK 17: ProposalsView has citations + refusals panel
- [ ] TASK 0: `cd orchestration/ui && bun run build` — rebuild frontend dist
- [ ] TASK 1: `PYTHONPATH=. python3 reasoning/proposal_generator.py` — generate proposals + citations
- [ ] TASK 2: `PYTHONPATH=. python3 enrichment/backfill_supplier_web.py` — populate Supplier_Commercial
- [ ] TASK 3: Trigger `regulatory_drift_alert` + `price_monitor` pipelines via POST API
- [ ] TASK 18: DB state verification (proposals, suppliers, citations, refusals all non-zero)
- [ ] TASK 19: End-to-end demo walk-through (all 6 manual integration tests pass)

---

## NOTES

**Port**: CLAUDE.md says `--port 8000`. The frontend `.env` points to `http://95.216.146.149:8001` (remote server). For local dev, set `VITE_AGNES_API_URL=http://localhost:8000` in `orchestration/ui/.env` before building. For demo on the remote server, use port 8001.

**Task ordering**: Tasks 1–3 (data) must run before tasks 13–16 (schema + citation generation) because proposal_generator.py skips rows where `Proposal_Text IS NOT NULL`. Run TASK 13 (migration) before TASK 1 (proposal generator) so citations are extracted on first run. Correct order: TASK 13 → TASK 1 → TASK 14 → rest.

**Risk: Empty Claim_Citation on legacy proposals**: If proposal_generator.py was already run (Proposal_Text populated), re-running it will skip those rows (line 54: `WHERE Proposal_Text IS NULL`). To extract citations for existing proposals, either clear Proposal_Text first or add a `--citations-only` mode to the generator. For demo, clearing Proposal_Text and re-running 50 proposals is ~10 minutes but guarantees full citations.

**Risk: EmptyState children prop**: Check `orchestration/ui/src/components/shared/States.tsx` before implementing RegulatoryAlertsView — if `EmptyState` doesn't accept children for the "Run Pipeline" button, render the Button after `</EmptyState>` instead.

**Citation model**: Haiku (claude-haiku-4-5-20251001) is used for citation extraction (TASK 16) to minimize cost. It runs 8 citations per proposal × 50 proposals = ~400 Haiku calls. At ~$0.00025/call that's ~$0.10 total. Acceptable.
