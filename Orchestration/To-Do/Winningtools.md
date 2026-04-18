# Features that can win this hackathon (without breaking what works)

Judging emphasis, ranked by the brief:

1. Practical usefulness / business relevance
2. Quality of reasoning and **evidence trails**
3. **Trustworthiness and hallucination control**
4. Ability to **source and operationalize missing external information**
5. Soundness of substitution logic and compliance inference
6. Quality and defensibility of the sourcing proposal
7. Creativity in how the system **scales and improves over time**
8. UI polish **explicitly not a priority** — do not spend a minute on it past functional

So the right strategy is: **over-invest in reasoning, evidence, and creativity; under-invest in pixels**.

---

## Tier S — "Judge moments" that likely win the room

These are features where a judge watches 30 seconds and writes you down as the team to beat. Build these first if you have any time at all.

### S1. Multimodal label/SDS ingestion (image + PDF → compliance constraints)

The brief literally calls out "label images, packaging text, supplier websites" as fair game. Almost no team will do this well.

- Upload a product label JPG → vision model extracts "Contains: soy, milk. Certified vegan. Kosher OU-D."
- Upload a Safety Data Sheet PDF → extract CAS, purity, allergens, shelf life, country of origin.
- Feeds straight into `reasoning/compliance_reasoner.py` as a new structured-evidence source with `source_type='label_ocr'` and confidence < API sources so the reasoner weights it appropriately.
- Demo moment: during the mag stearate anchor case, drop a vegan-certified tablet label on the chat box. System flags that any bovine-source mag stearate is refused. Proposes the plant-source alternative. Every claim cites the OCR snippet with bounding-box.

Effort: ~3–4 hours (use GPT-4o vision or Claude vision via API, no training needed; pdfplumber + image crop for layout). High wow-factor.

### S2. Red-team worker (playbook §8 item you haven't built)

Every proposal gets adversarially attacked by a second agent before it's shown:

- "Can you break this substitution with a plausible counterexample?"
- "What compliance constraint does this miss?"
- "What if the buyer is in the EU, not US?"

If the red-team finds a hole, the proposal is either patched, downgraded in confidence, or replaced with a refusal. Show the red-team transcript in the evidence panel — judges love seeing the system argue with itself.

Effort: ~2 hours. It's another ADK agent with a prompt that ingests the proposal + evidence trail. Add a `red_team` node to the end of every pipeline DAG.

### S3. Citation ledger — every claim links to a source row

Add a `Claim_Citation` table: `(claim_id, proposal_id, claim_text, source_type, source_url, source_snippet, confidence, retrieved_at)`. Every sentence in a proposal writes one row.

- UI shows each proposal claim as clickable → opens the source row with highlighted snippet.
- If a claim has **zero** citations, it's auto-labeled "unsubstantiated" and hidden from the main view.
- This is directly the "evidence trails" criterion. Untouchable defense when a judge asks "how do you know?"

Effort: ~2 hours. Schema is one table; wire `proposal_writer.py` to emit citations alongside text.

### S4. Refusal panel as a first-class screen

Your `refusal_engine.py` already exists — most teams won't have anything like it. Make refusals demo-visible:

- Seed the demo with ingredients that *should* refuse (e.g., a BOM that asks for a kosher substitute when no kosher supplier is indexed).
- Refusal card shows: what was asked, why it refused, what evidence it lacks, and what would unblock it ("need halal cert from supplier X").
- Judges will remember this. It's the opposite of the usual hackathon "AI confidently wrong" pattern.

Effort: ~1 hour. Endpoint + JSON; the engine exists.

---

## Tier A — Reasoning quality features (direct judging criteria 2 & 5)

### A1. Role vector (not role label)

Today `role_inferrer.py` outputs one role per ingredient. Upgrade to a **role distribution**: e.g., stearic acid = {lubricant: 0.8, emulsifier: 0.2}. Substitutions only valid when distributions overlap by threshold. Kills bad substitutions like lubricant↔emulsifier masquerading as "same thing."

### A2. Grade lattice

Build a partial order over grades: USP > food-grade > industrial. A USP ingredient can substitute down, never up. Encoded as a small graph, gated in `substitution_graph.py`.

