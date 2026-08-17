"""
Последнее звено цепочки моделей: если не ответил никто — отвечает Клод.

Перебор в `core/ai_router` идёт по всем провайдерам с ключами (шесть бесплатных,
затем платные). Когда не отвечает ни один — раньше запрос человека просто
пропадал с текстом «ни один ИИ-провайдер не подключён». Здесь он вместо этого
кладётся в общую очередь заданий (`ProductionJob`, kind `ai_task`), уходит
владельцу в Telegram и ждёт ответа Клода из аккаунта Claude Code.

Два ограничителя, чтобы очередь не залило:
  * только запросы, начатые человеком (см. `interactive`) — фоновые шаги
    конвейера падают как раньше, иначе один прогон фабрики породит десяток
    заданий, которые придётся разбирать вручную;
  * одинаковый вопрос не ставится в очередь дважды в течение часа.
"""
import hashlib
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta

KIND = "ai_task"
_WINDOW = timedelta(hours=1)      # окно дедупликации одинаковых вопросов

# Запрос начат человеком (Telegram, командный центр, кнопка в вебе).
_interactive: ContextVar[bool] = ContextVar("ai_interactive", default=False)
_where: ContextVar[dict] = ContextVar("ai_where", default={})


def interactive(source: str = "web", chat_id: str = ""):
    """Пометить текущий запрос как «его ждёт человек» и запомнить, куда отвечать."""
    _interactive.set(True)
    _where.set({"source": source, "chat_id": str(chat_id or "")})


def reset():
    """Снять пометку. Нужно там, где один процесс обслуживает и запросы людей,
    и фоновую работу: иначе фоновый сбой уедет в очередь к Клоду как «его ждут»."""
    _interactive.set(False)
    _where.set({})


@contextmanager
def suppressed():
    """Служебный вызов внутри запроса человека: его в очередь отдавать нельзя.

    Самопроверки, выбор формата, разметка — вещи на секунду работы модели. Гнать
    такое через ручную пересылку бессмысленно: человек потратит минуты на то, что
    конвейер должен пропустить и пойти дальше.
    """
    was, where = _interactive.get(), _where.get()
    _interactive.set(False)
    try:
        yield
    finally:
        _interactive.set(was)
        _where.set(where)


def wanted() -> bool:
    return bool(_interactive.get())


def _digest(system: str, prompt: str) -> str:
    return hashlib.sha256(f"{system}\n{prompt}".encode("utf-8")).hexdigest()[:16]


WAIT_TEXT = (
    "🧠 Ни одна подключённая модель сейчас не ответила, поэтому запрос ушёл "
    "Клоду в аккаунт Claude Code. Ответ придёт сюда же, как только он его даст."
)


async def ask(system: str, prompt: str, role: str = "", errors: str = "") -> str:
    """Кладёт запрос в очередь для Клода. Возвращает текст для того, кто ждёт."""
    from core import production_queue as pq

    place = _where.get() or {}
    digest = _digest(system, prompt)

    # Тот же вопрос уже ждёт ответа — второй раз не заводим.
    since = datetime.utcnow() - _WINDOW
    for j in await pq.jobs(limit=50):
        if j.get("kind") != KIND:
            continue
        if (j.get("brief") or {}).get("digest") != digest:
            continue
        if j.get("status") in (pq.QUEUED, pq.TAKEN):
            return WAIT_TEXT
        done = j.get("done_at") or ""
        if done and datetime.fromisoformat(done) > since:
            return WAIT_TEXT

    brief = {"digest": digest, "system": system, "prompt": prompt, "role": role,
             "source": place.get("source", "web"), "chat_id": place.get("chat_id", ""),
             "why": errors[:400]}
    job = await pq.enqueue(brief, kind=KIND)

    await _tell_owner(job, prompt)
    return WAIT_TEXT


async def _tell_owner(job: dict, prompt: str):
    """Владелец должен узнать сразу: иначе задание будет ждать вечно."""
    try:
        from core.notify import notify_owner
        await notify_owner(
            "🧠 <b>Нужен Клод</b> — свои модели не ответили.\n\n"
            f"<b>Вопрос:</b> {prompt[:600]}\n\n"
            f"Задание <code>{job['id'][:8]}</code> — на вкладке «Производство». "
            "Перешлите вопрос Клоду и вставьте ответ формой.")
    except Exception:
        pass


def as_text(brief: dict) -> str:
    """Задание словами — его пересылают Клоду целиком."""
    b = brief or {}
    parts = []
    if b.get("system"):
        parts.append(f"Роль: {b['system']}")
    parts.append(f"Вопрос: {b.get('prompt', '')}")
    if b.get("why"):
        parts.append(f"(свои модели отказали: {b['why']})")
    return "\n\n".join(parts)


async def deliver(job: dict) -> dict:
    """Отдаёт ответ Клода тому, кто спрашивал: в Telegram и в общую ленту."""
    brief = job.get("brief") or {}
    text = (job.get("assets") or {}).get("text") or ""
    if not text:
        return {"status": "empty", "note": "ответ пустой — доставлять нечего"}

    delivered = []
    chat_id = brief.get("chat_id")
    try:
        if chat_id:
            from core.telegram_bot import send_message
            await send_message(str(chat_id), f"🧠 <b>Ответ Клода</b>\n\n{text}")
            delivered.append("telegram")
        else:
            from core.notify import notify_owner
            if await notify_owner(f"🧠 Ответ Клода\n\n{text}"):
                delivered.append("telegram")
    except Exception as e:
        return {"status": "error", "note": str(e)[:160]}

    # Лента — это то, что видно на сайте: ответ должен быть и там.
    try:
        from core.command_center import log_event
        await log_event(brief.get("source") or "web", "agent", text)
        delivered.append("feed")
    except Exception:
        pass

    return {"status": "delivered", "to": delivered}
