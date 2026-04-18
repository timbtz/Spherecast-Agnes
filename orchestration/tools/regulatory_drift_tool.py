"""
Deterministic tool: detect regulatory drift from FDA_IID_Change_Log,
pair before/after rows for Status=C, assign severity, cross-reference opportunities.
"""
import sqlite3

from orchestration.api.agnes_context import AgnesContext

_SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def _try_float(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return float(s.strip())
    except (ValueError, AttributeError):
        return None


def run(ctx: AgnesContext) -> dict:
    conn = sqlite3.connect(str(ctx.enriched_db_path))
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT cl.ChangeId, cl.SnapshotDate, cl.IngredientName, cl.Route,
               cl.DosageForm, cl.MaxPotencyPerUnit, cl.MaxDailyExposure,
               cl.MaxDailyExposureUOM, cl.Status, cl.CanonicalIngredientId,
               ic.Name AS canonical_name,
               co.Id AS opportunity_id, co.Consolidation_Score
        FROM FDA_IID_Change_Log cl
        JOIN Ingredient_Canonical ic ON ic.Id = cl.CanonicalIngredientId
        LEFT JOIN Consolidation_Opportunity co ON co.CanonicalIngredientId = cl.CanonicalIngredientId
        ORDER BY cl.ChangeId, cl.SnapshotDate
    """).fetchall()
    conn.close()

    # Group rows by ChangeId
    by_change: dict[int, list] = {}
    for r in rows:
        cid = r["ChangeId"]
        if cid not in by_change:
            by_change[cid] = []
        by_change[cid].append(r)

    alerts: list[dict] = []
    for change_id, group in by_change.items():
        first = group[0]
        status = first["Status"]
        canonical_id = first["CanonicalIngredientId"]
        ingredient_name = first["canonical_name"] or first["IngredientName"]
        route = first["Route"] or ""
        dosage_form = first["DosageForm"] or ""
        opportunity_id = first["opportunity_id"]
        consolidation_score = first["Consolidation_Score"]

        q1_row = next((r for r in group if r["SnapshotDate"] == "Q1 2026"), None)
        q2_row = next((r for r in group if r["SnapshotDate"] == "Q2 2026"), None)
        q1_mde = q1_row["MaxDailyExposure"] if q1_row else None
        q2_mde = q2_row["MaxDailyExposure"] if q2_row else None

        if status == "D":
            severity = "HIGH"
            summary = f"{ingredient_name} ({route}/{dosage_form}) was DELETED from FDA IID Q1→Q2 2026"
        elif status == "C":
            q1_val = _try_float(q1_mde)
            q2_val = _try_float(q2_mde)
            if q1_val is not None and q2_val is not None:
                if q2_val < q1_val:
                    severity = "HIGH"
                else:
                    severity = "LOW"
            else:
                severity = "MEDIUM"
            uom = first["MaxDailyExposureUOM"] or ""
            summary = f"{ingredient_name}: MDE corrected {q1_mde}→{q2_mde} {uom}".strip()
        else:  # R
            severity = "MEDIUM"
            summary = f"{ingredient_name} ({route}/{dosage_form}) was REVISED in Q2 2026"

        alerts.append({
            "canonical_id": canonical_id,
            "ingredient_name": ingredient_name,
            "change_id": change_id,
            "status": status,
            "severity": severity,
            "change_summary": summary,
            "route": route,
            "dosage_form": dosage_form,
            "q1_mde": q1_mde,
            "q2_mde": q2_mde,
            "has_opportunity": opportunity_id is not None,
            "opportunity_id": opportunity_id,
            "consolidation_score": consolidation_score,
        })

    alerts.sort(key=lambda a: _SEVERITY_ORDER.get(a["severity"], 99))

    top_canonical_id = alerts[0]["canonical_id"] if alerts else None
    high_count = sum(1 for a in alerts if a["severity"] == "HIGH")

    return {
        "drift_alerts": alerts,
        "canonical_id": top_canonical_id,
        "count": len(alerts),
        "high_severity_count": high_count,
    }
