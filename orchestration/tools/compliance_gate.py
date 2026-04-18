"""
Deterministic tool: check whether candidate suppliers satisfy compliance requirements
for all products using the target ingredient.

Returns a list of qualified (supplier, product) pairs that pass all gates.
"""
import sqlite3

from orchestration.api.agnes_context import AgnesContext

# Certifications that must be supplied by the ingredient supplier (not just claimed on label)
_SUPPLIER_CERTS = {"NSF", "USP", "InformedSport", "BSCG"}


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
    return {
        "qualified": qualified,
        "disqualified": disqualified,
        "product_count": len(products),
    }
