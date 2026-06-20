from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PipelineNode:
    id: str
    agent_class: Optional[str] = None   # LLM agent class name (from agent_registry)
    tool_class: Optional[str] = None    # Deterministic tool class name (from tools/)
    depends_on: list[str] = field(default_factory=list)
    when: Optional[str] = None          # Named condition guard (from conditions.py)


@dataclass
class Pipeline:
    name: str
    trigger: str                        # manual|schedule|data_update|chat
    nodes: list[PipelineNode] = field(default_factory=list)
