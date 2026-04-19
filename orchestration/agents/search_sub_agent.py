"""
SearchSubAgent: isolated google_search grounding agent.
Must be a standalone LlmAgent — google_search cannot be mixed with other tool types.
"""
import os

from dotenv import load_dotenv

load_dotenv()

_MODEL = "gemini-2.5-flash"

_SYSTEM = """You are a supply chain research assistant. Use google_search to find B2B
suppliers for the given ingredient and return a JSON array.

CRITICAL: Return ONLY a JSON array. The first character must be `[` and the last must be `]`.
Do not wrap it in markdown fences. Do not add any prose before or after.

Each element of the array MUST use exactly these field names (no synonyms, no variations):

  - supplier_name        : string  (e.g. "PureBulk, Inc.")
  - price_range_usd_per_kg : string  (price quoted in USD per KILOGRAM only.
                                      If the source quotes per-lb or in another currency,
                                      CONVERT to USD/kg before writing. Example: "$8-12 USD/kg".
                                      Use empty string "" if no numeric price is published.)
  - moq_range_kg          : string  (MOQ in KILOGRAMS, e.g. "25 kg" or "1-5 kg".
                                      Convert lb → kg if needed. Empty string if unknown.)
  - country               : string  (origin country, ISO short form preferred, e.g. "USA", "China", "India")
  - certifications        : array of strings  (e.g. ["USP", "GMP", "Kosher"]).
                                      MUST be a JSON array, never a single string.
  - website               : string  (product or supplier URL)
  - grade                 : string  (e.g. "supplement", "USP", "lab-reagent", "industrial".
                                      Use "lab-reagent" for Sigma/Aldrich/Thermo-Fisher style listings.)

If a field is unknown, use an empty string "" (or [] for certifications). Never use null.

Example of a valid response:
[
  {
    "supplier_name": "PureBulk, Inc.",
    "price_range_usd_per_kg": "$22-28 USD/kg",
    "moq_range_kg": "25 kg",
    "country": "USA",
    "certifications": ["NSF", "GMP"],
    "website": "https://purebulk.com/products/example",
    "grade": "supplement"
  }
]
"""


async def search(ingredient_name: str, query_hint: str = "") -> str:
    from google import genai
    from google.adk.agents import LlmAgent
    from google.adk.runners import InMemoryRunner
    from google.adk.tools import google_search
    from google.genai import types

    query = f"{ingredient_name} bulk supplier price MOQ certificate {query_hint}".strip()

    client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY", ""))
    agent = LlmAgent(
        name="search_sub_agent",
        model=_MODEL,
        instruction=_SYSTEM,
        tools=[google_search],
    )
    runner = InMemoryRunner(agent=agent, app_name="agnes")
    session = await runner.session_service.create_session(app_name="agnes", user_id="system")

    output_text = ""
    async for event in runner.run_async(
        user_id="system",
        session_id=session.id,
        new_message=types.Content(parts=[types.Part(text=query)], role="user"),
    ):
        if event.content and event.content.parts:
            output_text += event.content.parts[-1].text or ""

    return output_text.strip()