### A3. Dual-model compliance gate

Run `check_compliance` through two models (e.g., GPT-4 + Claude, or GPT-4 + a deterministic rule engine). Disagreement ⇒ escalate to refusal or human review. This is the single cleanest "hallucination control" story.

### A4. Quantitative equivalence check

If the substitute has different density, active concentration, or moisture content, auto-recompute the %w/w in the BOM and flag if it breaks spec tolerance. Your `quantity_enricher.py` has the hooks — just surface the math in the proposal.

### A5. BOM-context constraints

Same ingredient, different products → different constraints. A BOM for a gummy has chewability constraints a tablet BOM doesn't. Encode BOM context as a constraint set the substitution search must satisfy. Show the judge the same ingredient being accepted in product X and refused in product Y.

---

## Tier B — Evidence sourcing (criterion 4)

### B1. Certification registry scraper

One more source module in `enrichment/sources/`:

- USDA Organic Integrity Database lookup
- Non-GMO Project Verified lookup
- Kosher (OU / OK / Star-K) public cert listings
- Halal (IFANCA / JAKIM) cert lookups

Per cert, cache last-checked date and expiry. Hook into the compliance reasoner.

### B2. Wayback Machine fallback

When a supplier page 404s, retry against `web.archive.org`. One `try: ... except: ...` branch in the scraper path. Makes your demo feel robust to bitrot.

### B3. FDA / EU regulatory reference pinner

Instead of a vague "GRAS substance," link each claim to the exact CFR section (e.g., 21 CFR 184.1724 for sodium stearate) or EU E-number registry. One-time seed of the mapping table. Huge trust signal.

### B4. Generalized supplier landing-page reader

You already have a Playwright stack for Molport. Generalize: given any supplier URL for a CAS, extract (price, MOQ, lead time, cert claims) with a prompt-engineered extractor. Widens your supplier universe past Molport for free.

### B5. Demand aggregation across fake multi-tenant scenario

Your `bom_impact.py` is partial. Seed 3 fictitious CPG companies sharing Agnes, show cross-tenant consolidation ("if all three buy mag stearate together, MOQ tier drops and price per kg falls 12%"). Exactly the brief's thesis, concretely demoed.

---

## Tier C — Proposal defensibility (criterion 6)

### C1. Pareto tradeoff card per proposal

Don't rank by $ alone. Show every proposal on 4–5 axes:

