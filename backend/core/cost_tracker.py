"""
Учёт расходов на AI — единая касса.

Раньше в `AgentLog` попадали только вызовы через `BaseAgent`, а автопилот, фабрика,
дирижёр, viral_research и intent тратили бюджет мимо учёта — цифра «Потрачено»
занижалась в разы. Теперь запись делает сам `ai_router`, поэтому под учётом
оказывается КАЖДЫЙ вызов модели, кто бы его ни инициировал.

Привязка к задаче идёт через contextvar: `task_manager.run()` выставляет id текущей
задачи, и вызовы внутри неё сами попадают в её расход — менять вызывающий код не нужно.
"""
import os

from core import notify
from contextvars import ContextVar
from datetime import datetime, timedelta

from sqlalchemy import select, func

from database.db import AsyncSessionLocal
from database.models import AgentLog, UserProfile

# Кто и в рамках какой задачи сейчас вызывает модель (для атрибуции расхода).
current_task_id: ContextVar[str] = ContextVar("current_task_id", default="")
current_agent: ContextVar[str] = ContextVar("current_agent", default="")
current_niche_id: ContextVar[str] = ContextVar("current_niche_id", default="")

DEFAULT_BUDGET_USD_DAY = 5.0


async def record(model: str, tokens: int = 0, cost: float = 0.0, status: str = "success",
                 duration: float = 0.0, error: str = "", agent: str = ""):
    """Пишет расход одного вызова модели в AgentLog и в текущую задачу.

    Никогда не роняет вызывающего: учёт не должен ломать основную работу.
    """
    agent = agent or current_agent.get() or "core"
    try:
        async with AsyncSessionLocal() as db:
            db.add(AgentLog(niche_id=current_niche_id.get() or "", agent_name=agent, status=status,
                            model_used=model or "", tokens_used=int(tokens or 0),
                            cost_usd=float(cost or 0.0), duration_sec=float(duration or 0.0),
                            error=(error or None)))
            await db.commit()
    except Exception:
        pass

    task_id = current_task_id.get()
    if task_id:
        try:
            from core.task_manager import add_cost
            await add_cost(task_id, model=model, tokens=tokens, cost=cost)
        except Exception:
            pass


async def spend(hours: int = 24) -> dict:
    """Сколько потрачено и сколько токенов израсходовано за период."""
    since = datetime.utcnow() - timedelta(hours=hours)
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(func.coalesce(func.sum(AgentLog.cost_usd), 0.0),
                   func.coalesce(func.sum(AgentLog.tokens_used), 0),
                   func.count(AgentLog.id))
            .where(AgentLog.created_at >= since)
        )
        cost, tokens, calls = r.one()
    return {"hours": hours, "cost_usd": round(float(cost or 0), 6),
            "tokens": int(tokens or 0), "calls": int(calls or 0)}


async def budget_limit() -> float:
    """Дневной лимит: из профиля, иначе из env, иначе значение по умолчанию."""
    try:
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(UserProfile).limit(1))
            prof = r.scalar_one_or_none()
        if prof and (prof.budget_usd_day or 0) > 0:
            return float(prof.budget_usd_day)
    except Exception:
        pass
    try:
        return float(os.getenv("AI_BUDGET_USD_DAY", DEFAULT_BUDGET_USD_DAY))
    except ValueError:
        return DEFAULT_BUDGET_USD_DAY


async def budget_status() -> dict:
    """Состояние бюджета за сутки: потрачено, лимит, процент, нужен ли алерт/стоп."""
    day = await spend(24)
    limit = await budget_limit()
    used = day["cost_usd"]
    pct = round(used / limit * 100, 1) if limit > 0 else 0.0
    return {**day, "limit_usd": limit, "used_pct": pct,
            "alert": pct >= 80, "exceeded": limit > 0 and used >= limit}


