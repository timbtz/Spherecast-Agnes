"""
4-state compliance reasoner tool for Agnes DAG.
Reads canonical_id from upstream node output (find-alternatives OR find-substitutes).
Builds ComplianceInput from DB, runs ComplianceReasoner, applies CONFIDENCE_FLOOR.
Returns structured dict for downstream nodes and condition guards.
"""
import sqlite3

from orchestration.api.agnes_context import AgnesContext
from reasoning.compliance_reasoner import ComplianceReasoner, ComplianceInput
from reasoning.refusal_engine import CONFIDENCE_FLOOR

_DEFAULT_JURISDICTIONS = ["US-FDA", "EU", "CA", "JP"]

_GRADE_TO_USE_CLASS = {
    "supplement": "supplement",
    "food": "food",
    "excipient": "supplement",   # excipients are used in supplement products
    "sweetener": "food",
    "flavor": "food",
    "unknown": "supplement",     # pessimistic default
}


def run(ctx: AgnesContext) -> dict:
    # 1. Resolve canonical_id from upstream nodes
    canonical_id = (
        ctx.get("find-alternatives", {}).get("canonical_id")
        or ctx.get("find-substitutes", {}).get("canonical_id")
    )
    if not canonical_id:
        return {"qualified": False, "outcome": "no_canonical_id", "above_floor": False}

    conn = sqlite3.connect(str(ctx.enriched_db_path))
    conn.row_factory = sqlite3.Row

    # 2. Fetch ingredient metadata
    ic_row = conn.execute(
        "SELECT Name, Grade_Flag, Function FROM Ingredient_Canonical WHERE Id = ?",
        (canonical_id,),
    ).fetchone()
    if not ic_row:
        conn.close()
        return {"qualified": False, "outcome": "canonical_not_found", "above_floor": False}

    ingredient_name = ic_row["Name"]
    grade_flag = (ic_row["Grade_Flag"] or "unknown").lower()
    use_class = _GRADE_TO_USE_CLASS.get(grade_flag, "supplement")

    # 3. Build incumbent_precedents: which jurisdictions have compliance evidence
    #    for products using this ingredient?
    compliance_rows = conn.execute(
        """
        SELECT DISTINCT pc.Certification
        FROM Product_Compliance pc
        JOIN SKU_To_Canonical stc ON stc.ProductId = pc.ProductId
        WHERE stc.CanonicalId = ?
          AND pc.Status IN ('confirmed', 'claimed', 'implied')
        """,
        (canonical_id,),
    ).fetchall()
    conn.close()

    # Infer incumbent_precedents from cert coverage.
    # NSF/USP certs are primarily US; EU/CA/JP precedent unknown from our cert data.
    has_certs = len(compliance_rows) > 0
    incumbent_precedents = {
        "US-FDA": has_certs,    # certs present → incumbent passes US-FDA
        "EU": None,             # unknown — insufficient EU-specific cert data
        "CA": None,             # unknown
        "JP": None,             # unknown
    }

    # 4. Run compliance reasoner
    cr = ComplianceReasoner()
    inp = ComplianceInput(
        candidate_name=ingredient_name,
        use_class=use_class,
        jurisdictions=_DEFAULT_JURISDICTIONS,
        incumbent_precedents=incumbent_precedents,
    )
    comp_result = cr(inp)

    # 5. Check confidence floor
    comp_confidence = comp_result.confidence or 0.0
    above_floor = comp_confidence >= CONFIDENCE_FLOOR
    outcome = (comp_result.result or {}).get("outcome", "unknown")

    # 6. Determine qualified flag (for condition guards)
    # "refuse" means not viable; others are viable with caveats
    viable = outcome != "refuse" and above_floor

    return {
        "outcome": outcome,
        "compound_confidence": comp_confidence,
        "above_floor": above_floor,
        "qualified": viable,
        "ingredient_name": ingredient_name,
        "use_class": use_class,
        "per_jurisdiction": (comp_result.result or {}).get("per_jurisdiction", []),
        "reason": (comp_result.result or {}).get("reason", ""),
        "refusal": comp_result.refusal,
        "canonical_id": canonical_id,
    }
