"""
Живой статус задачи в Telegram: одно сообщение, которое обновляется по шагам.

Между «запущено» и «готово» проходят минуты, и всё это время человек видел
пустой экран — «я нажал кнопку, и ничего не происходит». Здесь задача получает
одно сообщение вида

    ⚙️ Делаю ролик
    ✅ 1/7 Анализ задачи
    ✅ 2/7 Исследование
    ⏳ 3/7 Сценарий

и оно редактируется на каждом шаге, а не засыпает чат новыми сообщениями.
"""
import os

import httpx

from core.task_manager import add_step, CREATED, RUNNING, WAITING, COMPLETED, FAILED

# Ожидаемые шаги конвейера — по ним считается «3 из 7». Список неточен для любой
# задачи, поэтому знаменателем берём максимум из плана и факта: показать «8/7»
# хуже, чем показать честное «8/8».
PLAN = ["Анализ задачи", "Исследование", "Сценарий", "Промпты",
        "Генерация", "Проверка", "Готовый результат"]

_messages: dict[str, tuple[str, int]] = {}      # task_id → (chat_id, message_id)

HEAD = {CREATED: "🕓", RUNNING: "⚙️", WAITING: "⏸", COMPLETED: "✅", FAILED: "⚠️"}


def _url(method: str) -> str:
    return f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN', '')}/{method}"


async def start(task_id: str, chat_id: str, title: str) -> None:
    """Первое сообщение задачи. Дальше оно только редактируется."""
    if not chat_id or not os.getenv("TELEGRAM_BOT_TOKEN"):
        return
    text = f"⚙️ <b>{title}</b>\n⏳ 1/{len(PLAN)} {PLAN[0]}"
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(_url("sendMessage"),
                             json={"chat_id": chat_id, "text": text,
                                   "parse_mode": "HTML",
                                   "disable_web_page_preview": True})
            data = r.json()
        if data.get("ok"):
            _messages[task_id] = (str(chat_id), data["result"]["message_id"])
    except Exception:
        pass


async def step(task_id: str, action: str, ok: bool = True, error: str = "") -> None:
    """Шаг задачи. Перерисовку делает сам `add_step` — здесь только запись."""
    await add_step(task_id, action, ok=ok, error=error)


async def finish(task_id: str, ok: bool, note: str = "") -> None:
    await _redraw(task_id, final=(COMPLETED if ok else FAILED), note=note)
    _messages.pop(task_id, None)


async def _redraw(task_id: str, final: str = "", note: str = "") -> None:
    place = _messages.get(task_id)
    if not place:
        return
    chat_id, message_id = place

    from core.task_manager import get
    task = await get(task_id)
    if not task:
        return

    steps = task.get("steps") or []
    total = max(len(PLAN), len(steps))
    lines = [f"{HEAD.get(final or task.get('status'), '⚙️')} "
             f"<b>{task.get('goal') or task.get('kind')}</b>"]

    from core.errors import human
    for i, s in enumerate(steps[-8:], start=max(1, len(steps) - 7)):
        mark = "✅" if s.get("ok") else "⚠️"
        line = f"{mark} {i}/{total} {s.get('action', '')}"
        if not s.get("ok") and s.get("error"):
            line += f"\n    {human(s['error'])}"
        lines.append(line)

    if not final and len(steps) < total:
        lines.append(f"⏳ {len(steps) + 1}/{total} {PLAN[min(len(steps), len(PLAN) - 1)]}")
    if note:
        lines.append(f"\n{note}")

    try:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(_url("editMessageText"),
                         json={"chat_id": chat_id, "message_id": message_id,
                               "text": "\n".join(lines)[:4000], "parse_mode": "HTML",
                               "disable_web_page_preview": True})
    except Exception:
        pass


def watching(task_id: str) -> bool:
    return task_id in _messages
