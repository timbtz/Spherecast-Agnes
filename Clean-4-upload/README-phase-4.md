# Agnes — phase-4 branch walkthrough

This branch is where the reasoning scaffold lives — everything that turns raw
enrichment data into auditable substitution proposals. If you just merged
`master` into `phase-4` and ran `reorganize-phase-4.sh`, the layout below is
what you should see.

---

## TL;DR — how phase-4 plugs into master

```
               enrichment/                  reasoning/
master owns:   (Tim — Stage 2 pipeline)     (Gursagar — Stage 2 Phase 4 scaffold)
                       │                              │
                       ▼                              ▼
                 db_enriched.sqlite  ◀──reads/writes──┘
                       │
                       ▼
phase-4 adds:    orchestration/              ← Tim's Stage 3 ADK agents
                 ├── agents/                   (router, proactive, reactive,
                 ├── pipelines/                 research, proposal_writer,
                 ├── tools/                     search_sub_agent, adk_runner)
                 ├── schema/
                 ├── api/
                 └── ui/
```

Phase-4's job is to add the reasoning + orchestration layer on top of the
Stage-2 data that's already sitting in `db_enriched.sqlite` on master.

---

## Directory layout

```
Spherecast-Agnes/                       # (branch: phase-4)
│
├── .claude/                   Claude Code skills and slash commands
├── .env.template              Copy to .env and fill keys (never commit .env)
├── .gitignore                 Blocks __pycache__, .env, *.sqlite, caches
├── CLAUDE.md                  Agent self-maintained run-state log
├── README.md                  Top-level contributor guide (project-wide)
├── README-phase-4.md          THIS FILE — phase-4 branch walkthrough
├── requirements.txt
│
├── Orchestration/             DOCS (capital O) — PRDs, plans, wiki, refs
│   ├── PRDs/                  meta-workflow.md, PRD.md, SQLBackendPRD.md
│   ├── Plans/                 Step-by-step execution plans
│   ├── References/            One *-guide.md per API / tool
│   ├── Wiki/                  LLM-maintained reasoning pages (Stage 3+)
│   └── Data/                  llm-wiki.md reference, Spherecast context
│
├── orchestration/             CODE (lowercase o) — Stage 3 agents
│   ├── __init__.py
│   ├── agents/
│   │   ├── router_agent.py          top-level dispatcher
│   │   ├── proactive_agent.py       consolidation ranking runner
│   │   ├── reactive_agent.py        supplier-fallout → alternative
│   │   ├── research_agent.py        net-new supplier discovery
│   │   ├── proposal_writer.py       final proposal text generation
│   │   ├── search_sub_agent.py      Google ADK web search wrapper
│   │   └── _adk_runner.py           ADK session / runner helper
│   ├── api/                   FastAPI (or equivalent) endpoint layer
│   ├── pipelines/             DAG definitions wiring agents together
│   ├── schema/                pydantic / JSON schemas for tool I/O
│   ├── tools/                 MCP-style tool fns the agents call
│   └── ui/                    Stage 4 frontend (placeholder)
│
├── enrichment/                Stage 2 pipeline (owned on master)
│   ├── pipeline.py            Entry: python pipeline.py --phase 1|2|3
│   ├── db_bootstrap.py        Clone db.sqlite → db_enriched.sqlite
│   ├── db_migrate_v11.py      v1.1 migration (idempotent)
│   ├── backfill_phase1.py
│   ├── run_dedup.py
│   ├── sources/               pubchem.py, dsld.py, molport.py, …
│   ├── normalizers/           ingredient_normalizer, fuzzy_matcher
│   ├── parsers/               sku_parser.py
│   └── enrichers/             quantity, commercial, compliance
│
├── reasoning/                 Stage 2 Phase 4 + substitution engine
│   ├── consolidation_scorer.py   Formula: C·0.40 + B·0.25 + F·0.20 + S·0.15
│   ├── substitution_graph.py     Builds ingredient equivalence edges
│   ├── proposal_generator.py     Claude-adjusted proposal text
│   ├── gate_engine.py            6-gate substitution (canonical/role/form/
│   │                             grade/morphology/regulatory)
│   ├── compliance_reasoner.py    4-state dual-rule compliance outcomes
│   ├── refusal_engine.py         Hard 0.60 confidence floor
│   └── qualify_candidate.py      ToolResult wrapper + evidence ledger hook
│
├── schema/
│   └── enriched_schema.sql    v1.1 locked (v1.2 additive migration pending)
│
├── scripts/                   One-off maintenance scripts (from master)
│
└── docs/                      Human handoff notes (was tim-package/)
    ├── phase4-package-readme.md   Gursagar's drop-in package overview
    ├── integration-handoff.md     What Tim needs to wire against
    ├── missing-data-schema.md     Enrichment gaps the scaffold exposes
    ├── run-instructions.md        One-time setup + how to run the chain
    ├── example-output.md          Sample reasoning-chain output
    └── demo-results.md            Real-data run across top-4 opportunities
```

