# REF-DAG-CANVAS-ALPINEJS

**Reference Guide: Live DAG Visualization Component for HappyRobot Dashboard**

*Target file: `static/dashboard.html` — Alpine.js + DaisyUI + Tailwind, no build tooling, CDN-only*

---

## Table of Contents

1. [Context and Constraints](#1-context-and-constraints)
2. [CDN Imports](#2-cdn-imports)
3. [New Backend API Contract](#3-new-backend-api-contract)
4. [Alpine.js State Model Additions](#4-alpinejs-state-model-additions)
5. [Dagre Layout Engine](#5-dagre-layout-engine)
6. [D3.js SVG Rendering](#6-d3js-svg-rendering)
7. [Status Color Scheme and CSS Animations](#7-status-color-scheme-and-css-animations)
8. [SSE EventSource Subscription](#8-sse-eventsource-subscription)
9. [Node Output Drawer (DaisyUI)](#9-node-output-drawer-daisyui)
10. [Pipeline Run History Panel](#10-pipeline-run-history-panel)
11. [Reasoning Trail Component](#11-reasoning-trail-component)
12. [HTML Layout — Where to Insert Things](#12-html-layout--where-to-insert-things)
13. [Full Integration Checklist](#13-full-integration-checklist)

---

## 1. Context and Constraints

### What Already Exists

`static/dashboard.html` is a single-file Alpine.js application with no build step. It uses:

- **Alpine.js 3.x** (`x-data="dashboard()"`, `x-init="init()"`) — all state lives in the `dashboard()` function
- **DaisyUI 4** + **Tailwind CSS CDN** — UI components
- **marked.js** — markdown rendering already wired up
- A 5-second `setInterval` refresh loop polling `/leads`, `/drafts`, `/pipeline/active`, `/analytics/overview`
- An `expandRun(run)` method that fetches `/pipeline/status/{job_id}` and shows per-node status rows inline in the Agent Activity Feed

### What PRD 6 Phase 3 Adds

A full DAG canvas showing pipeline nodes as positioned cards with live status colours, driven by SSE. The canvas replaces the text-only node list in the expanded run view. It also adds:

- A **node output drawer** — click any node to see the agent's full output
- A **pipeline run history panel** per lead
- A **wiki health / reasoning trail** component (profile → strategy memo → draft chain)

### Why D3 + Dagre (Not React Flow)

Archon's reference implementation (WORKFLOW_ORCHESTRATION_BRIEFING §8) uses React Flow v12 with a Dagre layout engine. This project cannot use React Flow because:

1. There is no build toolchain — no npm, no bundler, no JSX transform
2. Alpine.js already owns the DOM; React would require a separate mount root and state bridge

The equivalent CDN-friendly stack is:
- **dagre.js** for topological layout (same library React Flow uses internally)
- **D3.js v7** for SVG rendering (imperative DOM, no VDOM needed)
- **Alpine.js** for reactive state glue (D3 reads `dagNodeStates`, redraws SVG on change)

---

## 2. CDN Imports

Add these two `<script>` tags to `<head>`, **after** the existing Tailwind CDN script and **before** the Alpine.js script:

```html
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>HappyRobot Dashboard</title>
  <link href="https://cdn.jsdelivr.net/npm/daisyui@4/dist/full.min.css" rel="stylesheet" />
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>

  <!-- DAG canvas dependencies — add these two lines -->
  <script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/dagre@0.8.5/dist/dagre.min.js"></script>

  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
</head>
```

**Why these exact versions:**

- `d3@7` — D3 v7 changed `d3.event` to normal event arguments (breaking change from v6). The code in this guide uses v7 signatures (`(event, d)` in handlers). Using v6 will silently break click events.
- `dagre@0.8.5` — dagre's npm package has not been updated since 0.8.5 (2019). This is the last stable release. Later semver ranges might resolve to forks with incompatible APIs. Pin exactly.
- D3 must load before Alpine because `renderDag()` is called from Alpine methods — it needs `d3` to be on `window`. Alpine is `defer`-loaded, so the order here is correct: D3 and dagre load synchronously, Alpine defers until DOM ready.

---

## 3. New Backend API Contract

PRD 6 Phase 2 must add three new endpoints to `api/routes/pipelines.py`. The frontend implementer needs to know exactly what to parse.

### 3.1 `GET /pipeline/definition/{pipeline_name}`

Returns the static structure of a named pipeline from `PIPELINE_REGISTRY`.

**Response shape:**
```json
{
  "name": "inbound_responder",
  "nodes": [
    {
      "id": "wiki-readiness",
      "agent_class": "WikiReadinessAgent",
      "depends_on": [],
      "type": "agent"
    },
    {
      "id": "strategy",
      "agent_class": "StrategyAgent",
      "depends_on": ["wiki-readiness"],
      "type": "agent"
    },
    {
      "id": "response",
      "agent_class": "ResponseAgent",
      "depends_on": ["strategy"],
      "type": "agent"
    },
    {
      "id": "draft-approval",
      "agent_class": null,
      "depends_on": ["response"],
      "type": "approval"
    },
    {
      "id": "sender",
      "agent_class": "SenderAgent",
      "depends_on": ["draft-approval"],
      "type": "agent"
    }
  ]
}
```

`type` is `"agent"` for `PipelineNode` and `"approval"` for `ApprovalNode`. The frontend uses `type` to render approval nodes differently (diamond icon vs rect).

**Backend implementation stub (add to `api/routes/pipelines.py`):**
```python
@router.get("/definition/{pipeline_name}")
async def pipeline_definition(pipeline_name: str):
    from api.pipeline_def import PIPELINE_REGISTRY, ApprovalNode
    pipeline = PIPELINE_REGISTRY.get(pipeline_name)
    if not pipeline:
        raise HTTPException(404, f"Pipeline not found: {pipeline_name}")
    nodes = []
    for n in pipeline.nodes:
        nodes.append({
            "id": n.id,
            "agent_class": getattr(n, "agent_class", None),
            "depends_on": n.depends_on,
            "type": "approval" if isinstance(n, ApprovalNode) else "agent",
        })
    return {"name": pipeline.name, "nodes": nodes}
```

### 3.2 `GET /pipeline/stream/{run_id}` (SSE)

Server-Sent Events stream for a specific run. Returns `text/event-stream`.

**Event types and payload shapes:**

```
event: node_started
data: {"node_id": "wiki-readiness", "pipeline_name": "inbound_responder", "run_id": "abc123"}

event: node_completed
data: {"node_id": "wiki-readiness", "node_output": "WikiReadinessAgent output text here...", "run_id": "abc123"}

event: node_failed
data: {"node_id": "strategy", "error": "LLM call timeout after 30s", "run_id": "abc123"}

event: node_skipped
data: {"node_id": "draft-approval", "reason": "when_condition_false", "run_id": "abc123"}

event: pipeline_completed
data: {"run_id": "abc123", "status": "completed"}
```

The frontend only uses `node_id`, `node_output`, `error`, and `status`. All other fields are informational. On `pipeline_completed`, the frontend closes the EventSource.

**Backend implementation stub:**
```python
from fastapi.responses import StreamingResponse
import asyncio

@router.get("/stream/{run_id}")
async def pipeline_stream(run_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """SSE stream: replay historical events then tail new ones."""
    async def event_generator():
        # 1. Replay events already written to pipeline_events for this run
        async with db.execute(
            "SELECT event_type, node_id, data FROM pipeline_events "
            "WHERE run_id = ? ORDER BY created_at ASC",
            (run_id,),
        ) as cur:
            rows = [dict(r) async for r in cur]
        for row in rows:
            payload = json.loads(row["data"] or "{}")
            payload["node_id"] = row["node_id"]
            yield f"event: {row['event_type']}\ndata: {json.dumps(payload)}\n\n"

        # 2. Tail: poll every 500ms for new events (simple polling tail)
        last_seen_count = len(rows)
        while True:
            await asyncio.sleep(0.5)
            async with db.execute(
                "SELECT event_type, node_id, data FROM pipeline_events "
                "WHERE run_id = ? ORDER BY created_at ASC",
                (run_id,),
            ) as cur:
                all_rows = [dict(r) async for r in cur]
            new_rows = all_rows[last_seen_count:]
            for row in new_rows:
                payload = json.loads(row["data"] or "{}")
                payload["node_id"] = row["node_id"]
                yield f"event: {row['event_type']}\ndata: {json.dumps(payload)}\n\n"
                if row["event_type"] == "pipeline_completed":
                    return
            last_seen_count = len(all_rows)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

### 3.3 `GET /pipeline/runs?lead_id={id}`

Returns the run history for a specific lead.

**Response shape:**
```json
{
  "runs": [
    {
      "run_id": "abc123",
      "pipeline_name": "inbound_responder",
      "status": "completed",
      "started_at": "2026-04-15T10:00:00Z",
      "completed_at": "2026-04-15T10:02:30Z"
    },
    {
      "run_id": "def456",
      "pipeline_name": "inbound_responder",
      "status": "failed",
      "started_at": "2026-04-14T09:30:00Z",
      "completed_at": "2026-04-14T09:31:05Z"
    }
  ]
}
```

**Backend implementation stub:**
```python
@router.get("/runs")
async def pipeline_runs(lead_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute(
        "SELECT id, pipeline_name, status, started_at, completed_at "
        "FROM pipeline_runs WHERE lead_id = ? ORDER BY started_at DESC LIMIT 20",
        (lead_id,),
    ) as cur:
        rows = [dict(r) async for r in cur]
    return {
        "runs": [
            {
                "run_id": r["id"],
                "pipeline_name": r["pipeline_name"],
                "status": r["status"],
                "started_at": r["started_at"],
                "completed_at": r["completed_at"],
            }
            for r in rows
        ]
    }
```

---

## 4. Alpine.js State Model Additions

All additions go inside the `dashboard()` function in `static/dashboard.html`. Add the new state fields at the top of the returned object (alongside `leads`, `drafts`, etc.) and add the new methods alongside `refresh()`, `selectLead()`, etc.

### 4.1 New State Fields

```js
function dashboard() {
  return {
    // --- existing fields (do not remove) ---
    leads: [],
    drafts: [],
    pipelines: [],
    activePipelines: [],
    pausedPipelines: [],
    analytics: null,
    opportunities: [],
    autodreamActivity: [],
    selectedLead: null,
    activeTab: 'profile',
    leadDetail: null,
    draftContent: null,
    strategyMemoMd: null,
    loadingDetail: false,
    expandedRunId: null,
    expandedRunNodes: [],

    // --- NEW: DAG canvas state ---
    dagPipeline: null,        // { name, nodes } — from GET /pipeline/definition/
    dagLayout: null,          // computed by computeDagLayout(); { nodes, edges, width, height }
    dagNodeStates: {},        // { [nodeId]: { status, output, label } }
    activeRunId: null,        // run_id currently displayed in DAG canvas
    sseConnection: null,      // EventSource instance — close() before reassigning
    selectedNodeId: null,     // clicked node for output drawer; null = drawer closed
    pipelineRuns: [],         // from GET /pipeline/runs?lead_id=
    showDagPanel: false,      // toggle the DAG panel visibility
    dagLoading: false,        // loading indicator for definition fetch
    // ... rest of init(), methods below
  }
}
```

### 4.2 New Methods (add to returned object)

```js
// Load pipeline definition and set up dagLayout + initial node states (all 'pending')
async loadPipelineDefinition(pipelineName) {
    this.dagLoading = true;
    try {
        const res = await fetch(`/pipeline/definition/${encodeURIComponent(pipelineName)}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        this.dagPipeline = data;

        // Build dagNodeStates with pending status for each node
        const states = {};
        for (const node of data.nodes) {
            states[node.id] = {
                status: 'pending',
                output: '',
                label: node.agent_class || node.id,
                type: node.type,
            };
        }
        this.dagNodeStates = states;

        // Compute layout: nodes need id+label, edges derived from depends_on
        const layoutNodes = data.nodes.map(n => ({ id: n.id, label: n.agent_class || n.id }));
        const layoutEdges = [];
        for (const node of data.nodes) {
            for (const dep of (node.depends_on || [])) {
                layoutEdges.push({ source: dep, target: node.id });
            }
        }
        this.dagLayout = computeDagLayout(layoutNodes, layoutEdges);
        this.showDagPanel = true;

        // Render SVG after next Alpine microtask tick (DOM must exist)
        this.$nextTick(() => this.renderDag());
    } catch (e) {
        console.error('[DAG] loadPipelineDefinition failed:', e);
    } finally {
        this.dagLoading = false;
    }
},

// Load run history for the currently selected lead
async loadPipelineRuns(leadId) {
    try {
        const res = await fetch(`/pipeline/runs?lead_id=${encodeURIComponent(leadId)}`);
        if (!res.ok) return;
        const data = await res.json();
        this.pipelineRuns = data.runs || [];
    } catch (e) {
        console.error('[DAG] loadPipelineRuns failed:', e);
    }
},

// Subscribe to SSE stream for a run; updates dagNodeStates and re-renders
subscribeToPipelineRun(runId) {
    // Tear down existing connection
    if (this.sseConnection) {
        this.sseConnection.close();
        this.sseConnection = null;
    }
    this.activeRunId = runId;

    const es = new EventSource(`/pipeline/stream/${runId}`);
    this.sseConnection = es;

    const updateNode = (nodeId, status, output) => {
        if (!this.dagNodeStates[nodeId]) {
            this.dagNodeStates[nodeId] = { status, output, label: nodeId, type: 'agent' };
        } else {
            this.dagNodeStates[nodeId] = {
                ...this.dagNodeStates[nodeId],
                status,
                output,
            };
        }
        this.renderDag();
    };

    es.addEventListener('node_started', e => {
        const d = JSON.parse(e.data);
        updateNode(d.node_id, 'running', '');
    });
    es.addEventListener('node_completed', e => {
        const d = JSON.parse(e.data);
        updateNode(d.node_id, 'completed', d.node_output || '');
    });
    es.addEventListener('node_failed', e => {
        const d = JSON.parse(e.data);
        updateNode(d.node_id, 'failed', d.error || '');
    });
    es.addEventListener('node_skipped', e => {
        const d = JSON.parse(e.data);
        updateNode(d.node_id, 'skipped', '');
    });
    es.addEventListener('pipeline_completed', () => {
        es.close();
        this.sseConnection = null;
        this.renderDag(); // final repaint to flush last states
    });
    es.onerror = () => {
        // Browser automatically reconnects SSE on network errors.
        // Log only — do not close; allow browser retry.
        console.warn('[SSE] connection error — browser will retry automatically');
    };
},

// Close SSE and clear activeRunId
unsubscribeFromRun() {
    if (this.sseConnection) {
        this.sseConnection.close();
        this.sseConnection = null;
    }
    this.activeRunId = null;
},

// Render (or re-render) the SVG using current dagLayout + dagNodeStates
renderDag() {
    if (!this.dagLayout) return;
    renderDagSvg('#dag-canvas', this.dagLayout, this.dagNodeStates, (nodeId) => {
        this.selectedNodeId = nodeId;
    });
},

// Open node output drawer (called by SVG click handler via renderDag callback)
openNodeDrawer(nodeId) {
    this.selectedNodeId = nodeId;
},

// Close node drawer
closeNodeDrawer() {
    this.selectedNodeId = null;
},

// Load definition + subscribe to a run atomically (called from run history "View" button)
async viewRun(run) {
    await this.loadPipelineDefinition(run.pipeline_name);
    this.subscribeToPipelineRun(run.run_id);
},
```

### 4.3 Additions to `selectLead()`

When a lead is selected, automatically load their run history and, if there is an active run for this lead, open the DAG canvas:

```js
async selectLead(lead) {
    this.selectedLead = lead;
    this.activeTab = 'profile';
    this.loadingDetail = true;
    this.leadDetail = null;
    this.draftContent = null;
    this.strategyMemoMd = null;

    // NEW: reset DAG state
    this.unsubscribeFromRun();
    this.dagPipeline = null;
    this.dagLayout = null;
    this.dagNodeStates = {};
    this.selectedNodeId = null;
    this.showDagPanel = false;

    await Promise.all([
        this.fetchLeadDetail(lead.id),
        this.loadPipelineRuns(lead.id),   // NEW
    ]);
    this.loadingDetail = false;

    // NEW: auto-open DAG if this lead has an active running pipeline
    const activeRun = this.activePipelines.find(r => r.lead_id === lead.id);
    if (activeRun) {
        await this.loadPipelineDefinition(activeRun.pipeline_name);
        this.subscribeToPipelineRun(activeRun.run_id);
    }
},
```

---

## 5. Dagre Layout Engine

### How Dagre Works

Dagre is a JavaScript port of the Graphviz dot layout algorithm. It takes a graph (nodes + edges), runs the Sugiyama framework for layered digraph drawing, and outputs concrete `(x, y)` coordinates for each node and waypoints for each edge. The layout is pure in-memory — dagre does not touch the DOM.

The key graph object is `dagre.graphlib.Graph()`. You assign node and edge metadata, call `dagre.layout(g)`, and then read back positions with `g.node(id)`.

### Layout Parameters

| Parameter | What it controls | Recommended value |
|-----------|-----------------|-------------------|
| `rankdir` | Direction of flow: `'LR'` (left→right), `'TB'` (top→bottom) | `'LR'` — pipelines have 5–8 sequential stages; LR uses horizontal space well and avoids vertical scroll in the canvas |
| `ranksep` | Pixels between rank (column) layers | `80` — gives breathing room between stages |
| `nodesep` | Pixels between nodes within the same rank | `40` — parallel nodes at the same stage need separation |
| `marginx` / `marginy` | Outer margin of the entire graph | `20` — prevents SVG clipping |

**Why LR over TB for pipelines:** The `inbound_responder` pipeline has 5 sequential nodes with at most 1 parallel pair. In TB layout with a 600px canvas height this leaves each node only ~100px vertical space. In LR layout with a 900px canvas width, each node gets ~160px horizontal space, which matches the `width: 160` we assign each node.

### Complete `computeDagLayout()` Function

Place this **outside** the `dashboard()` function, as a top-level utility (before the `<script>` closing tag):

```js
/**
 * computeDagLayout — wraps dagre to produce SVG-ready node positions.
 *
 * @param {Array<{id: string, label: string}>} nodes
 * @param {Array<{source: string, target: string}>} edges
 * @returns {{
 *   nodes: Array<{id, x, y, width, height, label}>,
 *   edges: Array<{v, w, points: Array<{x, y}>}>,
 *   width: number,
 *   height: number
 * }}
 */
function computeDagLayout(nodes, edges) {
    const g = new dagre.graphlib.Graph();
    g.setGraph({
        rankdir: 'LR',
        ranksep: 80,
        nodesep: 40,
        marginx: 20,
        marginy: 20,
    });
    g.setDefaultEdgeLabel(() => ({}));

    nodes.forEach(n => {
        g.setNode(n.id, { label: n.label, width: 160, height: 60 });
    });
    edges.forEach(e => {
        g.setEdge(e.source, e.target);
    });

    dagre.layout(g);

    return {
        nodes: g.nodes().map(id => ({ id, ...g.node(id) })),
        edges: g.edges().map(e => ({
            v: e.v,
            w: e.w,
            points: g.edge(e).points,
        })),
        width: g.graph().width,
        height: g.graph().height,
    };
}
```

**Reading dagre output:**

After `dagre.layout(g)`, each node has:
- `x`, `y` — the center point of the node rectangle
- `width`, `height` — dimensions you assigned

To draw the rect, compute top-left as `(x - width/2, y - height/2)`.

Each edge has `points: [{x, y}]` — an array of waypoints through which the edge path should pass. Use D3's line generator with basis interpolation to produce smooth curves through these points.

---

## 6. D3.js SVG Rendering

### Architecture: D3 Manages SVG, Alpine Manages State

Alpine owns the component state (`dagNodeStates`). D3 owns the SVG DOM entirely. The bridge is `renderDag()` — called by Alpine whenever state changes, it passes the current layout and state to a pure D3 function that wipes and redraws the SVG.

This is simpler than trying to bind Alpine `x-bind` attributes to SVG elements (Alpine's SVG support has edge cases with namespace attributes). Let D3 handle all SVG DOM mutations.

### Complete `renderDagSvg()` Function

Place this as a top-level function alongside `computeDagLayout()`:

```js
const STATUS_COLORS = {
    pending:   { fill: '#e5e7eb', stroke: '#9ca3af', text: '#6b7280' },
    running:   { fill: '#dbeafe', stroke: '#3b82f6', text: '#1d4ed8' },
    completed: { fill: '#dcfce7', stroke: '#22c55e', text: '#15803d' },
    failed:    { fill: '#fee2e2', stroke: '#ef4444', text: '#dc2626' },
    skipped:   { fill: '#f3f4f6', stroke: '#d1d5db', text: '#9ca3af' },
    approval:  { fill: '#fef9c3', stroke: '#eab308', text: '#854d0e' },
};

/**
 * renderDagSvg — full D3 render of DAG layout into an SVG element.
 *
 * @param {string} svgSelector  CSS selector for the SVG element, e.g. '#dag-canvas'
 * @param {object} layout       Output of computeDagLayout()
 * @param {object} nodeStates   { [nodeId]: { status, output, label, type } }
 * @param {function} onNodeClick  Callback: (nodeId) => void
 */
function renderDagSvg(svgSelector, layout, nodeStates, onNodeClick) {
    const padding = 40;
    const svg = d3.select(svgSelector);
    if (svg.empty()) return;  // element not yet in DOM

    svg.selectAll('*').remove();
    svg
        .attr('width', (layout.width || 400) + padding)
        .attr('height', (layout.height || 200) + padding);

    const g = svg.append('g').attr('transform', `translate(${padding / 2},${padding / 2})`);

    // --- Arrow marker definition ---
    svg.append('defs')
        .append('marker')
        .attr('id', 'dag-arrow')
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 10)
        .attr('refY', 0)
        .attr('markerWidth', 6)
        .attr('markerHeight', 6)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M0,-5L10,0L0,5')
        .attr('fill', '#9ca3af');

    // --- Draw edges ---
    const lineGenerator = d3.line()
        .x(d => d.x)
        .y(d => d.y)
        .curve(d3.curveBasis);  // smooth bezier through dagre waypoints

    g.selectAll('.dag-edge')
        .data(layout.edges)
        .enter()
        .append('path')
        .attr('class', 'dag-edge')
        .attr('d', d => lineGenerator(d.points))
        .attr('fill', 'none')
        .attr('stroke', '#d1d5db')
        .attr('stroke-width', 1.5)
        .attr('marker-end', 'url(#dag-arrow)');

    // --- Draw nodes ---
    const nodeG = g.selectAll('.dag-node')
        .data(layout.nodes)
        .enter()
        .append('g')
        .attr('class', d => {
            const state = nodeStates[d.id] || {};
            const base = 'dag-node cursor-pointer';
            return state.status === 'running' ? base + ' node-running' : base;
        })
        .attr('transform', d => `translate(${d.x - d.width / 2},${d.y - d.height / 2})`)
        .style('cursor', 'pointer')
        .on('click', (event, d) => {
            event.stopPropagation();
            onNodeClick(d.id);
        });

    // Node background rectangle
    nodeG.append('rect')
        .attr('width', d => d.width)
        .attr('height', d => d.height)
        .attr('rx', 8)
        .attr('ry', 8)
        .attr('fill', d => {
            const state = nodeStates[d.id] || {};
            const scheme = STATUS_COLORS[state.status] || STATUS_COLORS.pending;
            return scheme.fill;
        })
        .attr('stroke', d => {
            const state = nodeStates[d.id] || {};
            const scheme = STATUS_COLORS[state.status] || STATUS_COLORS.pending;
            return scheme.stroke;
        })
        .attr('stroke-width', d => {
            const state = nodeStates[d.id] || {};
            return state.status === 'running' ? 2.5 : 1.5;
        });

    // Node label (agent_class name, truncated to fit)
    nodeG.append('text')
        .attr('x', d => d.width / 2)
        .attr('y', d => d.height / 2 - 6)
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .attr('font-size', '11px')
        .attr('font-weight', '600')
        .attr('fill', d => {
            const state = nodeStates[d.id] || {};
            const scheme = STATUS_COLORS[state.status] || STATUS_COLORS.pending;
            return scheme.text;
        })
        .text(d => {
            const label = (nodeStates[d.id] || {}).label || d.id;
            // Truncate: "WikiReadinessAgent" → "WikiReadiness..."
            return label.length > 16 ? label.substring(0, 14) + '…' : label;
        });

    // Node ID (smaller, below label)
    nodeG.append('text')
        .attr('x', d => d.width / 2)
        .attr('y', d => d.height / 2 + 10)
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .attr('font-size', '9px')
        .attr('fill', '#9ca3af')
        .text(d => d.id);

    // Status icon (top-right corner of node)
    nodeG.append('text')
        .attr('x', d => d.width - 8)
        .attr('y', 12)
        .attr('text-anchor', 'end')
        .attr('font-size', '12px')
        .text(d => {
            const status = (nodeStates[d.id] || {}).status || 'pending';
            const icons = {
                pending:   '○',
                running:   '◉',
                completed: '✓',
                failed:    '✗',
                skipped:   '⊘',
                approval:  '⏸',
            };
            return icons[status] || '○';
        })
        .attr('fill', d => {
            const state = nodeStates[d.id] || {};
            const scheme = STATUS_COLORS[state.status] || STATUS_COLORS.pending;
            return scheme.stroke;
        });

    // Approval node: add a diamond overlay at bottom of rect
    nodeG.filter(d => (nodeStates[d.id] || {}).type === 'approval')
        .append('rect')
        .attr('x', d => d.width / 2 - 6)
        .attr('y', d => d.height - 8)
        .attr('width', 12)
        .attr('height', 12)
        .attr('transform', d => `rotate(45, ${d.width / 2}, ${d.height - 2})`)
        .attr('fill', STATUS_COLORS.approval.fill)
        .attr('stroke', STATUS_COLORS.approval.stroke)
        .attr('stroke-width', 1);
}
```

**Key implementation notes:**

- `svg.selectAll('*').remove()` on every render — this is the simplest correct approach for a sub-second refresh cycle. Do not try incremental updates; the number of nodes is small (≤10 per pipeline) so full redraws are imperceptible.
- `d3.curveBasis` through dagre waypoints produces smooth S-curves. `d3.curveLinear` would draw straight line segments through the same waypoints (also acceptable but less polished).
- The `url(#dag-arrow)` marker reference requires the `<defs>` to be inside the same `<svg>` element. Since we append `defs` to `svg` before `g`, it works.
- Alpine's `$nextTick` is critical before calling `renderDag()` — the `<svg id="dag-canvas">` must be in the DOM. Always call `renderDag()` inside `$nextTick` from `loadPipelineDefinition`.

---

## 7. Status Color Scheme and CSS Animations

### Color Constants

The `STATUS_COLORS` object is defined alongside the render function (section 6 above). Colors are chosen to match DaisyUI's badge color semantics:

| Status | Fill | Stroke | Text | DaisyUI equivalent |
|--------|------|--------|------|--------------------|
| `pending` | `#e5e7eb` gray-200 | `#9ca3af` gray-400 | `#6b7280` gray-500 | `badge-ghost` |
| `running` | `#dbeafe` blue-100 | `#3b82f6` blue-500 | `#1d4ed8` blue-700 | `badge-info` |
| `completed` | `#dcfce7` green-100 | `#22c55e` green-500 | `#15803d` green-700 | `badge-success` |
| `failed` | `#fee2e2` red-100 | `#ef4444` red-500 | `#dc2626` red-600 | `badge-error` |
| `skipped` | `#f3f4f6` gray-100 | `#d1d5db` gray-300 | `#9ca3af` gray-400 | `badge-ghost` dimmer |
| `approval` | `#fef9c3` yellow-100 | `#eab308` yellow-500 | `#854d0e` yellow-900 | `badge-warning` |

### CSS for Pulsing Running State

Add this `<style>` block to `<head>`, after the DaisyUI link:

```html
<style>
  @keyframes pulse-border {
    0%, 100% { stroke-opacity: 1; stroke-width: 2.5px; }
    50%       { stroke-opacity: 0.35; stroke-width: 1.5px; }
  }
  .node-running rect {
    animation: pulse-border 1.5s ease-in-out infinite;
  }

  /* Smooth DAG panel slide-in */
  #dag-panel {
    transition: opacity 0.2s ease;
  }

  /* Scrollable SVG container */
  #dag-canvas-container {
    overflow-x: auto;
    overflow-y: auto;
    max-height: 320px;
  }
</style>
```

**How the pulse animation connects to D3:** The `renderDagSvg` function assigns class `node-running` to the `<g>` element of any node with status `running`. The CSS `@keyframes` targets `rect` within that `<g>`. Because D3 assigns the class directly to the SVG group element, and CSS can target children with `.node-running rect`, the animation works without any Alpine involvement.

---

## 8. SSE EventSource Subscription

### EventSource Browser Behavior

The `EventSource` API has automatic reconnect built into the browser. If the connection drops (network blip, server restart), the browser waits ~3 seconds and re-sends the request with a `Last-Event-ID` header if the server set `id:` fields on events. Our backend does not set `id:` fields in the stub above, so the browser will reconnect but replay from the beginning. The backend's "replay then tail" approach handles this correctly — it always replays all historical events for the run before tailing, so a reconnect produces duplicate state updates, but since `dagNodeStates` is overwritten (not appended), this is idempotent.

**Do not call `es.close()` in `onerror`** — that prevents the browser's built-in reconnect. Only close when `pipeline_completed` is received.

### Complete `subscribeToPipelineRun` with Error Boundary

This is the full production implementation. Replace the stub from section 4 with this:

```js
subscribeToPipelineRun(runId) {
    if (this.sseConnection) {
        this.sseConnection.close();
        this.sseConnection = null;
    }
    this.activeRunId = runId;

    const es = new EventSource(`/pipeline/stream/${runId}`);
    this.sseConnection = es;

    const updateNode = (nodeId, patch) => {
        const existing = this.dagNodeStates[nodeId] || { status: 'pending', output: '', label: nodeId, type: 'agent' };
        this.dagNodeStates[nodeId] = { ...existing, ...patch };
        this.$nextTick(() => this.renderDag());
    };

    es.addEventListener('node_started', e => {
        const d = JSON.parse(e.data);
        updateNode(d.node_id, { status: 'running', output: '' });
    });

    es.addEventListener('node_completed', e => {
        const d = JSON.parse(e.data);
        updateNode(d.node_id, { status: 'completed', output: d.node_output || '' });
    });

    es.addEventListener('node_failed', e => {
        const d = JSON.parse(e.data);
        updateNode(d.node_id, { status: 'failed', output: d.error || 'unknown error' });
    });

    es.addEventListener('node_skipped', e => {
        const d = JSON.parse(e.data);
        updateNode(d.node_id, { status: 'skipped', output: d.reason || '' });
    });

    es.addEventListener('pipeline_completed', () => {
        // Reload run history so the completed run appears with correct status
        if (this.selectedLead) {
            this.loadPipelineRuns(this.selectedLead.id);
        }
        es.close();
        this.sseConnection = null;
        this.$nextTick(() => this.renderDag());
    });

    es.onerror = () => {
        // Do NOT close — let browser reconnect automatically.
        // Only log. The backend replay-then-tail design handles reconnects.
        console.warn('[SSE] pipeline stream error — browser will retry');
    };
},
```

**Important:** Use `this.$nextTick(() => this.renderDag())` inside SSE handlers rather than `this.renderDag()` directly. The SSE callback fires outside Alpine's reactive cycle. `$nextTick` ensures Alpine has processed any pending DOM mutations before D3 reads the SVG element.

---

## 9. Node Output Drawer (DaisyUI)

### DaisyUI Drawer Pattern

DaisyUI's drawer component uses a checkbox toggle + `drawer-side` div. For this use case we use Alpine's `x-show` to control visibility instead of a checkbox, which gives programmatic control.

### HTML Template

Add this at the very end of `<body>`, before the closing `</body>` tag and before the `<script>` block:

```html
<!-- Node Output Drawer — slides in from right when a DAG node is clicked -->
<div
  x-show="selectedNodeId !== null"
  x-transition:enter="transition ease-out duration-200"
  x-transition:enter-start="translate-x-full opacity-0"
  x-transition:enter-end="translate-x-0 opacity-100"
  x-transition:leave="transition ease-in duration-150"
  x-transition:leave-start="translate-x-0 opacity-100"
  x-transition:leave-end="translate-x-full opacity-0"
  class="fixed right-0 top-0 h-full w-96 bg-base-100 shadow-2xl z-50 flex flex-col"
  style="display: none;"
>
  <!-- Drawer header -->
  <div class="flex items-center justify-between px-4 py-3 border-b border-base-200">
    <div>
      <h3 class="font-semibold text-sm" x-text="dagNodeStates[selectedNodeId]?.label || selectedNodeId"></h3>
      <span
        class="badge badge-xs mt-0.5"
        :class="{
          'badge-ghost':   dagNodeStates[selectedNodeId]?.status === 'pending',
          'badge-info':    dagNodeStates[selectedNodeId]?.status === 'running',
          'badge-success': dagNodeStates[selectedNodeId]?.status === 'completed',
          'badge-error':   dagNodeStates[selectedNodeId]?.status === 'failed',
          'badge-warning': dagNodeStates[selectedNodeId]?.status === 'skipped',
        }"
        x-text="dagNodeStates[selectedNodeId]?.status || 'pending'"
      ></span>
    </div>
    <button class="btn btn-ghost btn-sm btn-square" @click="closeNodeDrawer()">✕</button>
  </div>

  <!-- Loading indicator for running nodes -->
  <template x-if="dagNodeStates[selectedNodeId]?.status === 'running'">
    <div class="flex items-center gap-2 px-4 py-2 bg-blue-50 text-blue-700 text-xs">
      <span class="loading loading-spinner loading-xs"></span>
      Agent is running…
    </div>
  </template>

  <!-- Output content -->
  <div class="flex-1 overflow-y-auto p-4">
    <template x-if="dagNodeStates[selectedNodeId]?.output">
      <div class="prose prose-sm max-w-none">
        <div x-html="typeof marked !== 'undefined'
          ? marked.parse(dagNodeStates[selectedNodeId].output)
          : dagNodeStates[selectedNodeId].output">
        </div>
      </div>
    </template>
    <template x-if="!dagNodeStates[selectedNodeId]?.output">
      <p class="text-xs text-base-content/40 italic">
        No output yet.
        <span x-show="dagNodeStates[selectedNodeId]?.status === 'pending'">
          This node has not started.
        </span>
      </p>
    </template>
  </div>

  <!-- Footer: node ID + type -->
  <div class="px-4 py-2 border-t border-base-200 text-xs text-base-content/40">
    Node ID: <code x-text="selectedNodeId"></code>
    · Type: <span x-text="dagNodeStates[selectedNodeId]?.type || 'agent'"></span>
  </div>
</div>

<!-- Drawer backdrop — click to close -->
<div
  x-show="selectedNodeId !== null"
  @click="closeNodeDrawer()"
  class="fixed inset-0 bg-black/20 z-40"
  style="display: none;"
></div>
```

**Note on `style="display: none;"`:** Alpine.js uses CSS `display` to implement `x-show`. The `style="display: none;"` on the element prevents a flash of the drawer on page load before Alpine initializes. This is the official Alpine pattern for hiding initially-invisible `x-show` elements.

---

## 10. Pipeline Run History Panel

### Where to Place It

Add this as a new card in the **right column** (`w-72 shrink-0` div), after the "Agent Activity" card and before the "Opportunity Queue" card. It shows only when a lead is selected.

```html
<!-- Pipeline Run History (shown when a lead is selected) -->
<div x-show="selectedLead && pipelineRuns.length > 0" class="card bg-base-100 shadow">
  <div class="card-body">
    <h3 class="card-title text-sm">
      Pipeline History
      <span class="badge badge-primary badge-sm" x-text="pipelineRuns.length"></span>
    </h3>

    <div class="space-y-1.5 max-h-64 overflow-y-auto">
      <template x-for="run in pipelineRuns" :key="run.run_id">
        <div class="bg-base-200 rounded p-2">
          <div class="flex justify-between items-start gap-1">
            <span
              class="text-xs font-mono truncate"
              x-text="run.pipeline_name?.replace(/_/g, ' ')"
            ></span>
            <span
              class="badge badge-xs shrink-0"
              :class="{
                'badge-success': run.status === 'completed',
                'badge-error':   run.status === 'failed',
                'badge-info':    run.status === 'running',
                'badge-warning': run.status === 'paused',
                'badge-ghost':   !['completed','failed','running','paused'].includes(run.status),
              }"
              x-text="run.status"
            ></span>
          </div>

          <div class="text-xs text-base-content/50 mt-0.5"
               x-text="run.started_at?.substring(0, 16)?.replace('T', ' ')"></div>

          <!-- Duration calculation -->
          <template x-if="run.completed_at && run.started_at">
            <div class="text-xs text-base-content/40" x-text="
              (function() {
                const s = new Date(run.started_at);
                const e = new Date(run.completed_at);
                const ms = e - s;
                return ms < 60000
                  ? Math.round(ms / 1000) + 's'
                  : Math.round(ms / 60000) + 'm ' + Math.round((ms % 60000) / 1000) + 's';
              })()
            "></div>
          </template>

          <!-- View button — loads definition + subscribes to SSE -->
          <div class="flex justify-end mt-1.5">
            <button
              class="btn btn-ghost btn-xs"
              :class="activeRunId === run.run_id ? 'btn-active' : ''"
              @click="viewRun(run)"
            >
              <span x-text="activeRunId === run.run_id ? 'Viewing' : 'View DAG'"></span>
            </button>
          </div>
        </div>
      </template>
    </div>
  </div>
</div>
```

---

## 11. Reasoning Trail Component

### Purpose

The reasoning trail links the three artifacts the inbound_responder pipeline produces for a lead: `profile.md` → `strategy-memo.md` → draft. These already exist as Alpine state (`leadDetail.profile_md`, `strategyMemoMd`, `draftContent`) but are shown in separate tabs. The reasoning trail gives a compact "show the chain" button group.

### HTML — Add as a New Tab

Add a `"pipeline"` tab to the existing tab list in the lead detail section:

```html
<!-- In the tabs tablist, add after Meetings tab: -->
<a role="tab" class="tab" :class="activeTab === 'pipeline' && 'tab-active'" @click="activeTab='pipeline'">
  Pipeline
  <span x-show="showDagPanel" class="badge badge-info badge-xs ml-1">live</span>
</a>
```

Then add the pipeline tab panel after the meetings panel (before the closing `</div>` of the lead detail `x-show` block):

```html
<!-- Pipeline tab — DAG canvas + reasoning trail -->
<div x-show="activeTab === 'pipeline'">

  <!-- Reasoning trail: wiki state chain -->
  <div class="mb-4">
    <h3 class="text-sm font-semibold mb-2 text-base-content/70">Reasoning Trail</h3>
    <div class="flex gap-2 flex-wrap">

      <!-- Profile.md badge -->
      <div
        class="badge gap-1 cursor-pointer"
        :class="leadDetail?.profile_md ? 'badge-success' : 'badge-ghost'"
        @click="activeTab = 'profile'"
        title="Click to view profile"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414A1 1 0 0121 9.414V19a2 2 0 01-2 2z" />
        </svg>
        profile.md
        <span x-show="leadDetail?.profile_md" class="text-xs">✓</span>
        <span x-show="!leadDetail?.profile_md" class="text-xs opacity-60">missing</span>
      </div>

      <span class="text-base-content/30 self-center">→</span>

      <!-- Strategy memo badge -->
      <div
        class="badge gap-1 cursor-pointer"
        :class="strategyMemoMd ? 'badge-success' : 'badge-ghost'"
        @click="activeTab = 'strategy'"
        title="Click to view strategy memo"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.347.347a3.5 3.5 0 01-4.95 0l-.347-.347z" />
        </svg>
        strategy-memo
        <span x-show="strategyMemoMd" class="text-xs">✓</span>
        <span x-show="!strategyMemoMd" class="text-xs opacity-60">missing</span>
      </div>

      <span class="text-base-content/30 self-center">→</span>

      <!-- Draft badge -->
      <div
        class="badge gap-1 cursor-pointer"
        :class="draftContent ? (draftContent.status === 'pending' ? 'badge-warning' : 'badge-success') : 'badge-ghost'"
        title="Draft status"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
        </svg>
        draft
        <span x-show="draftContent" x-text="draftContent?.status" class="text-xs"></span>
        <span x-show="!draftContent" class="text-xs opacity-60">none</span>
      </div>
    </div>
  </div>

  <!-- DAG Canvas loading state -->
  <template x-if="dagLoading">
    <div class="flex items-center gap-2 text-sm text-base-content/50 py-4">
      <span class="loading loading-spinner loading-sm"></span>
      Loading pipeline definition…
    </div>
  </template>

  <!-- DAG Canvas -->
  <div x-show="showDagPanel && dagLayout && !dagLoading">
    <div class="flex items-center justify-between mb-2">
      <h3 class="text-sm font-semibold text-base-content/70" x-text="dagPipeline?.name || 'Pipeline'"></h3>
      <div class="flex gap-1 items-center">
        <span x-show="sseConnection" class="badge badge-info badge-xs">
          <span class="loading loading-ring loading-xs mr-1"></span>
          live
        </span>
        <span x-show="activeRunId && !sseConnection" class="badge badge-ghost badge-xs">completed</span>
      </div>
    </div>

    <!-- Scrollable SVG container -->
    <div id="dag-canvas-container" class="border border-base-200 rounded-lg bg-base-50">
      <svg id="dag-canvas"></svg>
    </div>

    <p class="text-xs text-base-content/40 mt-1">Click a node to view agent output</p>
  </div>

  <!-- Empty state: no DAG loaded yet, but runs exist -->
  <template x-if="!showDagPanel && !dagLoading && pipelineRuns.length > 0">
    <div class="text-sm text-base-content/40 italic py-4">
      Select a run from Pipeline History to view its DAG.
    </div>
  </template>

  <!-- Empty state: no runs at all -->
  <template x-if="!showDagPanel && !dagLoading && pipelineRuns.length === 0">
    <div class="text-sm text-base-content/40 italic py-4">
      No pipeline runs for this lead yet.
    </div>
  </template>

</div>
```

---

## 12. HTML Layout — Where to Insert Things

This section gives precise insertion instructions for `static/dashboard.html`.

### 12.1 `<head>` additions (order matters)

```
EXISTING:  <script src="https://cdn.tailwindcss.com"></script>
EXISTING:  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
ADD HERE:  <script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
ADD HERE:  <script src="https://cdn.jsdelivr.net/npm/dagre@0.8.5/dist/dagre.min.js"></script>
ADD HERE:  <style> ... pulse-border animation ... </style>
EXISTING:  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
```

D3 and dagre must be synchronous (no `defer`) so they are available when Alpine initializes.

### 12.2 `<body>` additions

```
EXISTING:  <main ...>
             <!-- Left column: Lead list -->  (unchanged)

             <!-- Center column: Lead detail -->
               <!-- Tabs: add "Pipeline" tab to tablist -->
               <!-- Tab panels: add pipeline panel after meetings panel -->

             <!-- Right column -->
               <!-- Agent Activity (unchanged) -->
ADD HERE:      <!-- Pipeline Run History panel -->
               <!-- Opportunity Queue (unchanged) -->
               ...
           </main>

ADD HERE:  <!-- Node Output Drawer (fixed overlay) -->
ADD HERE:  <!-- Drawer backdrop -->

EXISTING:  <script>
             function dashboard() { return { ... } }
           </script>
```

### 12.3 `<script>` additions (inside the `<script>` block)

Add `computeDagLayout` and `renderDagSvg` as **top-level functions** in the script block, **before** the `dashboard()` function:

```html
<script>
  // --- DAG utilities (top-level, not inside dashboard()) ---
  const STATUS_COLORS = { ... };
  function computeDagLayout(nodes, edges) { ... }
  function renderDagSvg(svgSelector, layout, nodeStates, onNodeClick) { ... }

  // --- existing Alpine component ---
  function dashboard() {
    return {
      // existing fields...
      // NEW fields from section 4.1...

      async init() {
        await this.refresh();
        setInterval(() => this.refresh(), 5000);
      },

      // existing methods...
      // NEW methods from section 4.2...
    }
  }
</script>
```

### 12.4 `renderDag()` call sites

| Where | When to call |
|-------|-------------|
| `loadPipelineDefinition()` | After computing `dagLayout`, inside `$nextTick` |
| `subscribeToPipelineRun()` → `updateNode()` | Inside every SSE event handler, via `$nextTick` |
| `subscribeToPipelineRun()` → `pipeline_completed` | After closing SSE |
| `selectLead()` — auto-open for active run | After `loadPipelineDefinition()` resolves |

**Never** call `renderDag()` directly from Alpine template bindings (`:class`, `x-text`, etc.) — this causes infinite render loops. Only call it from methods.

### 12.5 Tab switching side effect

When the user clicks the "Pipeline" tab, the SVG container becomes visible but the SVG may be empty if `renderDag()` was called before the element was in the visible DOM subtree. Add a tab-switch watcher:

```js
// Inside dashboard() returned object, alongside other methods:
switchTab(tab) {
    this.activeTab = tab;
    if (tab === 'pipeline' && this.dagLayout) {
        this.$nextTick(() => this.renderDag());
    }
},
```

Then change all `@click="activeTab='pipeline'"` to `@click="switchTab('pipeline')"` in the tab list.

---

## 13. Full Integration Checklist

Use this checklist to verify the integration is complete before testing:

**CDN and CSS**
- [ ] `d3@7` script added to `<head>` (no `defer`, before Alpine)
- [ ] `dagre@0.8.5` script added to `<head>` (no `defer`, before Alpine)
- [ ] `@keyframes pulse-border` CSS added to `<style>` in `<head>`
- [ ] `.node-running rect` animation rule added

**Backend endpoints**
- [ ] `GET /pipeline/definition/{pipeline_name}` implemented and returns `{name, nodes[{id, agent_class, depends_on, type}]}`
- [ ] `GET /pipeline/stream/{run_id}` implemented as SSE with `text/event-stream` content-type
- [ ] `GET /pipeline/runs?lead_id=` implemented
- [ ] Router registered in `api/main.py` (if new file) — likely already on `/pipeline` prefix

**Alpine state**
- [ ] `dagPipeline`, `dagLayout`, `dagNodeStates`, `activeRunId`, `sseConnection`, `selectedNodeId`, `pipelineRuns`, `showDagPanel`, `dagLoading` added to `dashboard()` return object
- [ ] `loadPipelineDefinition()`, `loadPipelineRuns()`, `subscribeToPipelineRun()`, `unsubscribeFromRun()`, `renderDag()`, `openNodeDrawer()`, `closeNodeDrawer()`, `viewRun()`, `switchTab()` methods added
- [ ] `selectLead()` updated to call `loadPipelineRuns()` and auto-open DAG for active runs

**Top-level JS functions**
- [ ] `STATUS_COLORS` constant defined before `dashboard()`
- [ ] `computeDagLayout(nodes, edges)` defined before `dashboard()`
- [ ] `renderDagSvg(svgSelector, layout, nodeStates, onNodeClick)` defined before `dashboard()`

**HTML changes**
- [ ] "Pipeline" tab added to lead detail tab list with `switchTab('pipeline')` handler
- [ ] Pipeline tab panel added after meetings panel (DAG canvas + reasoning trail)
- [ ] `<svg id="dag-canvas">` inside `<div id="dag-canvas-container">` in pipeline tab
- [ ] Pipeline Run History card added to right column
- [ ] Node Output Drawer HTML added before `</body>`
- [ ] Drawer backdrop HTML added before `</body>`
- [ ] Existing tab `@click` handlers updated to use `switchTab()` if you want tab-switch re-render (optional but recommended)

**Smoke test sequence**
1. Open dashboard, select a lead that has a completed pipeline run
2. Run History panel should appear in right column with ≥1 entry
3. Click "View DAG" on a completed run → Pipeline tab opens, SVG renders with colored nodes
4. Click a completed node → drawer slides in showing agent output
5. Trigger a new pipeline run for the same lead via POST to `/pipeline/run/{name}`
6. Observe nodes turning blue (running) then green (completed) in real-time
7. Verify pulse animation on the currently-running node
8. On pipeline_completed, SSE closes, "live" badge disappears, "completed" badge appears

---

*Guide version: 2026-04-15 — covers PRD 6 Phase 3 frontend requirements.*
*Backend stubs in §3 are provisional — the backend implementer should adapt them to the actual DAG executor SSE broadcast mechanism when PRD 6 Phase 2 backend work lands.*
