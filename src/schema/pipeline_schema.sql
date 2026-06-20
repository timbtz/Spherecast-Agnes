-- Agnes Orchestration Schema
-- Applied by orchestration/api/db.py on first startup against orchestration.db

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id              TEXT    PRIMARY KEY,            -- UUID
    pipeline_name   TEXT    NOT NULL,
    trigger_source  TEXT    NOT NULL,               -- chat|data_update|schedule|manual
    trigger_payload TEXT    NOT NULL DEFAULT '{}',  -- JSON: user message, params extracted by router
    status          TEXT    NOT NULL DEFAULT 'running', -- running|completed|failed
    started_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    completed_at    TEXT,
    error           TEXT,
    metadata        TEXT    NOT NULL DEFAULT '{}'   -- JSON: channel, extra context
);

CREATE TABLE IF NOT EXISTS pipeline_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT    NOT NULL,
    event_type  TEXT    NOT NULL,   -- pipeline_started|node_started|node_completed|node_failed|node_skipped|pipeline_completed|pipeline_failed
    node_id     TEXT,               -- NULL for pipeline-level events
    data        TEXT    NOT NULL DEFAULT '{}',  -- JSON: node_output, error, elapsed_ms
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_pipeline_events_run_id ON pipeline_events(run_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status   ON pipeline_runs(status);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_name     ON pipeline_runs(pipeline_name);
