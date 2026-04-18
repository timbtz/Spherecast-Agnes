"""Tool contract shared by every Phase 4 reasoning module.

Design rules (from the integration plan):
  * Every tool returns a ToolResult — never a raw dict.
  * Confidence is a float in [0, 1]; missing values are NOT 1.0, they are None.
  * Evidence ids reference rows in Evidence_Ledger (sqlite). Tools never
    invent facts; if they have no evidence, the claim must be flagged.
  * Refusals are first-class. A refusal carries a reason string, not just
    None, so the UI can explain *why* a decision was withheld.
  * compound_confidence is multiplicative — mirrors the proposal's "all
    gates must pass" semantics. One soft link drops the whole chain.
"""

from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional


@dataclass
class ToolResult:
    """Uniform return shape for every reasoning tool."""

    result: Any
    confidence: Optional[float]
    evidence_ids: List[int] = field(default_factory=list)
    refusal: Optional[str] = None
    tool_name: str = ""
    latency_ms: int = 0

    @property
    def passed(self) -> bool:
        """True iff the tool produced a usable result and did not refuse."""
        return self.refusal is None and self.result is not None

    def with_meta(self, tool_name: str, latency_ms: int) -> "ToolResult":
        self.tool_name = tool_name
        self.latency_ms = latency_ms
        return self


def compound_confidence(values: Iterable[Optional[float]]) -> float:
    """Multiplicative confidence aggregation.

    None values are treated as 0.5 (unknown -> half-trust) so an unenriched
    field doesn't silently dominate the chain. Empty input returns 0.0
    rather than 1.0 — we will not pretend confidence we don't have.
    """
    vs = [0.5 if v is None else max(0.0, min(1.0, float(v))) for v in values]
    if not vs:
        return 0.0
    out = 1.0
    for v in vs:
        out *= v
    return out


class Tool(abc.ABC):
    """Abstract base. Subclasses implement `_run` and return a ToolResult.

    The wrapper handles timing + tool-name stamping so individual tools
    don't have to. If `_run` raises, the wrapper converts it to a refusal
    with the exception type — we never propagate raw exceptions through
    the reasoning chain (they collapse multi-tool plans).
    """

    name: str = "tool"

    def __call__(self, *args, **kwargs) -> ToolResult:
        t0 = time.monotonic()
        try:
            res = self._run(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 — we want a refusal, not a crash
            res = ToolResult(
                result=None,
                confidence=0.0,
                refusal=f"tool_exception:{type(e).__name__}:{e}",
            )
        dt_ms = int((time.monotonic() - t0) * 1000)
        return res.with_meta(self.name, dt_ms)

    @abc.abstractmethod
    def _run(self, *args, **kwargs) -> ToolResult:
        ...
