"""
Agnes Orchestration API
Run: uvicorn orchestration.api.main:app --reload --port 8000
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from orchestration.api import db as _db
from orchestration.api.routes import chat, pipelines, data_update, data

_DB_PATH = Path(__file__).parent.parent.parent / "orchestration.db"


@asynccontextmanager
async def lifespan(app: FastAPI):
    _db.init_db(_DB_PATH)
    yield


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

_UI_DIST = Path(__file__).parent.parent / "ui" / "dist"
_UI_DEV = Path(__file__).parent.parent / "ui"
_SERVE = _UI_DIST if _UI_DIST.exists() else _UI_DEV
if _SERVE.exists():
    app.mount("/ui/assets", StaticFiles(directory=str(_SERVE / "assets")), name="ui-assets")

    @app.get("/ui", include_in_schema=False)
    @app.get("/ui/", include_in_schema=False)
    def ui_index():
        return FileResponse(
            str(_SERVE / "index.html"),
            headers={"Cache-Control": "no-store"},
        )


@app.get("/health")
def health():
    return {"status": "ok", "service": "agnes-orchestration"}


@app.get("/")
def root():
    return {
        "service": "Agnes Orchestration API",
        "endpoints": {
            "POST /chat": "Send a natural-language message; Agnes picks the pipeline",
            "POST /pipelines/run/{name}": "Trigger a named pipeline directly",
            "GET  /pipelines": "List available pipelines",
            "GET  /runs": "List recent pipeline runs",
            "GET  /runs/{run_id}": "Run status + full event log",
            "GET  /runs/{run_id}/stream": "SSE stream of live pipeline events",
            "GET  /proposals": "List completed proposals",
            "POST /data-update": "Trigger proactive consolidation on new external data",
        },
    }
