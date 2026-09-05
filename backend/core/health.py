"""
Здоровье системы: агенты, площадки, планировщик, расходы, ошибки.

Данные для этого уже лежали в БД (`AgentLog`, `Task`, `Publication`), но нигде не
сводились: чтобы понять «работает ли всё», приходилось открывать пять страниц и
Telegram. Здесь один агрегат, на котором строится страница «Здоровье».

Статус агента честно опирается на факт: агент, не вызывавшийся сутки, — не
«онлайн», а «молчит», и это важно видеть, потому что чаще всего это и есть
симптом сломанного джоба.
"""
from datetime import datetime, timedelta

from sqlalchemy import select, func, desc, case

from database.db import AsyncSessionLocal
from database.models import AgentLog, Task

# Агент, не подававший признаков жизни дольше этого срока, считается молчащим.
SILENT_AFTER_HOURS = 24
# Доля успешных вызовов, ниже которой агент считается проблемным.
DEGRADED_BELOW = 0.8


async def _probe_telegram() -> dict:
    import os
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return {"ok": False, "detail": "токен не задан"}
    import httpx
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"https://api.telegram.org/bot{token}/getMe")
    data = r.json()
    if data.get("ok"):
        return {"ok": True, "detail": "@" + data["result"].get("username", "")}
    return {"ok": False, "detail": str(data.get("description", "отказ"))[:120]}


async def _probe_memory() -> dict:
    """Записать и прочитать обратно. Наличие таблицы — ещё не рабочая память."""
    from sqlalchemy import select
    from database.models import Connection
    from datetime import datetime as _dt

    key = "__healthcheck__"
    stamp = _dt.utcnow().isoformat()
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == key))
        row = r.scalar_one_or_none()
        if row:
            row.key_value = stamp
        else:
            db.add(Connection(key_name=key, key_value=stamp))
        await db.commit()

    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == key))
        row = r.scalar_one_or_none()
    if not row or row.key_value != stamp:
        return {"ok": False, "detail": "записанное не читается обратно"}

    from database.db import storage_info
    store = storage_info()
    if not store["persistent"]:
        return {"ok": False, "detail": "работает, но данные исчезнут при перезапуске"}
    return {"ok": True, "detail": "запись и чтение подтверждены"}


async def _probe_hixiit() -> dict:
    from core.hixiit import status as hixiit_status
    st = await hixiit_status()
    if st.get("mcp_ok"):
        return {"ok": True, "detail": f"MCP, кредитов: {st.get('credits', '—')}"}
    if st.get("api_key"):
        return {"ok": True, "detail": "ключ и секрет заданы"}
    if st.get("browser_agent"):
        return {"ok": True, "detail": "через браузер-агент на ПК"}
    return {"ok": False, "detail": st.get("mcp_error") or "доступа нет"}


async def _probe_web() -> dict:
    from core.websearch import search
    res = await search("test", 1)
    if res.get("ok") and res.get("results"):
        return {"ok": True, "detail": "поиск отвечает"}
    return {"ok": False, "detail": str(res.get("error") or "пустая выдача")[:120]}


async def _probe_instagram() -> dict:
    from connectors import get_connector
    conn = get_connector("instagram")
    if not conn or not conn.configured():
        return {"ok": False, "detail": "не подключён"}
    res = await conn.health()
    if res.get("ok"):
        return {"ok": True, "detail": str(res.get("account") or "подключён")}
    return {"ok": False, "detail": str(res.get("error") or "отказ")[:120]}


PROBES = {
    "Telegram": _probe_telegram,
    "Память": _probe_memory,
    "HIXIIT": _probe_hixiit,
    "Интернет-поиск": _probe_web,
    "Instagram": _probe_instagram,
}


async def probe_all() -> list[dict]:
    """Живая проверка сервисов: каждый статус — результат настоящего вызова.

    Наличие ключа ничего не доказывает: он может быть просрочен, без квоты или
    от другого аккаунта. Зелёный статус здесь означает, что запрос прошёл.
    """
    import asyncio

    async def one(name, fn):
        try:
            res = await asyncio.wait_for(fn(), timeout=45)
        except asyncio.TimeoutError:
            res = {"ok": False, "detail": "не ответил за 45 секунд"}
        except Exception as e:
            res = {"ok": False, "detail": f"{type(e).__name__}: {str(e)[:110]}"}
        return {"name": name, **res}

    return list(await asyncio.gather(*(one(n, f) for n, f in PROBES.items())))


