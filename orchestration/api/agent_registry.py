from typing import Callable

# Lazy imports: string name → async callable (ctx: AgnesContext) → dict
_AGENT_REGISTRY: dict[str, str] = {
    "ReactiveAgent":     "orchestration.agents.reactive_agent:run",
    "ProactiveAgent":    "orchestration.agents.proactive_agent:run",
    "ResearchAgent":     "orchestration.agents.research_agent:run",
    "ProposalWriter":    "orchestration.agents.proposal_writer:run",
}

_TOOL_REGISTRY: dict[str, str] = {
    "SupplierAlternativesTool":  "orchestration.tools.supplier_alternatives:run",
    "ComplianceGateTool":        "orchestration.tools.compliance_gate:run",
    "SubstitutionWalkerTool":    "orchestration.tools.substitution_walker:run",
    "BomImpactTool":             "orchestration.tools.bom_impact:run",
    "PriceBenchmarkTool":        "orchestration.tools.price_benchmark:run",
    "OpportunityRankerTool":     "orchestration.tools.opportunity_ranker:run",
    "RfqFormatterTool":          "orchestration.tools.rfq_formatter:run",
}


def _import(dotted: str) -> Callable:
    module_path, attr = dotted.rsplit(":", 1)
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, attr)


def get_agent(name: str) -> Callable:
    dotted = _AGENT_REGISTRY.get(name)
    if not dotted:
        raise KeyError(f"Unknown agent: {name!r}")
    return _import(dotted)


def get_tool(name: str) -> Callable:
    dotted = _TOOL_REGISTRY.get(name)
    if not dotted:
        raise KeyError(f"Unknown tool: {name!r}")
    return _import(dotted)
