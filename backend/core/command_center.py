"""
Единый центр управления — один «мозг» на дашборд и Telegram.

Идея: и дашборд, и Telegram — это лишь два «лица» одного управления. Любая
команда (свободным текстом или слэш-командой) уходит в один и тот же мозг —
Claude-дирижёра (core.marketing_director.run_director), а результат пишется в
ОБЩУЮ ленту активности. Поэтому что сделано из дашборда — видно в Telegram, и
наоборот: они связаны.

Хранилище ленты — таблица Connection (ключ control_feed, JSON-список), без
миграций схемы. Лента ограничена по размеру, чтобы не разрастаться.
"""
import json
import time

from sqlalchemy import select
from database.db import AsyncSessionLocal
from database.models import Connection

FEED_KEY = "control_feed"
FEED_MAX = 60


async def _get_conn(db, key: str):
    r = await db.execute(select(Connection).where(Connection.key_name == key))
    return r.scalar_one_or_none()


async def log_event(source: str, role: str, text: str):
    """Добавляет запись в общую ленту. source: dashboard|telegram|system; role: user|agent."""
    entry = {"ts": int(time.time()), "source": source, "role": role,
             "text": (text or "")[:1500]}
    async with AsyncSessionLocal() as db:
        c = await _get_conn(db, FEED_KEY)
        feed = []
        if c and c.key_value:
            try:
                feed = json.loads(c.key_value)
            except Exception:
                feed = []
        feed.append(entry)
        feed = feed[-FEED_MAX:]
        payload = json.dumps(feed, ensure_ascii=False)
        if c:
            c.key_value = payload
        else:
            db.add(Connection(key_name=FEED_KEY, key_value=payload))
        await db.commit()
    return entry


async def get_feed(limit: int = 40) -> list[dict]:
    async with AsyncSessionLocal() as db:
        c = await _get_conn(db, FEED_KEY)
    if not (c and c.key_value):
        return []
    try:
        feed = json.loads(c.key_value)
    except Exception:
        return []
    return feed[-limit:]


def _summarize(result: dict) -> str:
    """Короткий человекочитаемый итог работы дирижёра."""
    summary = (result.get("summary") or "").strip()
    steps = result.get("steps") or []
    if steps:
        done = sum(1 for s in steps if s.get("result_ok"))
        tail = f"\n\n⚙️ Шагов: {len(steps)} (успешно: {done})"
    else:
        tail = ""
    status = result.get("status", "")
    prefix = "" if status in ("done", "stopped") else f"[{status}] "
    return (prefix + (summary or "Готово.")) + tail


async def run_command(text: str, source: str = "dashboard", mirror: bool = True) -> dict:
    """Единая точка входа команды. Роутит в мозг (Claude-дирижёр), пишет в ленту,
    зеркалит результат в Telegram (если команда пришла из дашборда).

    Возвращает {ok, reply, cmd, steps}.
    """
    text = (text or "").strip()
    if not text:
        return {"ok": False, "reply": "Пустая команда."}

    await log_event(source, "user", text)

    # Маршрутизация свободного текста тем же роутером, что и Telegram.
    try:
        from core import intent
        cmd = await intent.route(text)
    except Exception:
        cmd = "/chat"

    task_id = ""
    try:
        if cmd == "/chat":
            from core import intent
            reply = await intent.chat_reply(text)
            steps = []
        else:
            # Дирижёру нужна модель. Без ключей заводить задачу, которая гарантированно
            # упадёт, — значит мусорить в журнале и врать пользователю про «ошибку
            # выполнения»: проблема не в выполнении, а в том, что выполнять нечем.
            from core.ai_router import ai_available, FREE_SIGNUP_HINT
            if not ai_available():
                from core.intent import NO_AI_REPLY
                reply = NO_AI_REPLY + FREE_SIGNUP_HINT
                await log_event(source, "agent", reply)
                return {"ok": False, "reply": reply, "cmd": cmd, "steps": [],
                        "reason": "no_ai_provider"}

            # Всё остальное ведёт мозг-дирижёр (Claude → инструменты) под задачей,
            # чтобы запуск было видно в /api/tasks и он не пропал при сбое.
            from core.marketing_director import run_director
            from core.task_manager import create, run as run_task, add_step
            task_id = await create("director", text, source=source)
            outcome = await run_task(task_id, lambda: run_director(text))
            if outcome.get("ok"):
                result = outcome["result"]
                reply = _summarize(result)
                steps = result.get("steps", [])
                for s in steps[:20]:
                    await add_step(task_id, str(s.get("action", ""))[:80],
                                   ok=bool(s.get("result_ok", True)),
                                   agent=str(s.get("executor", "") or ""))
            else:
                reply = f"⚠️ Ошибка выполнения: {str(outcome.get('error'))[:200]}"
                steps = []
    except Exception as e:
        reply = f"⚠️ Ошибка выполнения: {str(e)[:200]}"
        steps = []

    if task_id:
        reply = f"{reply}\n\n🆔 {task_id}"

    await log_event(source, "agent", reply)

    # Зеркалим в Telegram, чтобы дашборд и бот были связаны.
    if mirror and source == "dashboard":
        try:
            import os
            chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
            if os.getenv("TELEGRAM_BOT_TOKEN") and chat_id:
                from core.telegram_bot import send_message
                await send_message(chat_id, f"🖥 <b>С дашборда:</b> {text}\n\n{reply}")
        except Exception:
            pass

    return {"ok": True, "reply": reply, "cmd": cmd, "steps": steps, "task_id": task_id}
