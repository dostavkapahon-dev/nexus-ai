"""
Очередь производственных заданий: ТЗ уходит исполнителю, готовое медиа возвращается.

Зачем это нужно. Ролик собирает конвейер (`core/content_factory.py`), но само
видео может делать не сервер. Рабочий доступ к Higgsfield есть у Claude Code —
логичнее отдать ему готовое ТЗ и принять обратно ссылки на файлы, чем гадать,
совпадают ли эндпоинты серверной интеграции с настоящим API.

Между «отдали ТЗ» и «приняли результат» проходит время: минуты на генерацию,
возможен перезапуск инстанса. Поэтому задание живёт в БД, а не в памяти.

Кто делает видео, решает настройка `producer`:
  * `server` — как раньше, сервер сам зовёт HeyGen/HiggsField/Runway;
  * `claude` — конвейер кладёт ТЗ сюда и ждёт исполнителя.
"""
import asyncio
import json
from datetime import datetime

from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import Connection, ProductionJob

# Выдача задания — «прочитать и сразу пометить». Между этими действиями нельзя
# пускать второй запрос, иначе одно ТЗ уйдёт двум исполнителям и ролик сделают
# дважды. FOR UPDATE подошёл бы для Postgres, но SQLite его не знает, а замок
# в процессе закрывает реальный случай: исполнитель у нас один.
_claim_lock = asyncio.Lock()

QUEUED, TAKEN = "queued", "taken"
DONE, FAILED, CANCELLED = "done", "failed", "cancelled"

PRODUCER_KEY = "content_producer"
SERVER, CLAUDE = "server", "claude"


# ─────────────────────────── кто делает видео ───────────────────────────

async def producer() -> str:
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == PRODUCER_KEY))
        c = r.scalar_one_or_none()
    value = (c.key_value or "").strip().lower() if c else ""
    return value if value in (SERVER, CLAUDE) else SERVER


async def set_producer(value: str) -> dict:
    value = (value or "").strip().lower()
    if value not in (SERVER, CLAUDE):
        return {"ok": False, "error": f"режим должен быть {SERVER} или {CLAUDE}"}
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == PRODUCER_KEY))
        c = r.scalar_one_or_none()
        if c:
            c.key_value = value
        else:
            db.add(Connection(key_name=PRODUCER_KEY, key_value=value))
        await db.commit()
    return {"ok": True, "producer": value}


# ─────────────────────────── очередь ───────────────────────────

def _as_dict(j: ProductionJob) -> dict:
    return {
        "id": j.id, "kind": j.kind, "status": j.status,
        "brief": j.brief or {}, "assets": j.assets or {}, "note": j.note or "",
        "error": j.error, "plan_id": j.plan_id or "", "task_id": j.task_id or "",
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "taken_at": j.taken_at.isoformat() if j.taken_at else None,
        "done_at": j.done_at.isoformat() if j.done_at else None,
    }


async def enqueue(brief: dict, kind: str = "reel", plan_id: str = "",
                  task_id: str = "") -> dict:
    """Ставит ТЗ в очередь и возвращает задание целиком."""
    async with AsyncSessionLocal() as db:
        job = ProductionJob(kind=kind or "reel", status=QUEUED, brief=brief or {},
                            plan_id=plan_id or "", task_id=task_id or "")
        db.add(job)
        await db.flush()
        out = _as_dict(job)
        await db.commit()
    return out


async def claim() -> dict | None:
    """Выдаёт исполнителю следующее ТЗ и сразу помечает его взятым.

    Пометка ставится в той же транзакции: иначе два запроса подряд получили бы
    одно и то же задание и ролик сделали бы дважды.
    """
    async with _claim_lock:
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(ProductionJob)
                                 .where(ProductionJob.status == QUEUED)
                                 .order_by(ProductionJob.created_at.asc())
                                 .limit(1))
            job = r.scalar_one_or_none()
            if not job:
                return None
            job.status = TAKEN
            job.taken_at = datetime.utcnow()
            out = _as_dict(job)
            await db.commit()
    return out


async def submit(job_id: str, assets: dict, note: str = "") -> dict:
    """Принимает готовое медиа от исполнителя."""
    assets = {k: v for k, v in (assets or {}).items() if v}
    if not assets:
        return {"ok": False, "error": "не переданы ссылки на готовые файлы"}

    async with AsyncSessionLocal() as db:
        r = await db.execute(select(ProductionJob).where(ProductionJob.id == job_id))
        job = r.scalar_one_or_none()
        if not job:
            return {"ok": False, "error": "задание не найдено"}
        if job.status in (DONE, CANCELLED):
            return {"ok": False, "error": f"задание уже {job.status}"}
        job.status = DONE
        job.assets = assets
        job.note = (note or "")[:2000]
        job.error = None
        job.done_at = datetime.utcnow()
        out = _as_dict(job)
        await db.commit()
    return {"ok": True, "job": out}


