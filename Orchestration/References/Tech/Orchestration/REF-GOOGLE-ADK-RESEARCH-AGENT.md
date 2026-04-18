# REF-GOOGLE-ADK-RESEARCH-AGENT

**Audience:** Implementation agents completing `ResearchAgent` for the HappyRobot Sales Intelligence platform.
**Last updated:** 2026-04-15
**Status:** Authoritative — use this document alongside ARCHITECTURE-RESOLUTIONS.md for all ResearchAgent work.

---

## Quick Facts

| Property | Value |
|---|---|
| Agent file | `agents/research_agent.py` |
| Model | `gemini-2.5-flash` |
| System prompt file | `prompts/agents/research.md` |
| Pipeline | `new_lead_onboarding` — node `web-research` |
| Depends on | `lead-discovery` |
| Followed by | `lead-classification` |
| Primary output | `leads/{lead_id}/research-notes.md` |
| Secondary output | `leads/{lead_id}/company.md` (optional) |
| Forbidden write | `leads/{lead_id}/profile.md` — NEVER (compile.py domain) |

> **IMPORTANT:** The existing stub in `prompts/agents/research.md` was written for the `inbound_responder` pipeline (where a `profile.md` already exists). It is incorrect for `new_lead_onboarding` and must be replaced with the prompt in §5 of this document.

---

## 1. `google_search` Tool Reference

### 1.1 What it is

`google.adk.tools.google_search` is a **built-in grounding tool** for the Google Agent Development Kit. It is not a callable function that returns a Python dict; instead, it triggers Gemini's **Google Search grounding mechanism** internally. The model decides when to invoke it, formulates one or more search queries, receives grounding results, and incorporates them into its response — all within the same token generation step.

This means: **the agent cannot programmatically inspect individual search result dicts.** The LLM reads the grounded content and produces its text output. The raw results are surfaced to the model as context, not as structured Python objects your code can iterate over.

### 1.2 What the model receives from a grounding call

When grounding fires, the Gemini API populates `groundingMetadata` on the response candidate. The relevant fields surfaced to the model as context are:

```
groundingChunks[]
  .web.uri        — URL of the source page
  .web.title      — Page title

groundingSupports[]
  .segment.text   — Sentence in the model's answer
  .groundingChunkIndices[]  — Which groundingChunks back this sentence

webSearchQueries[]  — Actual queries submitted to Google Search

searchEntryPoint
  .renderedContent  — HTML snippet for Google's "search suggestions" UI
```

In practice, `groundingChunks` provides **5–10 web sources per model call**, each with a title and URL. Snippets (the 150–300 character text excerpts) appear in `groundingSupports.segment.text` as sentences the model generated, not as raw extracted text. The model sees the underlying page content during generation but does not return it as a raw field.

### 1.3 Known limitation: grounding chunks not always populated in ADK runner events

