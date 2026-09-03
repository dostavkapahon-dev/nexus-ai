"""
Очередь публикаций с повторами.

Раньше публикация была одноразовой: `_publish_one` вызывался, и если площадка
ответила таймаутом или 502, пост просто терялся — в `Publication` оставалась
строка `failed` без текста, повторить её было нечем. Теперь состояние публикации
живёт в БД целиком (текст, картинка, попытки, время следующей попытки), поэтому
очередь переживает рестарт инстанса, а не умирает вместе с процессом.

Ключевое различие — временный сбой и отказ по существу:
  * сеть, таймаут, 5xx, rate limit → повторяем с растущей паузой;
  * `blocked_by_api`, «не настроено», отклонённый контент → повторять бессмысленно,
    статус `blocked`/`failed` сразу, чтобы очередь не долбила площадку впустую.
"""
import os
from datetime import datetime, timedelta

from sqlalchemy import select, or_

from database.db import AsyncSessionLocal
from database.models import Publication

SCHEDULED, RETRYING = "scheduled", "retrying"
PUBLISHED, FAILED = "published", "failed"
BLOCKED, CANCELLED = "blocked", "cancelled"
# Пост подготовлен, но площадка стоит в режиме «с подтверждением»: он ждёт
# человека и не уходит наружу сам по себе.
PENDING = "pending_approval"

ACTIVE = (SCHEDULED, RETRYING)

# Пять попыток с паузами 2, 8, 30, 120 минут: сетевые сбои площадок обычно
# укладываются в этот интервал, а более частые повторы упираются в rate limit.
MAX_ATTEMPTS = int(os.getenv("PUBLISH_MAX_ATTEMPTS", "5"))
BACKOFF_MIN = (2, 8, 30, 120)

# Формулировки площадок, при которых повтор не имеет смысла.
_PERMANENT = ("не настроен", "not configured", "нет токена", "blocked_by_api",
              "invalid_token", "oauth", "permission", "unsupported", "не поддерж",
              # Отсутствие сценария или самого браузера не «пройдёт само»: повторять
              # это пять раз — впустую жечь время и мусорить в журнале.
              "нет браузерного сценария", "нет ни пк-агента")


def _is_permanent(res: dict) -> bool:
    """Отказ по существу (нет прав/токена/функции) — повторять нечего."""
    if res.get("blocked_by_api"):
        return True
    text = f"{res.get('error') or ''} {res.get('reason') or ''}".lower()
    return any(w in text for w in _PERMANENT)


def _backoff(attempts: int) -> timedelta:
    idx = min(max(attempts - 1, 0), len(BACKOFF_MIN) - 1)
    return timedelta(minutes=BACKOFF_MIN[idx])


async def enqueue(platform: str, text: str, image_url: str = "", *,
                  when: datetime | None = None, plan_id: str = "", niche_id: str = "",
                  topic: str = "", hook: str = "", content_format: str = "",
                  strategy_id: str = "", task_id: str = "", approved: bool = True,
                  video_url: str = "") -> str:
    """Ставит публикацию в очередь. `when=None` — как можно скорее.

    `approved` по умолчанию True: постановка в очередь — это обычно прямое
    решение человека (ручная публикация или подтверждение), и режим площадки её
    не задерживает. Автоматика (планировщик) ставит `approved=False`, и тогда
    площадка в режиме `confirm`/`manual` попадает в PENDING и ждёт человека.
    """
    from core.autopublish import may_autopublish
    status = SCHEDULED if approved or await may_autopublish(platform) else PENDING
    async with AsyncSessionLocal() as db:
        pub = Publication(
            plan_id=plan_id, niche_id=niche_id, platform=platform, status=status,
            scheduled_at=when or datetime.utcnow(), attempts=0,
            text=text or "", image_url=image_url or "", video_url=video_url or "",
            topic=(topic or "")[:300], hook=hook or "", content_format=content_format or "",
            strategy_id=strategy_id, task_id=task_id)
        db.add(pub)
        await db.flush()          # id проставляется на вставке — без flush читать рано
        pub_id = pub.id
        await db.commit()
    return pub_id


