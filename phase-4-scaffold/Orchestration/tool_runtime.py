"""Thin runtime wrapper that lets a planner (Gemini-ADK or Claude) call
reasoning tools by name with structured args and get uniform ToolResult
back.

This is intentionally NOT a full ADK integration — Tim's enrichment side
already wires ADK. This module provides:

  * a simple registry (name -> Tool instance)
  * `invoke(tool_name, **kwargs)` returning ToolResult
  * a `to_planner_schema()` helper that emits JSON schemas the planner
    can use as its tool list

When Tim is ready to expose the reasoning tools to the ADK runner, he
imports this registry and converts via `to_planner_schema()`. Until
then, the planner.py here uses the registry directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from reasoning.base import Tool, ToolResult


@dataclass
class ToolSpec:
    name: str
    description: str
    args_schema: Dict[str, Any]
    instance: Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, name: str, description: str, args_schema: Dict[str, Any], instance: Tool) -> None:
        if name in self._tools:
            raise ValueError(f"tool already registered: {name}")
        self._tools[name] = ToolSpec(name, description, args_schema, instance)

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    def names(self) -> List[str]:
        return sorted(self._tools.keys())

    def invoke(self, name: str, **kwargs) -> ToolResult:
        spec = self.get(name)
        if spec is None:
            return ToolResult(result=None, confidence=0.0, refusal=f"unknown_tool:{name}")
        return spec.instance(**kwargs)

    def to_planner_schema(self) -> List[Dict[str, Any]]:
        """JSON-schema-ish list the ADK / Anthropic tool API can ingest."""
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": {
                    "type": "object",
                    "properties": spec.args_schema,
                    "required": [k for k, v in spec.args_schema.items() if v.get("required", False)],
                },
            }
            for spec in self._tools.values()
        ]


def build_default_registry(conn=None) -> ToolRegistry:
    """Convenience constructor wiring every Phase 4 reasoning tool."""
    from reasoning.role_inferrer import RoleInferrer
    from reasoning.gate_engine import GateEngine
    from reasoning.compliance_reasoner import ComplianceReasoner
    from reasoning.refusal_engine import RefusalEngine
    from reasoning.supplier_scorer import SupplierScorer

    reg = ToolRegistry()
    reg.register(
        "infer_role",
        "Infer the functional role of an ingredient in a recipe slot.",
        {
            "ingredient_name": {"type": "string", "required": True},
            "recipe_slot_hint": {"type": "string"},
        },
        RoleInferrer(),
    )
    reg.register(
        "run_substitution_gates",
        "Six-gate substitution check between an incumbent and a candidate SKU.",
        {
            "incumbent": {"type": "object", "required": True},
            "candidate": {"type": "object", "required": True},
            "jurisdiction": {"type": "string", "required": True},
        },
        GateEngine(),
    )
    reg.register(
        "evaluate_compliance",
        "Dual-rule compliance reasoner across one or more jurisdictions.",
        {"inp": {"type": "object", "required": True}},
        ComplianceReasoner(),
    )
    reg.register(
        "decide_refusal",
        "Aggregate gate + compliance into recommend / refuse / human-review.",
        {"ctx": {"type": "object", "required": True}},
        RefusalEngine(conn=conn),
    )
    reg.register(
        "score_suppliers",
        "Score suppliers within an opportunity (Q,C,L,R weighted).",
        {
            "opportunity_id": {"type": "integer", "required": True},
            "suppliers": {"type": "array", "required": True},
        },
        SupplierScorer(conn=conn),
    )
    return reg
