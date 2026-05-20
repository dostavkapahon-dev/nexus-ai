import os
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import select

from database.db import init_db, AsyncSessionLocal
from database.models import Connection
from core.orchestrator import set_broadcast
from api.routes_niche import router as niche_router
from api.routes_queue import router as queue_router
from api.routes_prompts import router as prompts_router
from api.routes_settings import router as settings_router

class ConnectionManager:
    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(self, niche_id: str, ws: WebSocket):
        await ws.accept()
        self.connections.setdefault(niche_id, []).append(ws)

    def disconnect(self, niche_id: str, ws: WebSocket):
        if niche_id in self.connections:
            self.connections[niche_id].discard(ws) if hasattr(self.connections[niche_id], 'discard') else None
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

app = FastAPI(lifespan=lifespan, title="NEXUS AI")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(niche_router)
app.include_router(queue_router)
app.include_router(prompts_router)
app.include_router(settings_router)

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
        index = os.path.join(frontend_dist, "index.html")
        return FileResponse(index)
