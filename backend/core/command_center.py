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
import time

from core import kv

FEED_KEY = "control_feed"
FEED_MAX = 60

# Лента — одна JSON-строка, которую читают и переписывают целиком. Телеграм
# обрабатывает сообщения параллельными задачами, поэтому без замка две записи,
# начатые одновременно, затирали друг друга: побеждала та, что коммитилась
# последней, а вторая исчезала бесследно. Замок теперь общий для всех KV-строк
# (`core/kv`), а не свой у каждого модуля: свой не защищал от соседа.


async def log_event(source: str, role: str, text: str):
    """Добавляет запись в общую ленту. source: dashboard|telegram|system; role: user|agent."""
    entry = {"ts": int(time.time()), "source": source, "role": role,
             "text": (text or "")[:1500]}
    async with kv.update(FEED_KEY, []) as feed:
        feed.append(entry)
        del feed[:-FEED_MAX]          # длина ленты ограничена, правим на месте
    return entry


async def get_feed(limit: int = 40) -> list[dict]:
    feed = await kv.get(FEED_KEY, [])
    return feed[-limit:] if isinstance(feed, list) else []


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

    # Этого ответа ждёт человек: если свои модели откажут, вопрос уйдёт Клоду,
    # а не превратится в отказ.
    from core import ai_escrow
    ai_escrow.interactive(source=source)

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
                # Своих моделей нет — задачу ведёт Клод, а не отказ в ответ.
                from core import ai_escrow
                try:
                    reply = await ai_escrow.ask(
                        "Ты — дирижёр SMM-системы NEXUS AI. Выполни задачу владельца.",
                        text, role="director", errors="нет ни одного ключа ИИ")
                    reason = "escrow_claude"
                except Exception:
                    # Ручной режим выключен — не зовём человека, объясняем прямо.
                    from core.intent import NO_AI_REPLY
                    reply, reason = NO_AI_REPLY, "no_ai_provider"
                reply = f"{reply}\n\n{FREE_SIGNUP_HINT}"
                await log_event(source, "agent", reply)
                return {"ok": True, "reply": reply, "cmd": cmd, "steps": [],
                        "reason": reason}

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