A known issue in `google/adk-python` (tracked as issue #1693 and #3287) means that `grounding_chunks` and `grounding_supports` may not be populated in ADK `runner.run_async()` event objects even when search grounded successfully. The **model output text** is still grounded and correct — the metadata is just not reliably surfaced in Python-side events. Do not write code that depends on parsing `event.grounding_metadata.grounding_chunks` at runtime.

### 1.4 Number of search calls and results

- The model internally decides how many search queries to run within a single `run_async()` call. Each `google_search` "call" from the model's perspective may submit multiple queries to the index.
- Typical result: **5–10 grounded web sources** per model generation step that triggers search.
- You control total search usage by instructing the model in the system prompt to limit itself to N generation steps that invoke search. In this guide: **MAX 5 google_search invocations** per pipeline run.
- There is no hard-coded "results per call" parameter the agent controls.

### 1.5 What happens with no results

If Google Search returns no results (extremely rare), or the grounding service is unreachable, the model receives no grounding chunks and generates its answer from training knowledge only. The model will not raise an exception. The prompt must instruct the agent to detect this (no URLs cited, no factual data found) and write `status: no_results_found` in `research-notes.md`.

### 1.6 What happens on rate limit / quota

`google_search` uses the Gemini API's built-in grounding quota, billed per prompt (not per search query). There is no separate per-call rate limit distinct from the Gemini API quota. If the API returns a quota error, it surfaces as an exception from `runner.run_async()`, which `execute_node` in `dag_executor.py` catches and converts to a `node_failed` event.

### 1.7 Compatibility requirement

`google_search` is only compatible with **Gemini 2.x and later models**. `gemini-2.5-flash` is fully compatible. Do not switch to `gemini-1.x` for this agent.

### 1.8 Tool combination constraint

ADK enforces a restriction: **you cannot mix `google_search` with `code_execution` in the same agent**. However, you CAN combine `google_search` with custom function tools (like `read_file`, `write_file`, `list_directory`, `search_wiki`). The `research_agent` in `agents/research_agent.py` does exactly this — this combination is supported and is the correct pattern.

---

## 2. Pipeline Context for ResearchAgent

### 2.1 The `user_message` received by the agent

`execute_node()` in `api/dag_executor.py` constructs the `user_message` as follows (from the actual implementation at line 664–670):

```
Pipeline: new_lead_onboarding
Lead: {lead_id}
Lead wiki path: {lead_path}
Channel: {channel}
Run ID: {run_id}
Context: {json.dumps(context.to_dict())}
```

Example for a real lead:

```
Pipeline: new_lead_onboarding
Lead: logistics/dhl/anna-meyer
Lead wiki path: leads/logistics/dhl/anna-meyer
Channel: email
Run ID: f3a2c1d0-9e8b-4a7c-b5d6-1234567890ab
Context: {
  "run_id": "f3a2c1d0-9e8b-4a7c-b5d6-1234567890ab",
  "lead_id": "logistics/dhl/anna-meyer",
  "lead_path": "leads/logistics/dhl/anna-meyer",
  "lead_display": "Anna Meyer — DHL",
  "pipeline_name": "new_lead_onboarding",
  "channel": "email",
  "job_id": "logistics-dhl-anna-meyer-1713456000",
  "discovery_name": "Anna Meyer",
  "discovery_email": "anna.meyer@dhl.com",
  "discovery_company_hint": "DHL",
  "discovery_channel": "email",
  "existing_company_found": false,
  "existing_lead_found": false,
  "candidate_wiki_path": "",
  "candidate_industry": "logistics",
  "candidate_company_slug": "dhl",
  "discovery_context_summary": "No prior DHL contact found in wiki.",
  "discovery_confidence": 0.4
}
```

### 2.2 What the agent can read from the wiki at execution time

At the point `web-research` runs, the following files may exist. The agent should try to read them in this order:

| File path | Exists? | Contents |
|---|---|---|
| `leads/{lead_id}/pipeline-context.json` | Always | Full pipeline context including `discovery_*` fields from LeadDiscoveryAgent |
| `leads/{lead_id}/email/raw/*.md` | Yes (at least one) | The raw inbound email that triggered onboarding — contains company name, person name, message body |
| `leads/{lead_id}/discovery-notes.md` | Maybe | LeadDiscoveryAgent writes this if it found prior context in the wiki |
| `leads/{lead_id}/profile.md` | NO | Does NOT exist yet for new leads — this is written later by `LeadClassificationAgent` via `compile.py` |
| `leads/{lead_id}/company.md` | Maybe | May exist if the company has been contacted before via a different person |

The most important reads are `pipeline-context.json` (for structured metadata) and the raw email file (for the actual message text from which person name and company are extracted).

### 2.3 How to find the raw email file

```
list_directory("leads/{lead_id}/email/raw/")
→ entries: ["2026-04-15T10-30-00-inbound.md"]

read_file("leads/{lead_id}/email/raw/2026-04-15T10-30-00-inbound.md")
→ full email content: subject, from, body
```

The email body is the primary source for extracting the lead's name and company if `discovery_name`/`discovery_company_hint` in the context are empty or low-confidence.

---

## 3. Write Domain for ResearchAgent

### 3.1 Authoritative write table

Per `Orchestration/ARCHITECTURE-RESOLUTIONS.md` §1.1:

| File | Can write? | Reason |
|---|---|---|
| `leads/{lead_id}/research-notes.md` | **YES** | Primary output — ResearchAgent's core deliverable |
| `leads/{lead_id}/company.md` | **YES** | Company enrichment supplement (only if company data found) |
| `leads/{lead_id}/pipeline-context.json` | **YES** | Update with `research_*` fields so LeadClassificationAgent can read them |
| `leads/{lead_id}/profile.md` | **NO** | `compile.py` domain only — NEVER touch this file |
| `leads/{lead_id}/strategy-memo.md` | **NO** | StrategyAgent domain only |
| `leads/{lead_id}/drafts/*.md` | **NO** | ResponseAgent domain only |
| `wiki/index.md` | **NO** | KnowledgeCurationAgent domain |
| `wiki/seller/**` | **NO** | Read-only at agent runtime (enforced by `write_file` in `tools/file_tools.py`) |

### 3.2 What `write_file` enforces vs. what the prompt must enforce

`tools/file_tools.py` `write_file()` enforces exactly one restriction programmatically: it **rejects all `seller/` paths** with a `PermissionError`. All other path restrictions (including the `profile.md` prohibition) are **prompt-only** — there is no code guard preventing the agent from writing `profile.md`. The system prompt must be explicit that this is forbidden.

If you want to add a hard guard, add this check to `write_file()` in `tools/file_tools.py`:

```python
def write_file(wiki_root: Path, path: str, content: str) -> str:
    if path.startswith("seller/"):
        raise PermissionError("write_file: seller/ paths are read-only at agent runtime")
    # Hard guard against compile.py-owned files
    if path.endswith("/profile.md") or path.endswith("/summary.md"):
        raise PermissionError(
            f"write_file: {path} is compile.py domain — agents must not write this file"
        )
    ...
```

This is a recommended hardening step. Until it is added, the system prompt is the sole enforcement layer for the `profile.md` restriction.

---

## 4. `research-notes.md` Output Schema

This is the **canonical schema** that `LeadClassificationAgent` consumes. Any deviation will break the classification step. Do not alter this schema without updating `prompts/agents/lead_classification.md`.

```markdown
---
lead_id: {lead_id}
research_date: 2026-04-15T10:45:00Z
search_queries_run: 4
status: enriched
---

# Research Notes — Anna Meyer, DHL

## Company Overview
DHL Express is a division of Deutsche Post DHL Group, a global logistics and parcel delivery
company headquartered in Bonn, Germany. With over 380,000 employees in 220+ countries, DHL
is the world's largest international express mail service. The company operates across four
main divisions: Express, Parcel Germany, Global Forwarding/Freight, and Supply Chain.

## Recent News (last 90 days)
- DHL announced a €2B investment in European warehouse automation (March 2026) ([source](https://...))
- Deutsche Post DHL Group reported Q1 2026 revenue of €24.1B, up 4% YoY ([source](https://...))
- No significant leadership changes at DHL Express found in this period.

## Person Profile
Anna Meyer holds the title of Head of Procurement — Digital Solutions at DHL Express (per
LinkedIn and DHL corporate directory). Tenure: ~3 years at DHL. Background in supply chain
technology procurement; previously at Siemens Logistics. No published articles or speaking
events found in the past 90 days.

## Key Decision Makers
- Frank Appel — CEO, Deutsche Post DHL Group
- Ken Allen — CEO, DHL Express (relevant for enterprise-level deals)
- No specific procurement leadership beyond Anna Meyer found at the Express division level.

## Competitive Context
DHL Express competes with FedEx International, UPS Worldwide, and TNT (now FedEx). In the
logistics technology and digital solutions space, DHL is known to use SAP for ERP, Salesforce
for CRM, and has active vendor relationships with IBM and Accenture. They are evaluating
AI-based route optimization tools (per March 2026 press release).

## Research Confidence
medium — Company data is well-sourced from public records; person-specific data (title,
background) inferred from LinkedIn search results which may be slightly outdated.
```

### 4.1 Status values

| Status | Meaning |
|---|---|
| `enriched` | Substantive data found for both company and person |
| `partial` | Company data found but person profile thin (or vice versa) |
| `no_results_found` | All search queries returned no usable results |

### 4.2 Fields LeadClassificationAgent reads from `research-notes.md`

`LeadClassificationAgent` reads `research-notes.md` to populate `profile.md`. The fields it specifically looks for:

- **Company Overview** — used for `company` field and classification into industry folder
- **Person Profile** — used for `display_name`, `title` inference, and the profile body summary
- **Research Confidence** — influences `discovery_confidence` written to `pipeline-context.json`
- **status** frontmatter field — if `no_results_found`, classification agent falls back to `unclassified/` path with `needs_clarification: true`

### 4.3 Update `pipeline-context.json` after writing `research-notes.md`

After writing `research-notes.md`, ResearchAgent must update `pipeline-context.json` with these fields so LeadClassificationAgent can access them without re-reading the file:

```json
{
  "research_status": "enriched",
  "research_notes_path": "leads/logistics/dhl/anna-meyer/research-notes.md",
  "research_company_name": "DHL Express",
  "research_person_title": "Head of Procurement — Digital Solutions",
  "research_confidence": "medium",
  "research_date": "2026-04-15T10:45:00Z"
}
```

---

## 5. Complete `prompts/agents/research.md` System Prompt

This is the **main deliverable** of this guide. Replace the contents of `prompts/agents/research.md` with the following verbatim:

```markdown
You are ResearchAgent for HappyRobot, an AI sales intelligence platform.

## Your Role

You are the `web-research` node in the `new_lead_onboarding` pipeline. You run after
LeadDiscoveryAgent has searched the internal wiki, and before LeadClassificationAgent
writes the lead's profile. Your job is to enrich a brand-new, unknown inbound lead with
publicly available web intelligence so that LeadClassificationAgent can make an informed
classification decision.

This is a NEW lead — `profile.md` does NOT exist yet. Do not attempt to read or write it.

## Your Task

Given a new lead who has just sent an inbound message, research them and their company
using google_search. Write your findings to `leads/{lead_id}/research-notes.md`.

## Step-by-Step Instructions

### Step 1 — Read context

Read `pipeline-context.json` from the lead's wiki path:

```
read_file("leads/{lead_id}/pipeline-context.json")
```

Extract these fields (they were written by LeadDiscoveryAgent):
- `discovery_name` — lead's full name (may be empty)
- `discovery_email` — lead's email address (may be empty)
- `discovery_company_hint` — company name hint (may be empty)
- `discovery_channel` — inbound channel (email, linkedin, etc.)
- `discovery_confidence` — float 0.0–1.0; how confident LeadDiscoveryAgent was in its findings
- `discovery_context_summary` — any prior wiki context found (may be "No prior context found")

### Step 2 — Read the inbound message

List the raw email/message directory to find the inbound file:

```
list_directory("leads/{lead_id}/{channel}/raw/")
```

Read the most recent file. Extract:
- Lead's full name (from email signature or "From:" header)
- Company name (from email domain, signature, or message body)
- Message context (what are they asking about?)

If `discovery_name` from Step 1 is already populated and high-confidence, you can skip
this step. But if the company hint is weak or empty, the raw message is your best source.

### Step 3 — Determine search subjects

From Steps 1 and 2, establish:
- `company_name` — the best-known name for the company (e.g. "DHL Express", "Acme Corp")
- `person_name` — the lead's full name
- `person_email_domain` — the domain from their email (e.g. "dhl.com")

If company name is entirely unknown after Steps 1 and 2, use the email domain as the
company identifier for search queries.

### Step 4 — Run google_search (MAX 5 calls)

Execute the following search strategy in order. Stop early if you have sufficient data
(a clear company overview + person profile). Do NOT run all 5 if the first 3 are
sufficient.

**Search 1 (always run):**
`"{company_name}" company overview logistics [or relevant industry]`

**Search 2 (always run):**
`"{company_name}" news 2026`

**Search 3 (run if person not yet found):**
`"{person_name}" "{company_name}" LinkedIn OR title OR role`

**Search 4 (run if industry/competitors not yet clear):**
`"{company_name}" competitors market OR industry OR funding`

**Search 5 (fallback only — use if company name is in non-English or results are thin):**
`site:{email_domain} OR "{email_domain}" company B2B`

**Hard limit: do not run more than 5 google_search invocations in a single pipeline run.**

The first call returns 5–10 grounded sources. If a company is not findable in 2–3
attempts, additional searches will not help — move to writing with partial data.

### Step 5 — Write `research-notes.md`

Write the following file. Fill every section with your findings. Where you found nothing,
write the specified fallback text — do NOT leave sections empty or skip them.

Path: `leads/{lead_id}/research-notes.md`

```markdown
---
lead_id: {lead_id}
research_date: {ISO-8601 UTC timestamp, e.g. 2026-04-15T10:45:00Z}
search_queries_run: {number of google_search calls you made, 1–5}
status: {enriched | partial | no_results_found}
---

# Research Notes — {Full Name}, {Company Name}

## Company Overview
{2–4 sentences: what does this company do, industry, approximate size (employees/revenue
if found), HQ location. If nothing found: "No public company data found for {company_name}.
Domain: {email_domain}."}

## Recent News (last 90 days)
{Bullet list of notable developments: funding rounds, acquisitions, leadership changes,
product launches, major contracts, regulatory events. Cite source URLs inline as
([source](url)). Include date of each item.
If no recent news found: "No recent news found for {company_name} in the past 90 days."}

## Person Profile
{What is publicly known: job title, LinkedIn summary, tenure at company, prior employers,
published articles, speaking events. Cite sources.
If no person data found: "No public profile data found for {person_name}. Role inferred
from email domain {email_domain} only."}

## Key Decision Makers
{Other relevant contacts at the company: CTO, VP Sales, Head of Procurement, or equivalent
roles relevant to HappyRobot's services. Only include if found in search results.
If none found: "No additional decision maker data found."}

## Competitive Context
{Who are this company's main competitors? What tools or vendors do they likely use in areas
relevant to HappyRobot's offering? Any public mentions of technology stack or vendor
relationships?
If none found: "No competitive or technology stack data found for {company_name}."}

## Research Confidence
{high | medium | low} — {one sentence: explain why. E.g. "high — major public company with
extensive press coverage." or "low — company name is generic; results mixed with unrelated
entities."}
```

**Status values:**
- `enriched` — substantive data found for both company and person
- `partial` — one of company or person has meaningful data; the other is thin
- `no_results_found` — all searches returned no usable data for this company/person

### Step 6 — Optionally write `company.md`

If the company is a significant public or well-documented private company AND
`leads/{lead_id}/company.md` does not already exist, write a brief stub:

Path: `leads/{lead_id}/company.md` (or the shared path `leads/{industry}/{company}/company.md`
if you can determine the correct industry slug)

```markdown
---
company: {Company Name}
domain: {email_domain}
industry: {industry}
size_estimate: {headcount range or revenue range if found}
hq: {city, country}
founded: {year if found}
last_researched: {ISO-8601 date}
---

# {Company Name}

{2–3 sentences from Company Overview.}

## Sources
- {url 1}
- {url 2}
```

Skip this step if: (a) `company.md` already exists at the lead path, or (b) you have
only minimal data (partial/no_results_found status).

### Step 7 — Update `pipeline-context.json`

Read the current `pipeline-context.json`, merge these fields, and write it back:

```json
{
  "research_status": "{enriched | partial | no_results_found}",
  "research_notes_path": "leads/{lead_id}/research-notes.md",
  "research_company_name": "{best-known company name}",
  "research_person_title": "{job title if found, else ''}",
  "research_confidence": "{high | medium | low}",
  "research_date": "{ISO-8601 timestamp}"
}
```

Do NOT overwrite existing `discovery_*` fields — only add `research_*` fields.

### Step 8 — Output

End your response with exactly this line (no trailing content after it):

```
RESEARCH_COMPLETE: leads/{lead_id}/research-notes.md
```

This sentinel is parsed by the DAG executor to confirm the file was written.

---

## Write Domain Constraints — MANDATORY

**YOU MAY WRITE:**
- `leads/{lead_id}/research-notes.md` — primary output (REQUIRED every run)
- `leads/{lead_id}/company.md` — optional company stub
- `leads/{lead_id}/pipeline-context.json` — merge research fields only

**YOU MUST NEVER WRITE:**
- `leads/{lead_id}/profile.md` — this file does NOT exist yet and MUST be created only
  by `compile.py` after `LeadClassificationAgent` runs. Writing it here would corrupt
  the pipeline. This is a hard architectural rule (ARCHITECTURE-RESOLUTIONS §1.1).
- `leads/{lead_id}/strategy-memo.md` — StrategyAgent domain
- `leads/{lead_id}/drafts/` — ResponseAgent domain
- `wiki/index.md` — KnowledgeCurationAgent domain
- Any `seller/` path — blocked at runtime by `write_file` tool

---

## Fallback Behavior

**If all 5 searches return no usable results:**

Do not crash. Write `research-notes.md` with `status: no_results_found` and minimal
content in each section (use the "If nothing found" fallback text specified above).
Then update `pipeline-context.json` with `research_status: no_results_found`.
Output `RESEARCH_COMPLETE:` as normal.

`LeadClassificationAgent` is designed to handle `no_results_found` — it will classify
the lead as `unclassified` with `needs_clarification: true`, which is the correct outcome
for a lead with no public footprint.

**If the company name is in non-English:**

Append "company" or "B2B" to your search query. Example: `"Müller Logistik" company B2B`
or `"株式会社ロジスティクス" logistics company`. If the email domain is available, use
`site:{domain}` as a fallback.

**If the person name is extremely generic (e.g. "John Smith", "Li Wei"):**

Add the company name and email domain to the query: `"John Smith" acme.com procurement`.
If this still returns no useful person data, accept partial status and note it in Research
Confidence.

---

## Research Quality Guidelines

- Only report facts found in search results. Do not invent or infer company details.
- Cite source URLs inline for any specific claim: `([source](url))`.
- Date time-sensitive findings: `As of March 2026:`.
- If you find a result that seems to be about a different company with the same name,
  cross-reference with the email domain to disambiguate.
- Prioritize recency: news from the past 90 days is most valuable to the sales team.
- For company size: prefer official sources (LinkedIn company page, Crunchbase, annual
  report) over estimates.
- Do not include personally sensitive data beyond what is needed for B2B sales context
  (title, company, public career information).
```

---

## 6. Rate Limiting and Cost Control

### 6.1 Billing model

`google_search` grounding in Gemini API is billed **per prompt** (i.e., per `run_async()` call that triggers a grounding step), not per search query. As of April 2026, the Gemini API charges for grounding use in the `gemini-2.5-flash` tier; consult [https://ai.google.dev/pricing](https://ai.google.dev/pricing) for current rates. There is no separate per-search-call charge.

### 6.2 Natural throttle from pipeline scheduler

`RESPONSE_DELAY_SECONDS=900` (15 minutes) in the pipeline scheduler (see `api/queue.py` §2.2 of ARCHITECTURE-RESOLUTIONS) means new-lead onboarding pipelines fire at most once per 15 minutes per lead. For bulk ingestion, this throttles to approximately 4 new leads per hour. This is already safely within API quota for most production configurations.

### 6.3 Per-run search cap

The system prompt instructs **MAX 5 google_search invocations** per run. This is sufficient because:

- The first search call typically returns 5–10 grounded sources from the Google Search index.
- If a company is not findable in 2–3 attempts with different query formulations, additional searches will not improve results.
- 5 calls × (5–10 sources each) = 25–50 data points, which is more than sufficient for a lead enrichment note.

If research quality is consistently low on complex leads and you want to raise the cap, change the limit in the system prompt only — no code change required.

### 6.4 Total tokens per run

With the 5-call cap, total token consumption per ResearchAgent run is bounded:
- Input: system prompt (~600 tokens) + pipeline context (~300 tokens) + grounded content (~2000–4000 tokens) = ~3000–5000 input tokens
- Output: `research-notes.md` content (~500–800 tokens)

This is well within `gemini-2.5-flash`'s context window and cost profile.

---

## 7. Integration with Surrounding Pipeline Nodes

### 7.1 Data flow

```
[Inbound email/message arrives via webhook]
    |
    | webhook handler writes raw interaction file
    | compile_worker enqueues compile.py (builds profile stubs, not yet present)
    | pipeline_scheduler waits RESPONSE_DELAY_SECONDS
    |
    v
[new_lead_onboarding pipeline fires]
    |
    v
LeadDiscoveryAgent  (node: lead-discovery)
  - Reads: wiki search for company/name, existing leads/ directory
  - Writes: pipeline-context.json (discovery_* fields)
  - Writes: discovery-notes.md (if prior context found)
    |
    v
ResearchAgent  (node: web-research)  ← YOU ARE HERE
  - Reads: pipeline-context.json, email/raw/*.md, discovery-notes.md
  - Runs: up to 5 google_search calls
  - Writes: research-notes.md (REQUIRED), company.md (optional)
  - Updates: pipeline-context.json (research_* fields)
    |
    v
LeadClassificationAgent  (node: lead-classification)
  - Reads: pipeline-context.json (discovery_* + research_* fields), research-notes.md
  - Writes: leads/{path}/profile.md  ← THE ONLY AGENT THAT WRITES PROFILE.MD
  - Writes: leads/{industry}/{company}/company.md (if not present)
  - Updates: index.md, pipeline-context.json (classification fields)
    |
    v
StrategyAgent → ResponseAgent → ApprovalNode → SenderAgent
```

### 7.2 Fields LeadClassificationAgent reads from ResearchAgent output

`LeadClassificationAgent` (`prompts/agents/lead_classification.md`) reads `pipeline-context.json` for `research_*` fields and directly reads `research-notes.md`. The fields it consumes:

| Field | Source | Used for |
|---|---|---|
| `research_status` | `pipeline-context.json` | Decides classified vs unclassified path |
| `research_notes_path` | `pipeline-context.json` | Locates the research notes file |
| `research_company_name` | `pipeline-context.json` | Canonical company name for folder slug |
| `research_person_title` | `pipeline-context.json` | Populates `profile.md` title field |
| `research_confidence` | `pipeline-context.json` | Combined with `discovery_confidence` for final confidence score |
| **Company Overview** section | `research-notes.md` | Profile body, company.md stub |
| **Person Profile** section | `research-notes.md` | Profile body summary |
| **Research Confidence** section | `research-notes.md` | Classification confidence reasoning |

---

## 8. Model Choice Rationale

### Why `gemini-2.5-flash` (not `gemini-2.5-pro`)

| Consideration | Flash | Pro |
|---|---|---|
| Task type | Retrieval + summarization | Deep reasoning |
| Speed | Faster (lower latency per node) | Slower |
| Cost | Significantly cheaper | More expensive |
| Quality for this task | Sufficient — web research is read-and-summarize | Overkill for structured summarization |
| Context window | 1M tokens (sufficient) | 1M tokens |

Research tasks are primarily **retrieval and summarization**: find facts, write them in a structured format. This does not require multi-step reasoning chains. `gemini-2.5-flash` handles this well.

The 5-search-call constraint means total tokens per run are bounded (see §6.4). Even with flash's slightly lower quality ceiling, the grounded content it receives is factual (from Google Search), so hallucination risk is minimal.

### When to upgrade to Pro

Switch to `gemini-2.5-pro` if:
- Research quality is consistently poor on **non-English company names** (Japanese, Chinese, Arabic) where query reformulation requires cultural reasoning.
- Leads come from **obscure or niche industries** where the agent must reason about indirect signals to determine company context.
- The agent is producing factually confused outputs when two companies share similar names and the disambiguation requires reasoning about multiple signals.

To switch: change `model="gemini-2.5-flash"` to `model="gemini-2.5-pro"` in `agents/research_agent.py`. No other changes required.

---

## 9. Testing the ResearchAgent

### 9.1 Manual test invocation

```bash
# From project root
python -c "
import asyncio
from agents.research_agent import research_agent
from api.dag_executor import run_adk_agent

result = asyncio.run(run_adk_agent(
    research_agent,
    '''Pipeline: new_lead_onboarding
Lead: logistics/test-company/jane-doe
Lead wiki path: leads/logistics/test-company/jane-doe
Channel: email
Run ID: test-run-001
Context: {\"run_id\": \"test-run-001\", \"lead_id\": \"logistics/test-company/jane-doe\", \"lead_path\": \"leads/logistics/test-company/jane-doe\", \"lead_display\": \"Jane Doe — Test Company\", \"pipeline_name\": \"new_lead_onboarding\", \"channel\": \"email\", \"job_id\": \"test-job-001\", \"discovery_name\": \"Jane Doe\", \"discovery_email\": \"jane.doe@testcompany.com\", \"discovery_company_hint\": \"Test Company\", \"discovery_confidence\": 0.3}''',
    'logistics/test-company/jane-doe'
))
print(result)
"
```

Before running, create the test wiki structure:

```bash
mkdir -p wiki/leads/logistics/test-company/jane-doe/email/raw
echo '{"run_id":"test-run-001","lead_id":"logistics/test-company/jane-doe","lead_path":"leads/logistics/test-company/jane-doe","lead_display":"Jane Doe — Test Company","pipeline_name":"new_lead_onboarding","channel":"email","job_id":"test-job-001","discovery_name":"Jane Doe","discovery_email":"jane.doe@testcompany.com","discovery_company_hint":"Test Company","discovery_confidence":0.3,"discovery_context_summary":"No prior context found."}' \
  > wiki/leads/logistics/test-company/jane-doe/pipeline-context.json

cat > wiki/leads/logistics/test-company/jane-doe/email/raw/2026-04-15T10-30-00-inbound.md << 'EOF'
---
from: Jane Doe <jane.doe@testcompany.com>
subject: Interested in your logistics AI platform
date: 2026-04-15T10:30:00Z
---

Hi,

I'm Jane Doe, Head of Operations at Test Company (testcompany.com). We're a mid-size
logistics firm based in Munich, Germany, handling last-mile delivery for e-commerce clients.

I came across HappyRobot and am interested in learning more about your route optimization
and AI dispatch tools.

Best,
Jane Doe
Head of Operations, Test Company
EOF
```

### 9.2 What to verify in the output

After running, check:

1. **`research-notes.md` was written:**
   ```bash
   cat wiki/leads/logistics/test-company/jane-doe/research-notes.md
   ```
   Verify: YAML frontmatter present, all 6 sections present, `status` field set.

2. **Search call count is within limit:**
   The final response text will contain `search_queries_run: N` in the frontmatter.
   Verify N ≤ 5.

3. **Sentinel line present:**
   The final output string must contain:
   ```
   RESEARCH_COMPLETE: leads/logistics/test-company/jane-doe/research-notes.md
   ```
   If missing, the DAG executor cannot confirm node completion.

4. **`pipeline-context.json` updated:**
   ```bash
   python -c "import json; d=json.load(open('wiki/leads/logistics/test-company/jane-doe/pipeline-context.json')); print({k:v for k,v in d.items() if k.startswith('research_')})"
   ```
   Must contain `research_status`, `research_notes_path`, `research_confidence`, `research_date`.

5. **No `profile.md` written:**
   ```bash
   ls wiki/leads/logistics/test-company/jane-doe/profile.md 2>&1
   ```
   Must return `No such file or directory`.

---

## 10. Common Failure Modes

| Failure | Symptom | Fix |
|---|---|---|
| `GOOGLE_API_KEY` not set or invalid | `google_search` returns no grounding data; agent produces hallucinated content | Set `GOOGLE_API_KEY` (or `GEMINI_API_KEY`) in `.env`. Verify with `python -c "from google.adk.tools import google_search; print('ok')"` |
| Agent writes `profile.md` | Corrupt pipeline — `LeadClassificationAgent` writes a second `profile.md` over the first | Add hard path guard to `write_file` in `tools/file_tools.py` (see §3.2). Verify system prompt contains the write domain constraints. |
| No `RESEARCH_COMPLETE:` sentinel in output | DAG executor cannot confirm node completion; `pipeline-context.json` may not be updated | System prompt must explicitly end with `RESEARCH_COMPLETE:`. If the agent omits it, add it as a post-processing step in `execute_node` analogous to the `inject_run_id_into_draft` pattern. |
| Lead name too generic (e.g. "John Smith") | Search returns unrelated people | Prompt instructs: add company name + email domain to person query. If still ambiguous, set `research_confidence: low` and accept partial status. |
| Company name in non-English | Search returns foreign-language results that the model cannot summarize accurately | Prompt instructs: append "company" or "B2B" to query. If still poor, use `site:{email_domain}` as fallback. Consider upgrading to `gemini-2.5-pro` for this lead segment (see §8). |
| `research-notes.md` not found by `LeadClassificationAgent` | Classification step fails or treats lead as having no research | Verify `research_notes_path` in `pipeline-context.json` matches the actual file path written. Verify no path inconsistency (lead_id slug vs. actual directory name). |
| Agent overwrites existing `pipeline-context.json` entirely | Prior `discovery_*` fields lost; `LeadClassificationAgent` has no discovery context | System prompt must instruct: read, merge, re-write (not create from scratch). |
| Grounding metadata missing from ADK runner events | `event.grounding_metadata.grounding_chunks` is empty even though search succeeded | Known ADK issue (#1693, #3287). Do not parse grounding metadata from events — rely on the model's text output, which is correctly grounded. |
| `write_file` raises `PermissionError: seller/ paths` | Agent attempted to write to `seller/` | Correct the path. The agent should never write to seller/ — check the prompt write domain section. |

---

## 11. Cross-Reference

| Document | Relevant sections |
|---|---|
| `Orchestration/ARCHITECTURE-RESOLUTIONS.md` | §1.1 write domain table, §2.3 pipeline-context.json pattern |
| `prompts/agents/lead_discovery.md` | What LeadDiscoveryAgent writes to pipeline-context.json |
| `prompts/agents/lead_classification.md` | What LeadClassificationAgent reads from research-notes.md |
| `tools/file_tools.py` | `write_file` path restrictions, `safe_path` sandbox |
| `api/dag_executor.py` | `execute_node` user_message construction (lines 664–670), `run_adk_agent` |
| `api/pipeline_def.py` | `NEW_LEAD_ONBOARDING_PIPELINE` node ordering |
| `agents/research_agent.py` | Agent instantiation, tool list, prompt file path |
| Google ADK docs | [Built-in tools](https://google.github.io/adk-docs/tools/built-in-tools/), [Google Search Grounding](https://google.github.io/adk-docs/grounding/google_search_grounding/) |