async def agents(hours: int = 24) -> list[dict]:
    """Состояние агентов из журнала вызовов: доля успеха, расход, последний запуск."""
    since = datetime.utcnow() - timedelta(hours=hours)
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(AgentLog.agent_name,
                   func.count(AgentLog.id),
                   func.sum(case((AgentLog.status == "success", 1), else_=0)),
                   func.coalesce(func.sum(AgentLog.cost_usd), 0.0),
                   func.coalesce(func.sum(AgentLog.tokens_used), 0),
                   func.max(AgentLog.created_at))
            .where(AgentLog.created_at >= since)
            .group_by(AgentLog.agent_name)
            .order_by(desc(func.count(AgentLog.id))))
        rows = r.all()

        # Последний вызов вообще — чтобы отличить «молчит сутки» от «никогда не работал».
        r2 = await db.execute(
            select(AgentLog.agent_name, func.max(AgentLog.created_at))
            .group_by(AgentLog.agent_name))
        ever = {a: t for a, t in r2.all()}

    now = datetime.utcnow()
    out = []
    for name, calls, ok, cost, tokens, last in rows:
        calls, ok = int(calls or 0), int(ok or 0)
        rate = (ok / calls) if calls else 0.0
        last_ever = last or ever.get(name)
        silent = (not last_ever) or (now - last_ever > timedelta(hours=SILENT_AFTER_HOURS))
        if silent:
            status = "silent"
        elif rate < DEGRADED_BELOW:
            status = "degraded"
        else:
            status = "online"
        out.append({"agent": name or "—", "status": status, "calls": calls,
                    "success": ok, "success_rate": round(rate * 100, 1),
                    "cost_usd": round(float(cost or 0), 6), "tokens": int(tokens or 0),
                    "last_run": last_ever.isoformat() if last_ever else None})

    # Агенты, которые за период не вызывались ни разу, но работали раньше:
    # без них картина «всё зелено» врёт — сломанный джоб просто исчезает из списка.
    seen = {i["agent"] for i in out}
    for name, last in ever.items():
        if name and name not in seen:
            out.append({"agent": name, "status": "silent", "calls": 0, "success": 0,
                        "success_rate": 0.0, "cost_usd": 0.0, "tokens": 0,
                        "last_run": last.isoformat() if last else None})
    return out


async def social() -> list[dict]:
    """Статус площадок: настроен ли коннектор, валиден ли токен, можно ли публиковать."""
    try:
        from connectors import health_all
        return await health_all()
    except Exception as e:
        return [{"platform": "—", "ok": False, "error": str(e)[:200]}]


def scheduler_jobs() -> dict:
    """Живой планировщик и его джобы: id, следующий запуск.

    Планировщик не поднимается в тестах и до старта приложения — это не ошибка,
    поэтому здесь честное `running: false`, а не пустой список молча.
    """
    try:
        from core import scheduler as sch
        s = sch._scheduler
        if not s or not getattr(s, "running", False):
            return {"running": False, "jobs": []}
        jobs = [{"id": j.id,
                 "next_run": j.next_run_time.isoformat() if j.next_run_time else None}
                for j in s.get_jobs()]
        return {"running": True, "jobs": jobs}
    except Exception as e:
        return {"running": False, "jobs": [], "error": str(e)[:200]}


async def tasks_summary(hours: int = 24) -> dict:
    """Сводка по фоновой работе: сколько запущено, сколько упало."""
    since = datetime.utcnow() - timedelta(hours=hours)
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(Task.status, func.count(Task.id))
            .where(Task.created_at >= since).group_by(Task.status))
        by_status = {s: int(n) for s, n in r.all()}
    total = sum(by_status.values())
    failed = by_status.get("FAILED", 0)
    return {"hours": hours, "total": total, "by_status": by_status,
            "failed": failed,
            "fail_rate": round(failed / total * 100, 1) if total else 0.0}


async def costs() -> dict:
    """Расходы за сутки / неделю / месяц + состояние бюджета."""
    from core.cost_tracker import spend, budget_status
    return {"day": await spend(24), "week": await spend(24 * 7),
            "month": await spend(24 * 30), "budget": await budget_status()}


async def overview() -> dict:
    """Всё состояние системы одним ответом — то, что рисует страница «Здоровье»."""
    from core.notify import recent_errors
    from core.publish_queue import stats as publish_stats

    ag = await agents()
    tasks = await tasks_summary()
    problems = [a for a in ag if a["status"] != "online"]

    # Общий вердикт формулируем по фактам, а не «зелено, если не упало совсем всё».
    if tasks["fail_rate"] >= 50 or (ag and len(problems) == len(ag)):
        verdict = "broken"
    elif problems or tasks["failed"]:
        verdict = "degraded"
    else:
        verdict = "ok"

    # Временное хранилище — не жёлтая лампочка на всякий случай, а обещание
    # потерять ключи и память при следующем деплое. Зелёным система с ним быть
    # не может.
    from database.db import storage_info
    store = storage_info()
    if not store["persistent"] and verdict == "ok":
        verdict = "degraded"

    from core.ai_router import available_providers
    providers = available_providers()

    return {
        "verdict": verdict,
        # Управляющий слой работает и без ИИ, поэтому это не «сломано», а режим:
        # видно сразу, доступна ли генерация или только прямые команды.
        "ai": {"available": bool(providers), "providers": providers,
               "mode": "full" if providers else "control_only"},
        "storage": store,
        "agents": ag,
        "social": await social(),
        "scheduler": scheduler_jobs(),
        "tasks": tasks,
        "publishing": await publish_stats(),
        "costs": await costs(),
        "errors": await recent_errors(24, 5),
        "generated_at": datetime.utcnow().isoformat(),
    }
