import os
import json
import asyncio
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
from core.scheduler import start_scheduler
from core.telegram_bot import start_polling
from api.routes_auth import router as auth_router
from api.routes_niche import router as niche_router
from api.routes_queue import router as queue_router
from api.routes_prompts import router as prompts_router
from api.routes_settings import router as settings_router
from api.routes_profile import router as profile_router
from api.routes_desktop import router as desktop_router
from api.routes_automation import router as automation_router
from api.routes_control import router as control_router
from api.routes_tasks import router as tasks_router
from api.routes_cost import router as cost_router
from api.routes_publish import router as publish_router
from api.routes_telegram import router as telegram_router
from api.routes_agent_profile import router as agent_profile_router
from api.routes_agents import router as agents_router
from api.routes_health import router as system_router
from api.routes_social import router as social_router, public_router as social_public_router
from api.routes_analytics import router as performance_router
from api.routes_research import router as research_router
from api.routes_strategy import router as strategy_router
from api.routes_engagement import router as engagement_router

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
        # Дублируем в комнату "global": там сидит Командный центр и видит поток
        # событий по всем нишам сразу.
        rooms = {niche_id, "global"}
        payload = json.dumps({**data, "niche_id": niche_id})
        for room in rooms:
            for ws in list(self.connections.get(room, [])):
                try:
                    await ws.send_text(payload)
                except Exception:
                    pass

manager = ConnectionManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Первое, что видно в логах Render: какой код запущен и в каком он состоянии.
    # Без этой строки нельзя было отличить «ошибка не исправлена» от «сборка
    # не доехала», и починка уходила в гадание.
    try:
        from core.version import build_info
        b = build_info()
        print(f"[NEXUS] сборка {b['commit']} · миграции: {b['migration']} · "
              f"Chromium: {'установлен' if b['browser_installed'] else 'нет'}",
              flush=True)
    except Exception:
        pass

    await init_db()
    # Доступы едут в окружение через один слой: он же расшифровывает их и, если
    # шифрование только что включили, дошифровывает старые записи.
    from core.credentials import load_into_env
    await load_into_env()
    # Профиль агента наполняется из прежних настроек один раз — чтобы включение
    # новой формы не выглядело как «мои настройки пропали».
    try:
        from core.agent_profile import bootstrap
        await bootstrap()
    except Exception as e:
        print(f"[NEXUS] профиль агента не заполнен из старых настроек: {e}", flush=True)
    set_broadcast(manager.broadcast)
    # Задачи, зависшие в RUNNING с прошлого запуска, помечаем потерянными —
    # иначе они висят вечно и врут о состоянии системы.
    from core.task_manager import recover_stuck
    await recover_stuck()
    start_scheduler()
    start_polling()
    # Сервер сам делает разбор аккаунта и шлёт в Telegram (раз в сутки).
    from core.auto_report import auto_analyze_on_start
    asyncio.create_task(auto_analyze_on_start())
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
app.include_router(automation_router, dependencies=[Depends(require_auth)])
app.include_router(control_router,    dependencies=[Depends(require_auth)])
app.include_router(tasks_router,      dependencies=[Depends(require_auth)])
app.include_router(cost_router,       dependencies=[Depends(require_auth)])
app.include_router(publish_router,    dependencies=[Depends(require_auth)])
app.include_router(telegram_router,   dependencies=[Depends(require_auth)])
app.include_router(agent_profile_router, dependencies=[Depends(require_auth)])
app.include_router(agents_router,     dependencies=[Depends(require_auth)])
app.include_router(system_router,     dependencies=[Depends(require_auth)])
app.include_router(social_router,     dependencies=[Depends(require_auth)])
app.include_router(performance_router, dependencies=[Depends(require_auth)])
app.include_router(research_router,   dependencies=[Depends(require_auth)])
app.include_router(strategy_router,   dependencies=[Depends(require_auth)])
app.include_router(engagement_router, dependencies=[Depends(require_auth)])
# OAuth-callback вызывает Meta в браузере пользователя — без нашей авторизации.
app.include_router(social_public_router)
# Desktop agent — WebSocket must be outside auth dependency
app.include_router(desktop_router)

@app.get("/api/health")
async def health():
    """Лёгкий health-эндпоинт для внешней «пробуждалки» (UptimeRobot и т.п.),
    чтобы бесплатный Render не засыпал и Telegram-бот не замолкал.

    Отдаёт версию запущенного кода: без неё нельзя отличить «ошибка не исправлена»
    от «исправление ещё не задеплоено», и починка уходит в гадание.
    """
    from core.version import build_info
    return {"ok": True, "service": "nexus-ai", "build": build_info()}

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
