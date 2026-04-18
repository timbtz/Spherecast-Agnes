# Claude API Patterns Reference

Reference guide for using the Anthropic Python SDK in the Agnes pipeline.

All Agnes-specific patterns for tool use, structured extraction, prompt caching, batch processing, and vision.

---

## Model Selection

| Task | Model | Reason |
|---|---|---|
| Batch ingredient normalization (876 SKUs) | `claude-sonnet-4-6` | Best cost/quality; supports batches at 50% discount |
| Structured label extraction (high volume) | `claude-haiku-4-5` | ~3× cheaper, fast; sufficient for extraction |
| Complex substitution reasoning | `claude-sonnet-4-6` | Adequate for this domain |
| Sourcing proposal generation | `claude-sonnet-4-6` | Default workhorse |
| Vision: screenshot → supplement facts | `claude-haiku-4-5` | Vision-capable, cheapest |

**Never use LLM-generated CAS numbers without cross-validating against PubChem.**

---

## 1. Tool Use (Agentic Normalization Loop)

Claude decides which source to call next and continues until confident.

```python
import anthropic
import json

client = anthropic.Anthropic()

NORMALIZATION_TOOLS = [
    {
        "name": "lookup_pubchem",
        "description": "Search PubChem for chemical identity (CAS number, IUPAC name, molecular formula, synonyms). Use when the ingredient name is a chemical compound.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ingredient_name": {"type": "string", "description": "Name or synonym to search"}
            },
            "required": ["ingredient_name"]
        }
    },
    {
        "name": "lookup_dsld",
        "description": "Search NIH DSLD supplement label database for this ingredient. Returns standardized supplement names, UNII codes, and products containing it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ingredient_name": {"type": "string"}
            },
            "required": ["ingredient_name"]
        }
    },
    {
        "name": "fuzzy_match_canonical",
        "description": "Fuzzy match against already-normalized canonical ingredients in the database. Returns best match with similarity score.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ingredient_name": {"type": "string"},
                "threshold": {"type": "number", "description": "Minimum similarity score 0-1"}
            },
            "required": ["ingredient_name", "threshold"]
        }
    }
]

def normalize_ingredient_agentic(sku: str, name: str, max_iterations: int = 5) -> dict:
    """
    Use Claude to orchestrate normalization tool calls.
    Continues until confidence >= 0.9 or max_iterations reached.
    """
    messages = [{
        "role": "user",
        "content": f"""Normalize this supplement ingredient to a canonical identity.

SKU: {sku}
Extracted name: {name}

Use tools in this order:
1. fuzzy_match_canonical first (fastest — reuses existing work)
2. lookup_dsld for supplement-specific names
3. lookup_pubchem for chemical identity + CAS number

Stop when you have confidence >= 0.9. Output final result as JSON:
{{"canonical_name": "...", "cas": "...", "confidence": 0.0, "source": "pubchem|dsld|fuzzy", "notes": "..."}}"""
    }]

    for _ in range(max_iterations):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            tools=NORMALIZATION_TOOLS,
            messages=messages
        )

        if response.stop_reason == "end_turn":
            text = next((b.text for b in response.content if hasattr(b, "text")), "")
            try:
                # Extract JSON from response text
                start = text.find("{")
                end = text.rfind("}") + 1
                return json.loads(text[start:end])
            except (json.JSONDecodeError, ValueError):
                return {"canonical_name": name, "confidence": 0.0, "error": "parse_failed"}

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = _execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result)
                    })
            messages.append({"role": "user", "content": tool_results})

    return {"canonical_name": name, "confidence": 0.0, "error": "max_iterations"}

def _execute_tool(name: str, inputs: dict) -> dict:
    """Dispatch tool call to actual implementation."""
    if name == "lookup_pubchem":
        from enrichment.sources.pubchem import pubchem_lookup
        return pubchem_lookup(inputs["ingredient_name"])
    if name == "lookup_dsld":
        from enrichment.sources.dsld import dsld_search
        results = dsld_search(inputs["ingredient_name"])
        return {"hits": len(results), "first_result": results[0] if results else None}
    if name == "fuzzy_match_canonical":
        from enrichment.normalizers.fuzzy_matcher import fuzzy_match
        return fuzzy_match(inputs["ingredient_name"], inputs.get("threshold", 0.85))
    return {"error": f"unknown tool: {name}"}
```

---

## 2. Structured Extraction from Scraped Text

Parse unstructured scraped HTML into structured ingredient records.

