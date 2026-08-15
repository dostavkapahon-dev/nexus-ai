"""
Очередь публикаций: что стоит в расписании, что упало и почему, ручной повтор.
Защищено auth на уровне main.py.
"""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/publish", tags=["publish"])


@router.get("/queue")
async def publish_queue(status: str = "", limit: int = 50):
    """Состояние очереди: статус, попытки, причина отказа, время следующей попытки."""
    from core.publish_queue import queue, stats
    return {"items": await queue(status, limit), "stats": await stats()}


class ScheduleBody(BaseModel):
    platform: str
    text: str
    image_url: str | None = None
    when: str | None = None          # ISO-время UTC; пусто — как можно скорее
    niche_id: str | None = None
    topic: str | None = None


@router.post("/schedule")
async def schedule(body: ScheduleBody):
    """Ставит публикацию в очередь на указанное время."""
    from datetime import datetime
    from core.publish_queue import enqueue

    when = None
    if body.when:
        try:
            when = datetime.fromisoformat(body.when.replace("Z", ""))
        except ValueError:
            return {"ok": False, "error": "when: ожидается ISO-время, например 2026-08-12T19:00"}

    pub_id = await enqueue(body.platform, body.text, body.image_url or "", when=when,
                           niche_id=body.niche_id or "", topic=body.topic or "")
    return {"ok": True, "publication_id": pub_id}


@router.get("/pending")
async def pending_list(limit: int = 50):
    """Что ждёт подтверждения — площадки в режиме «с подтверждением»."""
    from core.publish_queue import pending
    return {"items": await pending(limit)}


@router.post("/{pub_id}/approve")
async def approve(pub_id: str):
    """Подтвердить публикацию: она уходит в очередь и публикуется."""
    from core.publish_queue import approve as approve_pub
    return await approve_pub(pub_id)


# ─────────────────── режимы автопубликации по площадкам ───────────────────

class AutoBody(BaseModel):
    enabled: bool | None = None
    platforms: dict[str, str] | None = None   # {"telegram": "auto", "instagram": "confirm"}


@router.get("/auto")
async def auto_get():
    from core.autopublish import get_settings, MODES
    return {**await get_settings(), "modes": list(MODES)}


@router.post("/auto")
async def auto_set(body: AutoBody):
    """Общий выключатель и режим каждой площадки: manual | confirm | auto."""
    from core.autopublish import set_settings
    return await set_settings(body.enabled, body.platforms)


@router.post("/{pub_id}/retry")
async def retry(pub_id: str):
    """Повторить сейчас, не дожидаясь паузы. Работает и для FAILED/BLOCKED."""
    from core.publish_queue import retry_now
    return await retry_now(pub_id)


@router.post("/{pub_id}/cancel")
async def cancel(pub_id: str):
    """Снять запись с очереди."""
    from core.publish_queue import cancel as cancel_pub
    ok = await cancel_pub(pub_id)
    return {"ok": ok, "error": None if ok else "нельзя отменить: уже не в очереди"}


@router.post("/process")
async def process(limit: int = 20):
    """Разобрать очередь прямо сейчас (то же, что делает джоб каждые 10 минут)."""
    from core.publish_queue import process_due
    return await process_due(limit)
