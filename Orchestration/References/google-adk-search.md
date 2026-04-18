# Google ADK — Search Integration Reference

Reference guide for implementing `enrichment/sources/google_search.py` using Google Agent Development Kit.

---

## What Is Google ADK?

**Google Agent Development Kit** (`google-adk`) is an open-source Python framework for building AI agents. It provides `google_search` as a built-in tool that grounds Gemini model responses with real-time web results.

```bash
pip install google-adk
```

**Official repos:**
- https://github.com/google/adk-python
- https://adk.dev

---

## Critical Constraints

| Constraint | Detail |
|---|---|
| **Model compatibility** | `google_search` only works with Gemini 2.0+ models (`gemini-2.5-flash`, `gemini-2.0-flash`) |
| **Tool isolation** | `google_search` **cannot be combined with other tools** in the same agent instance |
| **Multi-agent workaround** | Put `google_search` in a dedicated sub-agent; orchestrate from a parent agent |

---

## Authentication

Create a `.env` file in the project root:

```bash
GOOGLE_API_KEY="your_key_from_aistudio.google.com"
GOOGLE_GENAI_USE_VERTEXAI=false
```

ADK loads `.env` automatically. Get a free API key at https://aistudio.google.com.

---

## Basic Search Agent

```python
import asyncio
from google.adk.agents import Agent
from google.adk.models import Gemini
from google.adk.runners import InMemoryRunner
from google.adk.tools import google_search

search_agent = Agent(
    name="ingredient_searcher",
    model=Gemini(model="gemini-2.5-flash"),
    instruction="""You are a supply chain research assistant.
Search for ingredient supplier info, product labels, and certifications.
Return factual results with source URLs.
Format: {"query": "...", "results": [{"title": "...", "url": "...", "snippet": "..."}]}""",
    tools=[google_search]
)

async def web_search(query: str) -> str:
    runner = InMemoryRunner(agent=search_agent)
    response = await runner.run_debug(query)
    return response.content.parts[0].text

# Usage
result = asyncio.run(web_search("PureBulk magnesium stearate price bulk MOQ"))
```

---

## Agnes-Specific Search Queries

```python
# Ingredient identity
f"{ingredient_name} CAS number supplement"
f"{ingredient_name} INCI name botanical synonym"

# Supplier pricing
f"PureBulk {ingredient_name} price bulk"
f"Alibaba {ingredient_name} bulk supplier MOQ kg"
f"{supplier_name} {ingredient_name} price bulk MOQ"

# BOM quantities (product label)
f"iHerb product {iherb_id} supplement facts"
f"{product_name} {manufacturer} supplement facts ingredients"

# Certification lookups
f"NSF certified {ingredient_name} supplier"
f"site:listings.nsf.org {supplier_name}"
f"USP verified {product_name}"
```

---

## Multi-Agent Pattern (for combining search with other tools)

```python
from google.adk.agents import Agent
from google.adk.models import Gemini
from google.adk.runners import InMemoryRunner
from google.adk.tools import google_search, FunctionTool

# Search agent (search ONLY — no other tools)
search_agent = Agent(
    name="searcher",
    model=Gemini(model="gemini-2.5-flash"),
    instruction="Search the web. Return results with source URLs.",
    tools=[google_search]
)

# Custom validation tool
def validate_cas_number(cas: str) -> dict:
    """Cross-validate a CAS number against PubChem."""
    import requests
    r = requests.get(f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{cas}/JSON")
    return {"valid": r.status_code == 200, "cas": cas}

# Main enrichment agent (orchestrates search + other tools)
enrichment_agent = Agent(
    name="enricher",
    model=Gemini(model="gemini-2.5-flash"),
    instruction="Enrich ingredient data using search and validation tools.",
    tools=[FunctionTool(func=validate_cas_number)],
    sub_agents=[search_agent]   # Search available as a sub-agent tool
)

runner = InMemoryRunner(agent=enrichment_agent)
```

---

## Extracting Source URLs from Response

```python
def extract_grounding_urls(response) -> list[dict]:
    """Extract title + URL from grounding metadata."""
    try:
        chunks = response.content.parts[0].grounding_metadata.groundingChunks
        return [
            {"title": c.web.title, "url": c.web.uri}
            for c in chunks if c.web
        ]
    except (AttributeError, TypeError):
        return []
```

---

## Rate Limiting & Retry

```python
import asyncio
from functools import wraps

def retry_on_rate_limit(max_retries=3, base_delay=2):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if "RESOURCE_EXHAUSTED" in str(e) and attempt < max_retries - 1:
                        await asyncio.sleep(base_delay * (2 ** attempt))
                    else:
                        raise
        return wrapper
    return decorator

@retry_on_rate_limit(max_retries=3, base_delay=2)
async def safe_search(runner, query: str):
    return await runner.run_debug(query)
```

**Free tier limit:** ~100 requests/day per project. Cache all results in `db_enriched.sqlite`.

---

## Batch Search with Delays

```python
async def batch_search(queries: list[str], delay: float = 1.5) -> list[dict]:
    runner = InMemoryRunner(agent=search_agent)
    results = []
    for query in queries:
        try:
            response = await safe_search(runner, query)
            results.append({"query": query, "success": True, "text": response.content.parts[0].text})
        except Exception as e:
            results.append({"query": query, "success": False, "error": str(e)})
        await asyncio.sleep(delay)  # politeness delay
    return results
```

---

## Known Issues (April 2026)

| Issue | Workaround |
|---|---|
| `grounding_metadata` not always populated in runner events | Parse source URLs from the LLM's text response as fallback |
| `google_search` incompatible with older Gemini models | Always specify `gemini-2.5-flash` or `gemini-2.0-flash` |
| Cannot combine `google_search` with custom tools | Use multi-agent pattern — search agent as sub-agent |
