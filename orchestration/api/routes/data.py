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


def _normalize_name(name: str | None) -> str:
    if not name:
        return ""
    return name.title() if name.isupper() else name


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
    return [{**dict(r), "display_name": _normalize_name(r["display_name"])} for r in rows]


CERT_IMPLICATIONS = {
    "Vegan": ["Vegetarian"],
    "Organic": ["NonGMO"],
    "NSF": ["cGMP"],
    "InformedSport": ["cGMP"],
    "USP": ["cGMP"],
}


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

    products: dict[int, dict] = {}
    for r in rows:
        pid = r["product_id"]
        if pid not in products:
            sku = r["product_name"] or ""
            if sku.startswith("FG-"):
                # Strip source prefix (FG-iherb-, FG-amazon-, FG-thrive-market-, etc.)
                parts = sku[3:].split("-", 1)
                product_id_part = parts[1] if len(parts) > 1 else parts[0]
                display = f"{r['company']} #{product_id_part}"
            else:
                display = sku or f"{r['company']} Product {pid}"
            products[pid] = {
                "product_id": str(pid),
                "product_name": display,
                "company": r["company"],
                "off_market": bool(r["off_market_warning"]),
                "certifications": {},
            }
        status = r["status"] or "implied"
        cert_status = "certified" if status == "confirmed" else status if status == "derived" else "implied"
        products[pid]["certifications"][r["cert_type"]] = cert_status

    for prod in products.values():
        certs = prod["certifications"]
        for source_cert, implied_certs in CERT_IMPLICATIONS.items():
            if source_cert in certs:
                for implied in implied_certs:
                    if implied not in certs:
                        certs[implied] = "derived"

    result = list(products.values())
    return {"products": result, "count": len(result)}


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


@router.get("/proposals/{opportunity_id}/citations")
def proposal_citations(opportunity_id: int):
    try:
        with get_db() as db:
            rows = db.execute(
                """SELECT Id as id, OpportunityId as opportunity_id,
                          ClaimText as claim_text, SourceType as source_type,
                          SourceId as source_id, SourceUrl as source_url,
                          SourceSnippet as source_snippet, Confidence as confidence,
                          CreatedAt as created_at
                   FROM Claim_Citation
                   WHERE OpportunityId = ?
                   ORDER BY Id""",
                (opportunity_id,),
            ).fetchall()
        return {"opportunity_id": opportunity_id, "citations": [dict(r) for r in rows], "count": len(rows)}
    except Exception:
        return {"opportunity_id": opportunity_id, "citations": [], "count": 0}


@router.get("/refusals")
def get_refusals():
    import json as _json
    try:
        with get_db() as db:
            rows = db.execute(
                """SELECT Id as id, CanonicalId as canonical_id,
                          IngredientName as ingredient_name, Decision as decision,
                          Justification as justification, Confidence as confidence,
                          BlockingFactors as blocking_factors_raw,
                          UnblockHint as unblock_hint, CreatedAt as created_at
                   FROM Refusal_Log
                   WHERE Decision IN ('refuse', 'refuse_gate_fail', 'refuse_compliance',
                                       'refuse_low_confidence', 'defer_human_review')
                   ORDER BY Confidence DESC
                   LIMIT 100""",
            ).fetchall()
        result = []
        for r in rows:
            row = dict(r)
            try:
                row["blocking_factors"] = _json.loads(row.pop("blocking_factors_raw") or "[]")
            except (ValueError, TypeError):
                row["blocking_factors"] = []
                row.pop("blocking_factors_raw", None)
            result.append(row)
        return {"refusals": result, "count": len(result)}
    except Exception:
        return {"refusals": [], "count": 0}
