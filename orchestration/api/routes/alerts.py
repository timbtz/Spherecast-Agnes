"""Price change alert endpoints."""
import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/alerts", tags=["alerts"])
_DB = Path(__file__).parent.parent.parent.parent / "db_enriched.sqlite"


def _get_db_ro():
    conn = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _get_db_rw():
    conn = sqlite3.connect(str(_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/count")
def alert_count():
    """Unread (non-dismissed) alert count — used for TopBar badge."""
    with _get_db_ro() as db:
        row = db.execute(
            "SELECT COUNT(*) FROM Price_Change_Alert WHERE Dismissed = 0"
        ).fetchone()
    return {"count": row[0]}


@router.get("/")
def list_alerts(
    dismissed: bool = Query(default=False),
    severity: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
):
    with _get_db_ro() as db:
        q = """SELECT a.*, ic.Grade_Flag as grade
               FROM Price_Change_Alert a
               JOIN Ingredient_Canonical ic ON ic.Id = a.CanonicalIngredientId
               WHERE a.Dismissed = ?"""
        params: list = [int(dismissed)]
        if severity:
            q += " AND a.Severity = ?"
            params.append(severity)
        q += " ORDER BY a.Detected_At DESC LIMIT ?"
        params.append(limit)
        rows = db.execute(q, params).fetchall()
    return {"alerts": [dict(r) for r in rows], "count": len(rows)}


@router.post("/{alert_id}/dismiss")
def dismiss_alert(alert_id: int):
    with _get_db_rw() as db:
        row = db.execute("SELECT Id FROM Price_Change_Alert WHERE Id = ?", (alert_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Alert not found")
        db.execute("UPDATE Price_Change_Alert SET Dismissed = 1 WHERE Id = ?", (alert_id,))
        db.commit()
    return {"status": "dismissed", "alert_id": alert_id}


@router.get("/ingredient/{ingredient_id}")
def ingredient_alerts(ingredient_id: int, limit: int = Query(default=20, le=100)):
    with _get_db_ro() as db:
        rows = db.execute(
            """SELECT * FROM Price_Change_Alert
               WHERE CanonicalIngredientId = ?
               ORDER BY Detected_At DESC LIMIT ?""",
            (ingredient_id, limit)
        ).fetchall()
    return {"ingredient_id": ingredient_id, "alerts": [dict(r) for r in rows], "count": len(rows)}