```python
import json

EXTRACTION_SYSTEM = """You extract supplement ingredient data from raw text or HTML.
Return ONLY valid JSON — no markdown, no explanation.
If a field is not found, use null.
confidence: your certainty that the extraction is accurate (0.0–1.0)."""

def extract_supplement_facts_from_text(raw_text: str) -> dict:
    """Parse scraped page text into structured supplement facts."""
    response = client.messages.create(
        model="claude-haiku-4-5",   # cheap for high-volume extraction
        max_tokens=2048,
        system=EXTRACTION_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"""Extract supplement facts from this text:

{raw_text[:8000]}

Return JSON:
{{
  "product_name": "...",
  "serving_size": "...",
  "servings_per_container": null,
  "ingredients": [
    {{"name": "...", "amount": null, "unit": null, "daily_value_pct": null}}
  ],
  "other_ingredients": [],
  "confidence": 0.0
}}"""
        }]
    )
    try:
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()
        return json.loads(text)
    except (json.JSONDecodeError, IndexError):
        return {"confidence": 0.0, "error": "parse_failed"}

def extract_certifications_from_label_text(label_text: str) -> list[dict]:
    """Extract certification claims from product label text using Claude."""
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": f"""Extract certification claims from this label text:

{label_text}

Return JSON array:
[
  {{"certification": "NSF|USP|InformedSport|Organic|NonGMO|Kosher|Halal", "status": "confirmed|claimed|implied", "evidence_text": "..."}}
]

Return [] if no certifications found."""
        }]
    )
    try:
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()
        return json.loads(text)
    except Exception:
        return []
```

---

## 3. Prompt Caching

Cache the ingredient database system prompt when processing many ingredients in sequence. The cache stays warm for 5 minutes.

```python
def normalize_with_cached_db(ingredient_name: str, canonical_db_text: str) -> dict:
    """
    Normalize using a cached reference database.
    First call writes cache; subsequent calls read from cache (10× cheaper).
    """
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=[
            {"type": "text", "text": "You normalize supplement ingredient names."},
            {
                "type": "text",
                "text": f"Canonical ingredient database:\n{canonical_db_text}",
                "cache_control": {"type": "ephemeral"}   # cache for 5 minutes
            }
        ],
        messages=[{
            "role": "user",
            "content": f"Normalize this ingredient name: {ingredient_name}\nReturn JSON: {{canonical_name, confidence, notes}}"
        }]
    )

    # Log cache hit/miss
    usage = response.usage
    cache_hit = usage.cache_read_input_tokens > 0
    # cache_write: usage.cache_creation_input_tokens > 0

    try:
        text = response.content[0].text
        start, end = text.find("{"), text.rfind("}") + 1
        return {**json.loads(text[start:end]), "cache_hit": cache_hit}
    except Exception:
        return {"confidence": 0.0, "error": "parse_failed"}

def batch_normalize_with_cache(ingredients: list[str], canonical_db_text: str) -> list[dict]:
    """Process ingredients sequentially, reusing cached DB prompt."""
    results = []
    for name in ingredients:
        results.append(normalize_with_cached_db(name, canonical_db_text))
    return results
```

**Cost impact:** With caching + batches, ~95% cost reduction vs. naive requests on 876 ingredients.

---

## 4. Batch Processing (876 Ingredients)

Use the Message Batches API for processing all SKUs at once — 50% cost discount, async processing.

```python
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request
import time

def submit_normalization_batch(ingredients: list[dict], canonical_db_text: str) -> str:
    """
    Submit all 876 ingredients for batch normalization.
    Returns batch_id for polling. Results available within 24h (usually faster).
    """
    requests_list = []
    for i, ing in enumerate(ingredients):
        requests_list.append(Request(
            custom_id=f"ing_{i:06d}_{ing['sku']}",
            params=MessageCreateParamsNonStreaming(
                model="claude-sonnet-4-6",
                max_tokens=512,
                system=[
                    {"type": "text", "text": "Normalize supplement ingredient names. Return JSON only."},
                    {
                        "type": "text",
                        "text": f"Reference:\n{canonical_db_text}",
                        "cache_control": {"type": "ephemeral"}
                    }
                ],
                messages=[{
                    "role": "user",
                    "content": f"SKU: {ing['sku']}\nName: {ing['name']}\n\nReturn: {{canonical_name, cas, confidence, source, notes}}"
                }]
            )
        ))

    batch = client.messages.batches.create(requests=requests_list)
    print(f"Batch submitted: {batch.id} ({len(requests_list)} requests)")
    return batch.id

def wait_for_batch(batch_id: str, poll_seconds: int = 60) -> None:
    """Poll until batch completes."""
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        counts = batch.request_counts
        print(f"Status: {batch.processing_status} | done: {counts.succeeded + counts.errored} | pending: {counts.processing}")
        if batch.processing_status == "ended":
            return
        time.sleep(poll_seconds)

def collect_batch_results(batch_id: str) -> list[dict]:
    """Stream batch results without loading all into memory."""
    results = []
    for result in client.messages.batches.results(batch_id):
        sku = result.custom_id.split("_", 2)[2] if "_" in result.custom_id else result.custom_id
        if result.result.type == "succeeded":
            text = result.result.message.content[0].text
            try:
                start, end = text.find("{"), text.rfind("}") + 1
                data = json.loads(text[start:end])
                results.append({"sku": sku, "status": "ok", **data})
            except Exception:
                results.append({"sku": sku, "status": "parse_error", "raw": text})
        else:
            results.append({"sku": sku, "status": result.result.type})
    return results
```