- price Δ per kg
- lead time Δ
- compliance risk (0–1)
- supplier concentration risk (share of buyer's spend on this supplier)
- origin geo-risk (tariff / climate / political flag)

Highlight Pareto-dominant choices. Judges can eyeball whether your logic is principled.

### C2. Counterfactual / "what if this supplier drops"

You already have `supplier_fallout` pipeline. Surface the 2nd and 3rd choice in every proposal card with a confidence score on the fallback. The buyer should never see a single-supplier recommendation without a named backup.

### C3. "Defend this proposal" button

Buyer clicks → triggers the red-team worker live. Transcript appears in the ledger. The original proposal either stands, gets patched, or gets refused. A genuinely interactive moment in the demo.

### C4. Accept/reject → case memory (`record_case`)

Every accepted or rejected proposal is written to a `Case_Memory` table with embedding. Future proposals retrieve nearest neighbors and cite them: "Similar decision X was accepted on 2026-03-02 for Company Y." This is the "scales and improves over time" criterion made concrete — no retraining needed, just RAG over decisions.

### C5. Flag-for-reeval daemon

Once you have `record_case`, add a cron-style worker that auto-requeues any cached snapshot older than N days. Shows the system keeps itself fresh. Slideware is fine if you don't have time to wire the scheduler — just `flag_for_reeval` as a function and a count on the dashboard.

---

## Tier D — Practical / operational (criterion 1)

### D1. RFQ autodraft (`send_rfq` stub + `draft_rfq` real)

Your `rfq_formatter.py` drafts the body. Add a one-click "generate vendor email + spec sheet PDF" action. Attach the spec sheet (CAS, purity, certs required, MOQ). Even if `send_rfq` is a no-op, showing the vendor-ready RFQ draft is a huge "this is actually usable" moment.

### D2. CSV → BOM uploader

Let a buyer drop a CSV of components and get back an enriched BOM with substitution candidates in < 60s. Converts the system from "demo on our seed data" to "works on yours."

### D3. Savings dashboard

Aggregate $-savings across accepted proposals. Tracks "realized vs. projected" when follow-up data arrives. One number the exec would care about. Even if it's fake-populated, it tells the business story.

### D4. Change-order JSON export

Proposal → signed JSON (ID, timestamp, evidence hashes). Pitch: "this drops into SAP/Oracle with no custom glue." You're not building the ERP integration; you're exporting the contract.

---

## Tier E — Creativity / scalability story (criterion 7)

### E1. Similarity-based precedent retrieval (builds on C4)

Embedding index over past cases. Every new proposal shows "3 most similar past decisions" with accept/reject outcome.

### E2. A/B proposal mode

Generate two proposals with different objective functions (price-first vs. consolidation-first vs. resilience-first). Let the buyer pick. You're not guessing the weight, you're surfacing the frontier.

### E3. Supplier-health scoring

Per supplier: on-time-delivery rate (seed synthetic), cert expiry dates, price volatility (std over cached Molport snapshots), geographic concentration. Feeds into proposal ranking.

### E4. Buyer preference learning

Track accept/reject on proposals, re-fit the ranker weights. Not full RLHF — just a logistic regression over 5 axes. Shows the system learning from its users.

### E5. Calibrator worker (playbook §8 — deferred, but mention)

Periodically back-tests past proposals: "of the 47 proposals we recommended in March, 42 were accepted. The 5 rejected were all on lead-time grounds." Slideware fine, but the narrative is gold.

---

## Tier F — Hallucination traps to plant in the demo

Seed the demo with a few adversarial cases that naive systems get wrong. When Agnes catches them, it looks dramatically better than the competition.

- **Trap 1:** Ingredient name matches across products, but one product is vegan-certified. System must refuse bovine substitute.
- **Trap 2:** Cheaper Molport supplier is listed but purity is 95% vs. 99% required by a pharma BOM. System must flag grade mismatch.
- **Trap 3:** Substitute ingredient is E-numbered in the EU as allergen-flagged but allowed in US. System should output two different recommendations by geography.
- **Trap 4:** Supplier is listed as in-stock but `last_update_date` is > 180 days. System downgrades confidence and suggests a live-verified alternative.

Each trap is ~30 minutes of fixture-seeding and gives you 4 separate wow moments in the demo.

---

## What to **not** build

- Auth / multi-user / role-based access — no points.
- A prettier UI — brief says UI polish is not judged.
- Production deploy / Dockerfile polish — not judged; running locally on your laptop is fine.
- Write-path to any real supplier system — risk of a demo crash; keep `send_rfq` as a formatter.
- Any novel model training — no time, high risk. Stick to prompted LLMs + retrieval.

---

## Recommended build order (if it's just tonight + tomorrow morning)

1. **Citation ledger (S3)** — 2h. Everything downstream cites it.
2. **Red-team worker (S2)** — 2h. Connects straight into existing pipelines.
3. **Multimodal label/SDS (S1)** — 3h. Biggest judge moment. Needs vision model API key.
4. **Refusal panel (S4)** — 1h. Makes your existing `refusal_engine.py` demo-visible.
5. **Pareto tradeoff card (C1)** — 1h. Styling-free; just the data model + JSON.
6. **Counterfactual fallback (C2)** — 0.5h. `supplier_fallout` pipeline exists.
7. **Certification registry scraper (B1) — at least Kosher + Organic** — 2h.
8. **RFQ autodraft with PDF spec sheet (D1)** — 1h.
9. **Demo traps seeded (F)** — 0.5h of fixture writing.

Everything else is slideware — say "we have the hooks, here's how it scales" and point at the playbook §7/§8 table in `where-we-are.md`.

---

## One-line pitch for the deck

"Agnes is a reasoning-first sourcing agent: every substitute it proposes is challenged by an adversarial red-team, every compliance claim is grounded in a citeable source, and every refusal is as explainable as every recommendation."

That sentence maps directly to judging criteria 2, 3, 5, 6.
