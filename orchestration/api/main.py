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
