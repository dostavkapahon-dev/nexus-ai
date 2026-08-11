"""
Отчёты о завершении фоновой работы в Telegram.

Раньше о провале фоновой задачи владелец узнавал, только если сам заходил в
`/tasks` или в дашборд: ночной джоб мог падать неделю подряд, и снаружи это
выглядело как «система просто ничего не постит». Теперь итог приходит сам.

Правило громкости: сообщаем о том, что требует внимания или действия —
провалы, ожидание согласования, отмены. Успех фонового джоба молчалив, иначе
чат превращается в поток «всё хорошо» и в нём тонут настоящие проблемы.
Задачи, запущенные человеком из Telegram, отвечают сами — их не дублируем.
"""
import os

# Ручной запуск из Telegram отчитывается сам, в своём же диалоге.
_SELF_REPORTING_SOURCES = ("telegram",)

# Статусы, о которых стоит написать без спроса.
_LOUD = ("FAILED", "WAITING", "CANCELLED")

_KIND_RU = {
    "factory": "Фабрика контента", "pipeline": "Полный цикл по нише",
    "publish": "Публикация", "generate": "Генерация материалов",
    "trends": "Анализ трендов", "report": "Отчёт", "director": "Дирижёр",
    "metrics": "Сбор метрик", "competitors": "Конкуренты",
    "comments": "Комментарии", "tokens": "Токены площадок",
    "analytics": "Еженедельная аналитика",
}


def _chat_id() -> str:
    return os.getenv("TELEGRAM_CHAT_ID", "")


def should_report(task: dict) -> bool:
    """Стоит ли писать в Telegram про эту задачу."""
    if task.get("source") in _SELF_REPORTING_SOURCES:
        return False
    return task.get("status") in _LOUD


def format_task(task: dict) -> str:
    """Короткий отчёт: что за работа, чем кончилась, что делать дальше."""
    status = task.get("status", "")
    kind = _KIND_RU.get(task.get("kind", ""), task.get("kind") or "задача")
    head = {"FAILED": "❌ <b>Задача провалилась</b>",
            "WAITING": "⏸ <b>Задача ждёт согласования</b>",
            "CANCELLED": "🚫 <b>Задача отменена</b>",
            "COMPLETED": "✅ <b>Задача выполнена</b>"}.get(status, f"• <b>{status}</b>")

    lines = [head, f"{kind} · <code>{task.get('id', '')}</code>"]
    if task.get("goal"):
        lines.append(str(task["goal"])[:150])
    if task.get("duration_sec"):
        lines.append(f"Время: {float(task['duration_sec']):.0f} с")
    if task.get("cost_usd"):
        lines.append(f"Расход: ${float(task['cost_usd']):.4f}")

    if status == "FAILED":
        # Без текста ошибки отчёт бесполезен: чинить будет нечего.
        lines.append(f"\n⚠️ {str(task.get('error') or 'причина не сохранена')[:300]}")
        lines.append(f"\nПодробности: /task {task.get('id', '')}")
    elif status == "WAITING":
        lines.append("\nМатериал отправлен на согласование — ждём вашего решения.")
    return "\n".join(lines)


async def task_finished(task: dict):
    """Шлёт отчёт о завершившейся задаче. Никогда не роняет вызывающего."""
    try:
        if not should_report(task):
            return
        chat_id = _chat_id()
        if not (os.getenv("TELEGRAM_BOT_TOKEN") and chat_id):
            return
        from core.telegram_bot import send_message
        await send_message(chat_id, format_task(task))
    except Exception:
        pass


async def recent_errors(hours: int = 24, limit: int = 10) -> dict:
    """Свежие сбои системы: провалившиеся задачи и ошибки агентов.

    Один список вместо двух разных мест — по нему видно, сломано ли что-то
    сейчас, без похода в дашборд.
    """
    from datetime import datetime, timedelta
    from sqlalchemy import select, desc
    from database.db import AsyncSessionLocal
    from database.models import Task, AgentLog

    since = datetime.utcnow() - timedelta(hours=hours)
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(Task).where(Task.status == "FAILED")
            .where(Task.created_at >= since)
            .order_by(desc(Task.created_at)).limit(limit))
        tasks = [{"id": t.id, "kind": t.kind, "goal": (t.goal or "")[:80],
                  "error": (t.error or "")[:200],
                  "at": t.finished_at.isoformat() if t.finished_at else None}
                 for t in r.scalars().all()]

        r = await db.execute(
            select(AgentLog).where(AgentLog.status != "success")
            .where(AgentLog.created_at >= since)
            .order_by(desc(AgentLog.created_at)).limit(limit))
        agents = [{"agent": a.agent_name, "model": a.model_used,
                   "error": (a.error or "")[:200],
                   "at": a.created_at.isoformat() if a.created_at else None}
                  for a in r.scalars().all()]

    return {"hours": hours, "tasks": tasks, "agents": agents,
            "total": len(tasks) + len(agents)}
