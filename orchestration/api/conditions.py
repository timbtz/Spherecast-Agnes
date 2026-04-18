from typing import Callable
from orchestration.api.agnes_context import AgnesContext

ConditionFn = Callable[[AgnesContext], bool]


def has_alternatives(ctx: AgnesContext) -> bool:
    out = ctx.get("find-alternatives", {})
    return bool(out.get("alternatives"))


def above_score_threshold(ctx: AgnesContext) -> bool:
    out = ctx.get("scan-opportunities", {})
    opportunities = out.get("opportunities", [])
    return len(opportunities) > 0


def has_substitutes(ctx: AgnesContext) -> bool:
    out = ctx.get("find-substitutes", {})
    return bool(out.get("substitutes"))


def has_price_deviations(ctx: AgnesContext) -> bool:
    out = ctx.get("benchmark-prices", {})
    return bool(out.get("outliers"))


def compliance_feasible(ctx: AgnesContext) -> bool:
    out = ctx.get("gate-qualify", {})
    qualified = out.get("qualified", [])
    return len(qualified) > 0


def has_research_results(ctx: AgnesContext) -> bool:
    out = ctx.get("web-research", {})
    return bool(out.get("discovered_suppliers"))


def compliance_reasoner_feasible(ctx: AgnesContext) -> bool:
    """True when ComplianceReasonerTool returned a viable (non-refused, above-floor) result."""
    result = ctx.get("gate-compliance", {})
    return bool(result.get("qualified")) and bool(result.get("above_floor"))


def has_stale_prices(ctx: AgnesContext) -> bool:
    out = ctx.get("find-stale", {})
    return out.get("count", 0) > 0


def has_price_alerts(ctx: AgnesContext) -> bool:
    out = ctx.get("fetch-prices", {})
    return out.get("count", 0) > 0


def has_regulatory_drift(ctx: AgnesContext) -> bool:
    out = ctx.get("scan-drift", {})
    return bool(out.get("drift_alerts"))


_REGISTRY: dict[str, ConditionFn] = {
    "has_alternatives": has_alternatives,
    "above_score_threshold": above_score_threshold,
    "has_substitutes": has_substitutes,
    "has_price_deviations": has_price_deviations,
    "compliance_feasible": compliance_feasible,
    "has_research_results": has_research_results,
    "compliance_reasoner_feasible": compliance_reasoner_feasible,
    "has_stale_prices": has_stale_prices,
    "has_price_alerts": has_price_alerts,
    "has_regulatory_drift": has_regulatory_drift,
}


def evaluate(name: str, ctx: AgnesContext) -> bool:
    fn = _REGISTRY.get(name)
    if fn is None:
        raise ValueError(f"Unknown condition: {name!r}")
    return fn(ctx)
