"""
Agnes Orchestration API
Run: uvicorn orchestration.api.main:app --reload --port 8000
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from orchestration.api import db as _db
from orchestration.api.routes import chat, pipelines, data_update

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
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(pipelines.router)
app.include_router(data_update.router)

_UI_DIR = Path(__file__).parent.parent / "ui"
if _UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(_UI_DIR), html=True), name="ui")


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
