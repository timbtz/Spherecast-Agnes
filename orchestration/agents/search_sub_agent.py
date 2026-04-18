"""
SearchSubAgent: isolated google_search grounding agent.
Must be a standalone LlmAgent — google_search cannot be mixed with other tool types.
"""
import os

from dotenv import load_dotenv

load_dotenv()

_MODEL = "gemini-2.5-flash"

_SYSTEM = """You are a supply chain research assistant. Search for supplier information
for the given ingredient. Extract: supplier name, price range, MOQ, country, certifications,
contact/website. Return structured JSON list of discovered suppliers."""


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
