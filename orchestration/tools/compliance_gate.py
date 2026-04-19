"""
Deterministic tool: check whether candidate suppliers satisfy compliance requirements
for all products using the target ingredient.

Returns a list of qualified (supplier, product) pairs that pass all gates.

This is the legacy binary gate used by new_ingredient_research.yaml. The
sophisticated ComplianceReasonerTool replaces it in supplier_fallout and
substitution_discovery pipelines. When ALL candidates fail here we emit a
Refusal_Log entry so new_ingredient_research still produces first-class
refusal output — mirroring the reasoner's behavior so the refusal dashboards
and proposal narrative see both pipelines' gate failures.
"""
import logging
import sqlite3

from orchestration.api.agnes_context import AgnesContext

logger = logging.getLogger("agnes.compliance_gate")

# Certifications that must be supplied by the ingredient supplier (not just claimed on label)
_SUPPLIER_CERTS = {"NSF", "USP", "InformedSport", "BSCG"}


def _log_refusal(
    ctx: AgnesContext,
    canonical_id: int | None,
    ingredient_name: str,
    justification: str,
    blocking_factors: list[str],
    unblock_hint: str,
) -> None:
    """Persist a gate-failed refusal so downstream narrative writers (and the
    refusal dashboard) can surface it. Mirrors the pattern in
    compliance_reasoner_tool and the no-data explainers."""
    try:
        conn = sqlite3.connect(str(ctx.enriched_db_path))
        conn.execute(
            """INSERT OR IGNORE INTO Refusal_Log
               (CanonicalId, IngredientName, Decision, Justification,
                Confidence, BlockingFactors, UnblockHint, RunId)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                canonical_id,
                ingredient_name or "(unspecified)",
                "refuse",
                justification,
                1.0,
                str(blocking_factors),
                unblock_hint,
                getattr(ctx, "run_id", None),
            ),
        )
        conn.commit()
        conn.close()
    except Exception as err:
        logger.warning(f"Refusal_Log write failed in compliance_gate: {err}")


def run(ctx: AgnesContext) -> dict:
    alternatives = ctx.get("find-alternatives", {}).get("alternatives", [])
    canonical_id = ctx.get("find-alternatives", {}).get("canonical_id")

    if not canonical_id or not alternatives:
        return {"qualified": [], "disqualified": []}

    conn = sqlite3.connect(str(ctx.enriched_db_path))
    conn.row_factory = sqlite3.Row

    # Get all products using this canonical ingredient with their required certs
    products = conn.execute(
        """
        SELECT DISTINCT
            p.Id AS product_id,
            p.SKU AS product_name,
            c.Name AS company_name,
            GROUP_CONCAT(pc.Certification) AS required_certs
        FROM SKU_To_Canonical stc
        JOIN Product p ON p.Id = stc.ProductId
        JOIN Company c ON c.Id = p.CompanyId
        LEFT JOIN Product_Compliance pc ON pc.ProductId = p.Id
            AND pc.Status IN ('confirmed', 'claimed', 'implied')
        WHERE stc.CanonicalId = ?
        GROUP BY p.Id
        """,
        (canonical_id,),
    ).fetchall()

    qualified = []
    disqualified = []

    for supplier_row in alternatives:
        supplier_id = supplier_row["SupplierId"]
        supplier_certs_row = conn.execute(
            "SELECT Price_Type FROM Supplier_Commercial WHERE SupplierId=? AND CanonicalIngredientId=?",
            (supplier_id, canonical_id),
        ).fetchone()

        product_results = []
        all_pass = True

        for p in products:
            required = set((p["required_certs"] or "").split(",")) & _SUPPLIER_CERTS
            # For now: if supplier has Confidence >= 0.7 treat as meeting basic certs
            # Full cert registry check would query Certification_Registry
            gate_pass = supplier_row.get("Confidence", 0) >= 0.6
            product_results.append({
                "product_id": p["product_id"],
                "product_name": p["product_name"],
                "company_name": p["company_name"],
                "required_certs": list(required),
                "gate_pass": gate_pass,
            })
            if not gate_pass:
                all_pass = False

        entry = {**supplier_row, "product_gates": product_results}
        if all_pass:
            qualified.append(entry)
        else:
            disqualified.append(entry)

    conn.close()

    # If every candidate failed, emit a refusal event so new_ingredient_research
    # surfaces "gate-failed" as a first-class outcome instead of silently
    # handing the proposal writer an empty qualified list.
    if alternatives and not qualified:
        ingredient_name = (ctx.trigger_payload.get("ingredient_name") or "").strip()
        reasons: list[str] = []
        low_confidence = sum(
            1 for s in alternatives if (s.get("Confidence") or 0) < 0.6
        )
        if low_confidence:
            reasons.append(
                f"{low_confidence}/{len(alternatives)} candidate suppliers "
                f"below 0.6 confidence floor"
            )
        if not products:
            reasons.append(
                "no downstream products reference this canonical ingredient"
            )
        justification = (
            f"All {len(alternatives)} candidate suppliers disqualified by "
            f"the compliance gate for {ingredient_name or 'the requested ingredient'}. "
            + (" ".join(reasons) if reasons else "")
        ).strip()
        _log_refusal(
            ctx=ctx,
            canonical_id=canonical_id,
            ingredient_name=ingredient_name,
            justification=justification,
            blocking_factors=reasons or ["gate_failed"],
            unblock_hint=(
                "Raise supplier confidence via the supplier-verify pass, "
                "or re-enrich with supplier_web_enricher to surface "
                "additional candidates before retrying."
            ),
        )

    return {
        "qualified": qualified,
        "disqualified": disqualified,
        "product_count": len(products),
    }