async def attempt(pub_id: str) -> dict:
    """Одна попытка публикации записи очереди. Итог всегда сохраняется в БД."""
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Publication).where(Publication.id == pub_id))
        pub = r.scalar_one_or_none()
        if not pub:
            return {"ok": False, "error": "запись очереди не найдена"}
        if pub.status not in ACTIVE:
            return {"ok": False, "error": f"статус {pub.status} — публиковать нечего"}
        platform, text, image_url = pub.platform, pub.text or "", pub.image_url or ""
        video_url = pub.video_url or ""
        attempts = int(pub.attempts or 0) + 1

    from core.orchestrator import nexus_core
    try:
        res = await nexus_core._publish_one(platform, text, image_url, video_url)
    except Exception as e:
        res = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}

    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Publication).where(Publication.id == pub_id))
        pub = r.scalar_one_or_none()
        if not pub:
            return res
        pub.attempts = attempts
        if res.get("ok"):
            pub.status = PUBLISHED
            pub.published_at = datetime.utcnow()
            pub.external_id = str(res.get("post_id") or "")
            pub.post_url = str(res.get("post_url") or "")
            pub.next_retry_at = None
            pub.last_error = None
        else:
            err = str(res.get("error") or res.get("reason") or "публикация не удалась")[:500]
            pub.last_error = err
            if _is_permanent(res):
                # Честный «нельзя», а не бесконечные повторы: причина видна в last_error.
                pub.status = BLOCKED
                pub.next_retry_at = None
            elif attempts >= MAX_ATTEMPTS:
                pub.status = FAILED
                pub.next_retry_at = None
            else:
                pub.status = RETRYING
                pub.next_retry_at = datetime.utcnow() + _backoff(attempts)
        status = pub.status
        await db.commit()
    return {**res, "publication_id": pub_id, "status": status, "attempts": attempts}


async def due(limit: int = 20) -> list[str]:
    """Записи, которым пора: время наступило (или не задано)."""
    now = datetime.utcnow()
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(Publication.id)
            .where(Publication.status.in_(ACTIVE))
            .where(or_(Publication.scheduled_at.is_(None), Publication.scheduled_at <= now))
            .where(or_(Publication.next_retry_at.is_(None), Publication.next_retry_at <= now))
            .order_by(Publication.scheduled_at.asc())
            .limit(limit))
        return [row[0] for row in r.all()]


async def process_due(limit: int = 20) -> dict:
    """Джоб очереди: публикует всё, чему пришло время. Один проход, без рекурсии."""
    ids = await due(limit)
    ok = failed = 0
    for pub_id in ids:
        res = await attempt(pub_id)
        if res.get("ok"):
            ok += 1
        else:
            failed += 1
    return {"picked": len(ids), "published": ok, "not_published": failed}


async def approve(pub_id: str) -> dict:
    """Подтверждение поста, ждавшего человека: запись возвращается в очередь.
    Публикуем сразу, если её время уже наступило."""
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Publication).where(Publication.id == pub_id))
        pub = r.scalar_one_or_none()
        if not pub:
            return {"ok": False, "error": "запись не найдена"}
        if pub.status != PENDING:
            return {"ok": False, "error": f"статус {pub.status} — подтверждать нечего"}
        pub.status = SCHEDULED
        when = pub.scheduled_at
        await db.commit()
    if when and when > datetime.utcnow():
        # Запланировано на будущее — подтверждение не должно ломать расписание.
        return {"ok": True, "publication_id": pub_id, "status": SCHEDULED,
                "scheduled_at": when.isoformat()}
    return await attempt(pub_id)


async def pending(limit: int = 50) -> list[dict]:
    """Что ждёт подтверждения — площадки в режиме «с подтверждением»."""
    return await queue(PENDING, limit)


async def retry_now(pub_id: str) -> dict:
    """Ручной повтор: снимает паузу и публикует сразу, даже у FAILED/BLOCKED."""
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Publication).where(Publication.id == pub_id))
        pub = r.scalar_one_or_none()
        if not pub:
            return {"ok": False, "error": "запись не найдена"}
        if pub.status == PUBLISHED:
            return {"ok": False, "error": "уже опубликовано"}
        pub.status = RETRYING
        pub.next_retry_at = None
        pub.scheduled_at = datetime.utcnow()
        await db.commit()
    return await attempt(pub_id)


async def cancel(pub_id: str) -> bool:
    """Снимает запись с очереди. Опубликованное отменить нельзя."""
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Publication).where(Publication.id == pub_id))
        pub = r.scalar_one_or_none()
        if not pub or pub.status not in ACTIVE:
            return False
        pub.status = CANCELLED
        pub.next_retry_at = None
        await db.commit()
    return True


async def queue(status: str = "", limit: int = 50) -> list[dict]:
    """Состояние очереди для дашборда и Telegram."""
    async with AsyncSessionLocal() as db:
        q = select(Publication).order_by(Publication.scheduled_at.desc().nullslast())
        if status:
            q = q.where(Publication.status == status)
        r = await db.execute(q.limit(limit))
        rows = r.scalars().all()
    return [{"id": p.id, "platform": p.platform, "status": p.status,
             "attempts": int(p.attempts or 0), "error": p.last_error,
             "scheduled_at": p.scheduled_at.isoformat() if p.scheduled_at else None,
             "next_retry_at": p.next_retry_at.isoformat() if p.next_retry_at else None,
             "post_url": p.post_url, "topic": p.topic,
             "text": (p.text or "")[:200]} for p in rows]


async def stats() -> dict:
    """Счётчики по статусам — на них смотрит дашборд и /publish в Telegram."""
    from sqlalchemy import func
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Publication.status, func.count(Publication.id))
                             .group_by(Publication.status))
        return {s or "—": int(n) for s, n in r.all()}
