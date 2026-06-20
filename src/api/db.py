import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Optional

from orchestration.api.event_bus import publish

_SCHEMA = Path(__file__).parent.parent / "schema" / "pipeline_schema.sql"
_DEFAULT_DB = Path(__file__).parent.parent.parent / "orchestration.db"


def get_conn(db_path: Path = _DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(db_path: Path = _DEFAULT_DB) -> None:
    conn = get_conn(db_path)
    conn.executescript(_SCHEMA.read_text())
    conn.commit()
    conn.close()


# ── Run lifecycle ────────────────────────────────────────────────────────────

def create_run(
    pipeline_name: str,
    trigger_source: str,
    trigger_payload: dict,
    db_path: Path = _DEFAULT_DB,
) -> str:
    run_id = str(uuid.uuid4())
    conn = get_conn(db_path)
    conn.execute(
        "INSERT INTO pipeline_runs (id, pipeline_name, trigger_source, trigger_payload) VALUES (?,?,?,?)",
        (run_id, pipeline_name, trigger_source, json.dumps(trigger_payload)),
    )
    conn.commit()
    conn.close()
    return run_id


def update_run_status(
    run_id: str,
    status: str,
    error: Optional[str] = None,
    db_path: Path = _DEFAULT_DB,
) -> None:
    conn = get_conn(db_path)
    conn.execute(
        "UPDATE pipeline_runs SET status=?, completed_at=datetime('now'), error=? WHERE id=?",
        (status, error, run_id),
    )
    conn.commit()
    conn.close()


def get_run(run_id: str, db_path: Path = _DEFAULT_DB) -> Optional[dict]:
    conn = get_conn(db_path)
    row = conn.execute("SELECT * FROM pipeline_runs WHERE id=?", (run_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_runs(limit: int = 50, db_path: Path = _DEFAULT_DB) -> list[dict]:
    conn = get_conn(db_path)
    rows = conn.execute(
        "SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Event log ────────────────────────────────────────────────────────────────

async def write_event(
    run_id: str,
    event_type: str,
    node_id: Optional[str] = None,
    data: Optional[dict] = None,
    db_path: Path = _DEFAULT_DB,
) -> None:
    payload = data or {}
    conn = get_conn(db_path)
    conn.execute(
        "INSERT INTO pipeline_events (run_id, event_type, node_id, data) VALUES (?,?,?,?)",
        (run_id, event_type, node_id, json.dumps(payload)),
    )
    conn.commit()
    conn.close()
    await publish(run_id, {"event_type": event_type, "node_id": node_id, **payload})


def get_events(run_id: str, db_path: Path = _DEFAULT_DB) -> list[dict]:
    conn = get_conn(db_path)
    rows = conn.execute(
        "SELECT * FROM pipeline_events WHERE run_id=? ORDER BY id", (run_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_run_with_events(run_id: str, db_path: Path = _DEFAULT_DB) -> Optional[dict]:
    run = get_run(run_id, db_path)
    if not run:
        return None
    events = get_events(run_id, db_path)
    run["events"] = events
    return run