async def fail(job_id: str, error: str) -> dict:
    """Исполнитель не смог. Задание не теряется, причина видна."""
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(ProductionJob).where(ProductionJob.id == job_id))
        job = r.scalar_one_or_none()
        if not job:
            return {"ok": False, "error": "задание не найдено"}
        job.status = FAILED
        job.error = (error or "причина не указана")[:1000]
        job.done_at = datetime.utcnow()
        out = _as_dict(job)
        await db.commit()
    return {"ok": True, "job": out}


async def retry(job_id: str) -> dict:
    """Вернуть задание в очередь — например, если исполнитель взял и пропал."""
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(ProductionJob).where(ProductionJob.id == job_id))
        job = r.scalar_one_or_none()
        if not job:
            return {"ok": False, "error": "задание не найдено"}
        if job.status == DONE:
            return {"ok": False, "error": "задание уже выполнено"}
        job.status = QUEUED
        job.taken_at = None
        job.error = None
        out = _as_dict(job)
        await db.commit()
    return {"ok": True, "job": out}


async def cancel(job_id: str) -> dict:
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(ProductionJob).where(ProductionJob.id == job_id))
        job = r.scalar_one_or_none()
        if not job:
            return {"ok": False, "error": "задание не найдено"}
        if job.status == DONE:
            return {"ok": False, "error": "выполненное задание отменить нельзя"}
        job.status = CANCELLED
        out = _as_dict(job)
        await db.commit()
    return {"ok": True, "job": out}


async def get(job_id: str) -> dict | None:
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(ProductionJob).where(ProductionJob.id == job_id))
        job = r.scalar_one_or_none()
        return _as_dict(job) if job else None


async def jobs(status: str = "", limit: int = 50) -> list[dict]:
    async with AsyncSessionLocal() as db:
        q = select(ProductionJob).order_by(ProductionJob.created_at.desc()).limit(limit)
        if status:
            q = q.where(ProductionJob.status == status)
        r = await db.execute(q)
        return [_as_dict(j) for j in r.scalars()]


async def stats() -> dict:
    from sqlalchemy import func
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(ProductionJob.status, func.count(ProductionJob.id))
                             .group_by(ProductionJob.status))
        return {s or "—": int(n) for s, n in r.all()}


def brief_as_text(brief: dict) -> str:
    """ТЗ человеческим языком — его читает исполнитель и видит пользователь.

    Модель отдаёт бриф структурой; сырой JSON в чате нечитаем, а исполнителю
    нужны именно кадры и промпты, а не служебные поля.
    """
    brief = brief or {}
    # Текстовое задание для Клода описывается иначе, чем ролик: у него вопрос,
    # а не раскадровка.
    if brief.get("prompt") and not brief.get("storyboard"):
        from core.ai_escrow import as_text
        return as_text(brief)
    lines = []
    if brief.get("theme"):
        lines.append(f"Тема: {brief['theme']}")
    if brief.get("hook_text"):
        lines.append(f"Хук: {brief['hook_text']}")
    if brief.get("tone"):
        lines.append(f"Тон: {brief['tone']}")
    if brief.get("cover_prompt"):
        lines.append(f"Обложка: {brief['cover_prompt']}")
    if brief.get("video_motion_prompt"):
        lines.append(f"Движение камеры: {brief['video_motion_prompt']}")
    if brief.get("avatar_script"):
        lines.append(f"Текст озвучки: {brief['avatar_script']}")

    shots = brief.get("storyboard") or []
    if shots:
        lines.append("\nРаскадровка:")
        for i, shot in enumerate(shots, 1):
            t = shot.get("t") or f"кадр {i}"
            lines.append(f"  {t} — {shot.get('overlay', '')}")
            if shot.get("image_prompt"):
                lines.append(f"      промпт: {shot['image_prompt']}")

    extra = {k: v for k, v in brief.items()
             if k not in ("theme", "hook_text", "tone", "cover_prompt",
                          "video_motion_prompt", "avatar_script", "storyboard")
             and v and not k.startswith("_")}
    if extra:
        lines.append("\nПрочее: " + json.dumps(extra, ensure_ascii=False)[:500])
    return "\n".join(lines)
