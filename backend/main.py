import os
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select

from database.db import init_db, AsyncSessionLocal
from database.models import Connection
from core.orchestrator import set_broadcast
from core.auth import require_auth, check_rate
from api.routes_auth import router as auth_router
from api.routes_niche import router as niche_router
from api.routes_queue import router as queue_router
from api.routes_prompts import router as prompts_router
from api.routes_settings import router as settings_router
from api.routes_profile import router as profile_router
from api.routes_desktop import router as desktop_router

class ConnectionManager:
    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(self, niche_id: str, ws: WebSocket):
        await ws.accept()
        self.connections.setdefault(niche_id, []).append(ws)

    def disconnect(self, niche_id: str, ws: WebSocket):
        if niche_id in self.connections:
            try:
                self.connections[niche_id].remove(ws)
            except ValueError:
                pass

    async def broadcast(self, niche_id: str, data: dict):
        for ws in list(self.connections.get(niche_id, [])):
            try:
                await ws.send_text(json.dumps(data))
            except Exception:
                pass

manager = ConnectionManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Connection))
        for conn in result.scalars():
            os.environ[conn.key_name.upper()] = conn.key_value or ""
    set_broadcast(manager.broadcast)
    yield

app = FastAPI(lifespan=lifespan, title="NEXUS AI", docs_url=None, redoc_url=None)

# CORS — allow same origin + localhost dev
origins = ["http://localhost:5173", "http://localhost:3000"]
render_url = os.getenv("RENDER_EXTERNAL_URL", "")
if render_url:
    origins.append(render_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def security_headers(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"
    try:
        check_rate(ip)
    except Exception:
        return JSONResponse(status_code=429, content={"detail": "Too many requests"})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# Public routes (no auth)
app.include_router(auth_router)

# Protected API routes
app.include_router(niche_router,    dependencies=[Depends(require_auth)])
app.include_router(queue_router,    dependencies=[Depends(require_auth)])
app.include_router(prompts_router,  dependencies=[Depends(require_auth)])
app.include_router(settings_router, dependencies=[Depends(require_auth)])
app.include_router(profile_router,  dependencies=[Depends(require_auth)])
# Desktop agent — WebSocket must be outside auth dependency
app.include_router(desktop_router)

@app.websocket("/ws/{niche_id}")
async def websocket_endpoint(websocket: WebSocket, niche_id: str):
    await manager.connect(niche_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(niche_id, websocket)

# Serve frontend in production
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        return FileResponse(os.path.join(frontend_dist, "index.html"))