---

## 5. Vision — Screenshot to Supplement Facts

When HTML parsing fails, pass a Playwright screenshot to Claude for extraction.

```python
import base64

def extract_from_screenshot(screenshot_bytes: bytes) -> dict:
    """
    Extract supplement facts from a product page screenshot.
    Use claude-haiku-4-5 for cost efficiency at scale.
    """
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64.standard_b64encode(screenshot_bytes).decode()
                    }
                },
                {
                    "type": "text",
                    "text": """Extract the Supplement Facts label from this image.
Return JSON only:
{
  "product_name": "...",
  "serving_size": "...",
  "ingredients": [{"name": "...", "amount": "...", "unit": "...", "daily_value_pct": null}],
  "confidence": 0.0
}
Set confidence 0.9 if table is clearly visible, 0.5 if partially visible, 0.2 if unclear."""
                }
            ]
        }]
    )
    try:
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()
        return json.loads(text)
    except Exception:
        return {"confidence": 0.0, "error": "vision_parse_failed"}
```

---

## 6. Proposal Generation

LLM-powered sourcing proposal with evidence trail.

```python
PROPOSAL_SYSTEM = """You are a CPG supply chain analyst generating sourcing consolidation proposals.
Every proposal must be backed by evidence. Clearly flag uncertainty.
Never invent CAS numbers, prices, or certification statuses — only state what the data shows."""

def generate_consolidation_proposal(cluster: dict) -> dict:
    """
    Generate a structured sourcing proposal for a consolidation opportunity.

    cluster = {
        "canonical_name": "Magnesium Stearate",
        "cas": "557-04-0",
        "companies": ["C1", "C11", "C30", ...],
        "company_count": 14,
        "bom_count": 12,
        "suppliers": [...],
        "supplier_commercial": [...],
        "compliance_profiles": [...]
    }
    """
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=PROPOSAL_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"""Generate a sourcing consolidation proposal for:

Ingredient: {cluster['canonical_name']} (CAS: {cluster.get('cas', 'unknown')})
Companies buying separately: {cluster['company_count']} ({', '.join(cluster['companies'][:8])}{'...' if len(cluster['companies']) > 8 else ''})
BOM appearances: {cluster['bom_count']}
Current suppliers: {json.dumps(cluster['suppliers'], indent=2)}
Commercial data: {json.dumps(cluster['supplier_commercial'], indent=2)}
Compliance profiles: {json.dumps(cluster['compliance_profiles'], indent=2)}

Return JSON:
{{
  "ingredient": "...",
  "current_state": "...",
  "recommended_supplier": "...",
  "consolidation_rationale": "...",
  "compliance_delta": "...",
  "estimated_savings_narrative": "...",
  "confidence_score": 0.0,
  "data_gaps": [...],
  "sources_cited": [...]
}}"""
        }]
    )
    try:
        text = response.content[0].text
        start, end = text.find("{"), text.rfind("}") + 1
        return json.loads(text[start:end])
    except Exception:
        return {"confidence_score": 0.0, "error": "proposal_parse_failed"}
```

---

## Cost Estimation for 876 Ingredients

```
Batch normalization (claude-sonnet-4-6, ~1500 tokens each):
  876 × 1500 tokens × $1.50/MTok (batch rate) = ~$1.97

Extraction from 300 screenshots (claude-haiku-4-5, ~800 tokens):
  300 × 800 tokens × $0.80/MTok (batch rate) = ~$0.19

20 proposal generations (claude-sonnet-4-6, ~3000 tokens):
  20 × 3000 tokens × $3.00/MTok = ~$0.18

Total estimated cost: < $3
```
