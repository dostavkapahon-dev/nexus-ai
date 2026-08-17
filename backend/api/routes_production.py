"""
Производство медиа внешним исполнителем: выдача ТЗ и приём готовых файлов.

Сюда ходит Claude Code: забирает ТЗ (`/next`), генерирует ролик через Higgsfield
и HeyGen и возвращает ссылки (`/{id}/result`). Приём результата сам продолжает
конвейер — монтаж и согласование, — чтобы готовый ролик не лежал мёртвым грузом.

Защищено auth на уровне main.py.
"""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/production", tags=["production"])


@router.get("/next")
async def next_job():
    """Взять следующее ТЗ. Пусто — значит очередь пуста, это не ошибка."""
    from core.production_queue import claim, brief_as_text

    job = await claim()
    if not job:
        return {"ok": True, "job": None, "message": "очередь пуста"}
    return {"ok": True, "job": job, "brief_text": brief_as_text(job.get("brief"))}


@router.get("/jobs")
async def list_jobs(status: str = "", limit: int = 50):
    from core.production_queue import jobs, stats, producer, brief_as_text

    # ТЗ словами кладём прямо в список: исполнителю его надо переслать, а тянуть
    # ради текста `/next` нельзя — тот забирает задание себе.
    items = [{**j, "brief_text": brief_as_text(j.get("brief"))}
             for j in await jobs(status, limit)]
    return {"items": items, "stats": await stats(), "producer": await producer()}


@router.get("/jobs/{job_id}")
async def job_details(job_id: str):
    from core.production_queue import get, brief_as_text
    job = await get(job_id)
    if not job:
        return {"ok": False, "error": "задание не найдено"}
    return {"ok": True, "job": job, "brief_text": brief_as_text(job.get("brief"))}


class NewJobBody(BaseModel):
    brief: dict
    kind: str = "reel"
    plan_id: str = ""


@router.post("/jobs")
async def create_job(body: NewJobBody):
    """Создать ТЗ вручную — без запуска всего конвейера (проверка и разовые задачи)."""
    from core.production_queue import enqueue
    job = await enqueue(body.brief, body.kind, plan_id=body.plan_id)
    return {"ok": True, "job": job}


class ResultBody(BaseModel):
    video_url: str | None = None
    image_url: str | None = None
    audio_url: str | None = None
    cover_url: str | None = None
    text: str | None = None       # ответ Клода на текстовое задание (kind=ai_task)
    note: str = ""
    publish: bool = True          # продолжить конвейер: монтаж → согласование


@router.post("/{job_id}/result")
async def submit_result(job_id: str, body: ResultBody):
    """Принять готовое медиа и продолжить конвейер.

    Готовый ролик сам по себе бесполезен: дальше его надо смонтировать и
    показать владельцу. Поэтому приём результата сразу запускает продолжение,
    а не просто меняет статус в базе.
    """
    from core.production_queue import submit

    assets = {"video_url": body.video_url, "image_url": body.image_url,
              "audio_url": body.audio_url, "cover_url": body.cover_url,
              "text": body.text}
    res = await submit(job_id, assets, body.note)
    if not res.get("ok"):
        return res

    job = res["job"]
    if not body.publish:
        return {**res, "next": "остановлено по запросу: publish=false"}

    # Текстовое задание монтировать нечего — ответ уходит тому, кто спрашивал.
    from core import ai_escrow
    if job.get("kind") == ai_escrow.KIND:
        return {**res, "next": await ai_escrow.deliver(job)}

    from core.content_factory import finalize_from_assets
    outcome = await finalize_from_assets(job)
    return {**res, "next": outcome}


class FailBody(BaseModel):
    error: str


@router.post("/{job_id}/fail")
async def fail_job(job_id: str, body: FailBody):
    """Исполнитель не смог — причина сохраняется, владелец узнаёт."""
    from core.production_queue import fail
    from core.notify import notify_owner

    res = await fail(job_id, body.error)
    if res.get("ok"):
        await notify_owner(f"⚠️ Производство ролика не удалось: {body.error[:200]}\n"
                           f"Задание {job_id} можно вернуть в очередь.")
    return res


@router.post("/{job_id}/retry")
async def retry_job(job_id: str):
    from core.production_queue import retry
    return await retry(job_id)


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str):
    from core.production_queue import cancel
    return await cancel(job_id)


class ProducerBody(BaseModel):
    producer: str                 # server | claude


@router.post("/producer")
async def set_producer_mode(body: ProducerBody):
    """Кто делает видео: сервер сам или внешний исполнитель (Claude Code)."""
    from core.production_queue import set_producer
    return await set_producer(body.producer)
