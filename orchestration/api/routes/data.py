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
            SELECT co.Id as id, ic.Id as ingredient_id, ic.Name as ingredient_name,
                   ic.UNII_Code as unii, ic.Grade_Flag as grade,
                   co.Company_Count as company_count,
                   co.Consolidation_Score as consolidation_score,
                   co.Compliance_Feasible as compliance_feasible,
                   co.Proposal_Text as proposal_text
            FROM Consolidation_Opportunity co
            JOIN Ingredient_Canonical ic ON ic.Id = co.CanonicalIngredientId
            ORDER BY co.Consolidation_Score DESC
        """).fetchall()
    return [
        {**dict(r), "id": str(r["id"]), "ingredient_id": str(r["ingredient_id"]),
         "compliance_feasible": bool(r["compliance_feasible"])}
        for r in rows
    ]


@router.get("/ingredients")
def ingredients(grade: str | None = Query(default=None)):
    with get_db() as db:
        query = """
            SELECT ic.Id as id, ic.Name as display_name, ic.UNII_Code as unii,
                   ic.CAS_Number as cas, ic.PubChem_CID as pubchem_cid,
                   ic.SMILES as smiles, ic.Grade_Flag as grade,
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
    return [dict(r) for r in rows]


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
            SELECT co.Id as id, ic.Id as ingredient_id, ic.Name as ingredient_name,
                   co.Company_Count as company_count,
                   co.Consolidation_Score as consolidation_score,
                   co.Proposal_Text as proposal_text,
                   co.Compliance_Feasible as compliance_feasible,
                   ic.Grade_Flag as grade
            FROM Consolidation_Opportunity co
            JOIN Ingredient_Canonical ic ON ic.Id = co.CanonicalIngredientId
            WHERE co.Proposal_Text IS NOT NULL
            ORDER BY co.Consolidation_Score DESC
        """).fetchall()
    return [
        {**dict(r), "id": str(r["id"]), "ingredient_id": str(r["ingredient_id"]),
         "compliance_feasible": bool(r["compliance_feasible"]), "created_at": ""}
        for r in rows
    ]


@router.get("/fda-limits/{ingredient_id}")
def fda_limits(ingredient_id: int):
    with get_db() as db:
        rows = db.execute(
            """SELECT Route, DosageForm, MaxPotencyAmount, MaxPotencyUnit,
                      MaxDailyExposure, MaxDailyExposureUnit, RecordUpdated
               FROM FDA_Inactive_Ingredient
               WHERE CanonicalIngredientId = ?
               ORDER BY Route, DosageForm""",
            (ingredient_id,),
        ).fetchall()
    return {"ingredient_id": ingredient_id, "limits": [dict(r) for r in rows], "count": len(rows)}


@router.get("/ingredients/{ingredient_id}/safety")
def ingredient_safety(ingredient_id: int):
    from fastapi import HTTPException
    with get_db() as db:
        ic = db.execute(
            """SELECT Name, Grade_Flag, openfda_adverse_event_count
               FROM Ingredient_Canonical WHERE Id = ?""",
            (ingredient_id,),
        ).fetchone()
        if not ic:
            raise HTTPException(status_code=404, detail="Ingredient not found")
        limits = db.execute(
            """SELECT Route, DosageForm, MaxDailyExposure, MaxDailyExposureUnit
               FROM FDA_Inactive_Ingredient
               WHERE CanonicalIngredientId = ? AND MaxDailyExposure IS NOT NULL
               ORDER BY Route""",
            (ingredient_id,),
        ).fetchall()
    return {
        "ingredient_id": ingredient_id,
        "name": ic["Name"],
        "grade": ic["Grade_Flag"],
        "adverse_event_count": ic["openfda_adverse_event_count"],
        "fda_limits": [dict(r) for r in limits],
    }


@router.get("/regulatory-alerts")
def get_regulatory_alerts():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT
                cl.Id, cl.ChangeId, cl.SnapshotDate, cl.IngredientName,
                cl.Route, cl.DosageForm, cl.MaxPotencyPerUnit,
                cl.MaxDailyExposure, cl.MaxDailyExposureUOM, cl.Status,
                cl.CanonicalIngredientId, cl.MatchMethod, cl.MatchScore,
                ic.Name AS canonical_name,
                ic.Grade_Flag AS grade,
                MIN(co.Id) AS opportunity_id,
                MAX(co.Consolidation_Score) AS consolidation_score,
                MAX(co.regulatory_drift_flag) AS regulatory_drift_flag,
                co.regulatory_drift_reason
            FROM FDA_IID_Change_Log cl
            JOIN Ingredient_Canonical ic ON ic.Id = cl.CanonicalIngredientId
            LEFT JOIN Consolidation_Opportunity co ON co.CanonicalIngredientId = cl.CanonicalIngredientId
            GROUP BY cl.ChangeId, cl.SnapshotDate, cl.Route, cl.DosageForm
            ORDER BY cl.Status ASC, cl.ChangeId ASC
        """).fetchall()

    alerts: dict[int, dict] = {}
    for r in rows:
        cid = r["ChangeId"]
        if cid not in alerts:
            alerts[cid] = {
                "change_id": cid,
                "ingredient_name": r["canonical_name"] or r["IngredientName"],
                "status": r["Status"],
                "route": r["Route"],
                "dosage_form": r["DosageForm"],
                "canonical_id": str(r["CanonicalIngredientId"]),
                "grade": r["grade"],
                "opportunity_id": str(r["opportunity_id"]) if r["opportunity_id"] else None,
                "consolidation_score": r["consolidation_score"],
                "regulatory_drift_flag": bool(r["regulatory_drift_flag"]),
                "regulatory_drift_reason": r["regulatory_drift_reason"],
                "snapshots": [],
            }
        alerts[cid]["snapshots"].append({
            "snapshot_date": r["SnapshotDate"],
            "max_potency": r["MaxPotencyPerUnit"],
            "max_daily_exposure": r["MaxDailyExposure"],
            "mde_uom": r["MaxDailyExposureUOM"],
        })

    return {"alerts": list(alerts.values()), "count": len(alerts)}
