from typing import Callable

# Lazy imports: string name → async callable (ctx: AgnesContext) → dict
_AGENT_REGISTRY: dict[str, str] = {
    "ReactiveAgent":     "orchestration.agents.reactive_agent:run",
    "ProactiveAgent":    "orchestration.agents.proactive_agent:run",
    "ResearchAgent":     "orchestration.agents.research_agent:run",
    "ProposalWriter":    "orchestration.agents.proposal_writer:run",
    "PriceFetchAgent":            "orchestration.agents.price_fetch_agent:run",
    "PriceAlertWriter":           "orchestration.agents.price_alert_writer:run",
    "RegulatoryResearchAgent":    "orchestration.agents.regulatory_research_agent:run",
    "RegulatoryDriftAgent":       "orchestration.agents.regulatory_drift_agent:run",
}

_TOOL_REGISTRY: dict[str, str] = {
    "SupplierAlternativesTool":   "orchestration.tools.supplier_alternatives:run",
    "ComplianceGateTool":         "orchestration.tools.compliance_gate:run",
    "SubstitutionWalkerTool":     "orchestration.tools.substitution_walker:run",
    "BomImpactTool":              "orchestration.tools.bom_impact:run",
    "PriceBenchmarkTool":         "orchestration.tools.price_benchmark:run",
    "OpportunityRankerTool":      "orchestration.tools.opportunity_ranker:run",
    "RfqFormatterTool":           "orchestration.tools.rfq_formatter:run",
    "ComplianceReasonerTool":     "orchestration.tools.compliance_reasoner_tool:run",
    "PriceStalenesCheckerTool":   "orchestration.tools.price_staleness_checker:run",
    "RegulatoryDriftTool":        "orchestration.tools.regulatory_drift_tool:run",
    "NoDataExplainerTool":        "orchestration.tools.no_data_explainer:run",
    "NoOpportunityExplainerTool": "orchestration.tools.no_opportunity_explainer:run",
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
