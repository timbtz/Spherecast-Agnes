"""
GET /api/data/* — read-only endpoints for Agnes data explorer.
"""
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/data", tags=["data"])

_DB = Path(__file__).parent.parent.parent.parent / "db_enriched.sqlite"


def get_db():
    conn = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@router.get("/opportunities")
def opportunities():
    with get_db() as db:
        rows = db.execute("""
            SELECT co.Id as id, ic.Name as ingredient, ic.UNII_Code as unii,
                   ic.Grade_Flag as grade_flag, co.Company_Count as company_count,
                   co.Consolidation_Score as score,
                   co.Score_Formula_Component as score_formula_component,
                   co.Compliance_Feasible as compliance_feasible,
                   co.Proposal_Text as proposal_text
            FROM Consolidation_Opportunity co
            JOIN Ingredient_Canonical ic ON ic.Id = co.CanonicalIngredientId
            ORDER BY co.Consolidation_Score DESC
        """).fetchall()
    return {"opportunities": [dict(r) for r in rows], "count": len(rows)}


@router.get("/ingredients")
def ingredients(grade: str | None = Query(default=None)):
    with get_db() as db:
        query = """
            SELECT ic.Id as id, ic.Name as display_name, ic.UNII_Code as unii_code,
                   ic.CAS_Number as cas_number, ic.PubChem_CID as pubchem_cid,
                   ic.SMILES as smiles, ic.Grade_Flag as grade_flag,
                   ic.Confidence as match_score,
                   COUNT(DISTINCT CASE WHEN s.IngredientAId = ic.Id THEN s.IngredientBId END) +
                   COUNT(DISTINCT CASE WHEN s.IngredientBId = ic.Id THEN s.IngredientAId END) as substitution_edges
            FROM Ingredient_Canonical ic
            LEFT JOIN Ingredient_Substitution s ON s.IngredientAId = ic.Id OR s.IngredientBId = ic.Id
        """
        params: list = []
        if grade:
            query += " WHERE ic.Grade_Flag = ?"
            params.append(grade)
        query += " GROUP BY ic.Id ORDER BY ic.Name"
        rows = db.execute(query, params).fetchall()
    return {"ingredients": [dict(r) for r in rows]}


@router.get("/compliance")
def compliance():
    with get_db() as db:
        rows = db.execute("""
            SELECT pc.ProductId as product_id, p.SKU as product_name, c.Name as company,
                   pc.Certification as cert_type, pc.Status as status,
                   pc.Off_Market_Warning as off_market_warning
            FROM Product_Compliance pc
            JOIN Product p ON p.Id = pc.ProductId
            JOIN Company c ON c.Id = p.CompanyId
            ORDER BY c.Name, p.SKU
        """).fetchall()

    # Pivot: one object per product with certifications dict
    products: dict[int, dict] = {}
    for r in rows:
        pid = r["product_id"]
        if pid not in products:
            products[pid] = {
                "product_id": str(pid),
                "product_name": r["product_name"] or f"Product {pid}",
                "company": r["company"],
                "off_market": bool(r["off_market_warning"]),
                "certifications": {},
            }
        status = r["status"] or "implied"
        cert_status = "certified" if status == "confirmed" else "implied"
        products[pid]["certifications"][r["cert_type"]] = cert_status

    return list(products.values())


@router.get("/proposals")
def proposals():
    with get_db() as db:
        rows = db.execute("""
            SELECT ic.Name as ingredient, co.Company_Count as company_count,
                   co.Consolidation_Score as score, co.Proposal_Text as proposal_text,
                   co.Compliance_Feasible as compliance_feasible, ic.Grade_Flag as grade_flag
            FROM Consolidation_Opportunity co
            JOIN Ingredient_Canonical ic ON ic.Id = co.CanonicalIngredientId
            WHERE co.Proposal_Text IS NOT NULL
            ORDER BY co.Consolidation_Score DESC
        """).fetchall()
    return {"proposals": [dict(r) for r in rows]}
