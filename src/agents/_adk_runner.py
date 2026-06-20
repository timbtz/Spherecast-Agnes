"""Shared per-node InMemoryRunner helper for ADK agents."""
import os

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types


async def run_adk_agent(agent: LlmAgent, payload: str, run_id: str) -> str:
    """Run one ADK LlmAgent as a single DAG node. Returns final text output."""
    if not os.environ.get("GOOGLE_API_KEY"):
        return ""
    runner = InMemoryRunner(agent=agent, app_name=agent.name)
    session = await runner.session_service.create_session(app_name=agent.name, user_id=run_id)
    final = ""
    async for event in runner.run_async(
        user_id=run_id,
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=payload)]),
    ):
        if event.is_final_response() and event.content:
            for part in event.content.parts:
                if part.text:
                    final += part.text
    return final.strip()
