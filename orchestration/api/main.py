"""
Agnes Orchestration API
Run: uvicorn orchestration.api.main:app --reload --port 8000
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from orchestration.api import db as _db
from orchestration.api.routes import chat, pipelines, data_update, data, scoring, alerts

_DB_PATH = Path(__file__).parent.parent.parent / "orchestration.db"
logger = logging.getLogger("agnes.scheduler")

_PRICE_MONITOR_INTERVAL_H = 24


async def _price_monitor_scheduler():
    """Background loop: trigger price_monitor pipeline every 24h."""
    from orchestration.api import dag_executor

    await asyncio.sleep(60)  # Wait 60s after startup before first run
    while True:
        if os.environ.get("GOOGLE_API_KEY"):
            try:
                logger.info("Scheduler: triggering price_monitor pipeline")
                await dag_executor.execute_pipeline("price_monitor", "scheduled", {})
            except Exception as e:
                logger.error(f"Scheduler: price_monitor failed: {e}")
        await asyncio.sleep(_PRICE_MONITOR_INTERVAL_H * 3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _db.init_db(_DB_PATH)
    task = asyncio.create_task(_price_monitor_scheduler())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Agnes — Supply Chain Orchestration API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*", "Last-Event-ID"],
)

app.include_router(chat.router)
app.include_router(pipelines.router)
app.include_router(data_update.router)
app.include_router(data.router)
app.include_router(scoring.router)
app.include_router(alerts.router)

@app.get("/health")
def health():
    return {"status": "ok", "service": "agnes-orchestration"}


# --- SPA (Lovable frontend) served at root ---
# Build: cd orchestration/ui && bun install && bun run build
# Update from Lovable: ./pull-ui.sh
_UI_DIST = Path(__file__).parent.parent / "ui" / "dist"
if _UI_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(_UI_DIST / "assets")), name="ui-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_index(full_path: str):
        return FileResponse(str(_UI_DIST / "index.html"), headers={"Cache-Control": "no-store"})