> **Rule of thumb.** `Orchestration/` (capital O) = docs. `orchestration/`
> (lowercase o) = code. Tim set this convention on master; phase-4 now follows it.

---

## What got cleaned up (and why)

The pre-reorg phase-4 branch had a few things that made it confusing to read:

| Removed / moved                            | Reason                                      |
| ------------------------------------------ | ------------------------------------------- |
| `phase-4-scaffold/`                        | Full duplicate tree from initial bootstrap  |
| `tim-package/Orchestration/`               | Duplicate of root `Orchestration/` docs     |
| `tim-package/patches/`                     | Duplicate copies of `reasoning/*.py` files  |
| `tim-package/01-integration-handoff.md`    | → moved to `docs/integration-handoff.md`    |
| `tim-package/02-missing-data-schema.md`    | → moved to `docs/missing-data-schema.md`    |
| `.env` (tracked)                           | Untracked via `git rm --cached` — keys leak |
| `db.sqlite`, `db_enriched.sqlite` (tracked) | Binary DBs — untracked, rebuilt locally     |
| `**/__pycache__/` (tracked)                | Untracked; `.gitignore` now blocks them     |

Everything non-trivial that lived under `tim-package/` (handoff markdown) is
preserved under `docs/`. Nothing was deleted from git history — just removed
from the working tree of phase-4.

---

## How to work on phase-4

### First-time setup
```bash
git checkout phase-4
git pull
cp .env.template .env          # then fill ANTHROPIC_API_KEY, GOOGLE_API_KEY, DSLD_API_KEY
pip install -r requirements.txt
playwright install chromium
python enrichment/db_bootstrap.py   # creates db_enriched.sqlite locally
```

### Run the Stage-2 enrichment (already complete — safe to re-run)
```bash
python enrichment/pipeline.py --phase 1
python enrichment/backfill_phase1.py
python enrichment/run_dedup.py
python enrichment/pipeline.py --phase 2
python enrichment/pipeline.py --phase 3
python reasoning/consolidation_scorer.py
```

### Run a Stage-3 agent (ADK)
```bash
python -m orchestration.agents._adk_runner --agent proactive
# or
python -m orchestration.agents._adk_runner --agent reactive --supplier-id <id>
```

### Validate the reasoning scaffold
```bash
python -m reasoning.gate_engine --run-scenarios
# expect: 6/6 scenarios pass, evidence ledger populated
```

---

## Where to pick up next (as of this reorg)

1. **Wire `qualify_candidate.py` against real `db_enriched.sqlite`** rather than
   the stub fixture — it's currently returning mocked rows.
2. **Finish `orchestration/agents/router_agent.py`** — the dispatcher that
   picks reactive vs proactive vs research based on the trigger payload.
3. **Extend the jurisdiction packs** in `reasoning/compliance_reasoner.py`
   (currently US + EU; Playbook asks for at least CA and JP before demo).
4. **Open the PR from `phase-4` → `master`** once the above are green.
   The merge should now be conflict-free because phase-4 has been
   aligned to Tim's layout.
5. **Rotate `.env`** — the old committed copy is now in git history; any
   keys that were in it should be considered exposed and replaced.

---

## Pointers if you get lost

- Architecture rationale: `Orchestration/PRDs/meta-workflow.md`
- Live run state: `CLAUDE.md`
- Locked schema: `schema/enriched_schema.sql`
- Wiki pattern (Stage 3 reasoning persistence): `Orchestration/Data/llm-wiki.md`
- Tim's integration handoff notes: `docs/integration-handoff.md`
- Gaps Tim flagged against the schema: `docs/missing-data-schema.md`