async def by_model(hours: int = 24, limit: int = 10) -> list[dict]:
    """Разбивка расхода по моделям — что именно съедает бюджет."""
    since = datetime.utcnow() - timedelta(hours=hours)
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(AgentLog.model_used,
                   func.coalesce(func.sum(AgentLog.cost_usd), 0.0),
                   func.coalesce(func.sum(AgentLog.tokens_used), 0),
                   func.count(AgentLog.id))
            .where(AgentLog.created_at >= since)
            .group_by(AgentLog.model_used)
            .order_by(func.coalesce(func.sum(AgentLog.cost_usd), 0.0).desc())
            .limit(limit)
        )
        rows = r.all()
    return [{"model": m or "—", "cost_usd": round(float(c or 0), 6),
             "tokens": int(t or 0), "calls": int(n or 0)} for m, c, t, n in rows]


async def by_agent(hours: int = 24, limit: int = 10) -> list[dict]:
    """Разбивка по агентам — кто инициирует расход."""
    since = datetime.utcnow() - timedelta(hours=hours)
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(AgentLog.agent_name,
                   func.coalesce(func.sum(AgentLog.cost_usd), 0.0),
                   func.count(AgentLog.id))
            .where(AgentLog.created_at >= since)
            .group_by(AgentLog.agent_name)
            .order_by(func.coalesce(func.sum(AgentLog.cost_usd), 0.0).desc())
            .limit(limit)
        )
        rows = r.all()
    return [{"agent": a or "—", "cost_usd": round(float(c or 0), 6), "calls": int(n or 0)}
            for a, c, n in rows]


async def by_kind(hours: int = 24) -> dict:
    """Разделяет расход на текст и медиа: видео стоит в разы больше текста,
    и смешивать их в одной цифре — значит не понимать, куда уходит бюджет."""
    since = datetime.utcnow() - timedelta(hours=hours)
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(AgentLog.agent_name,
                   func.coalesce(func.sum(AgentLog.cost_usd), 0.0),
                   func.count(AgentLog.id))
            .where(AgentLog.created_at >= since)
            .group_by(AgentLog.agent_name))
        rows = r.all()

    media_cost, media_calls = 0.0, 0
    text_cost, text_calls = 0.0, 0
    for agent, cost, n in rows:
        if agent == "media":
            media_cost += float(cost or 0); media_calls += int(n or 0)
        else:
            text_cost += float(cost or 0); text_calls += int(n or 0)
    return {"media": {"cost_usd": round(media_cost, 6), "calls": media_calls},
            "text": {"cost_usd": round(text_cost, 6), "calls": text_calls}}


_alerted_at = {"day": "", "level": 0}


async def maybe_alert():
    """Шлёт в Telegram предупреждение при 80 % бюджета и при превышении.

    На каждый уровень — не чаще одного раза в сутки, чтобы не спамить.
    """
    try:
        st = await budget_status()
        today = datetime.utcnow().date().isoformat()
        level = 2 if st["exceeded"] else (1 if st["alert"] else 0)
        if level == 0:
            return
        if _alerted_at["day"] == today and _alerted_at["level"] >= level:
            return

        chat_id = await notify.owner_chat()
        if not (os.getenv("TELEGRAM_BOT_TOKEN") and chat_id):
            return
        from core.telegram_bot import send_message
        if level == 2:
            text = (f"🛑 <b>Дневной бюджет AI исчерпан</b>\n"
                    f"Потрачено ${st['cost_usd']:.4f} из ${st['limit_usd']:.2f} "
                    f"({st['used_pct']}%).\n\nПлатные модели можно приостановить: /cost")
        else:
            text = (f"⚠️ <b>Бюджет AI на {st['used_pct']}%</b>\n"
                    f"Потрачено ${st['cost_usd']:.4f} из ${st['limit_usd']:.2f} за сутки.")
        await send_message(chat_id, text)
        _alerted_at.update(day=today, level=level)
    except Exception:
        pass
