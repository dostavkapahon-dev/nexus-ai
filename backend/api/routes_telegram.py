"""
Подключение Telegram-канала и публикация в него.

Один и тот же слой команд обслуживает и веб, и самого бота: страница
«Подключения → Telegram → Добавить канал» ходит сюда же, куда ходит ядро,
когда публикует пост. Поэтому канал, подключённый в вебе, сразу работает в
Telegram, и наоборот.

Защищено auth на уровне main.py.
"""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


# ─────────────────────────── подключение ───────────────────────────

class TokenBody(BaseModel):
    token: str | None = None          # можно проверить токен до сохранения


@router.get("/status")
async def status():
    """Сводка: бот, подключённые каналы, канал по умолчанию."""
    from core.telegram_channels import status as tg_status
    return await tg_status()


@router.post("/bot/check")
async def bot_check(body: TokenBody):
    """Шаг 1 — подключение бота: жив ли токен."""
    from core.telegram_channels import bot_info
    return await bot_info(body.token or "")


class SaveBotBody(BaseModel):
    token: str


@router.post("/bot/connect")
async def bot_connect(body: SaveBotBody):
    """Сохраняет токен бота, но только если Telegram его принял: иначе в системе
    оседает нерабочий ключ, а ошибка всплывает при первой публикации."""
    from core.telegram_channels import bot_info, _persist_env
    import os

    token = (body.token or "").strip()
    info = await bot_info(token)
    if not info.get("ok"):
        return info
    os.environ["TELEGRAM_BOT_TOKEN"] = token
    await _persist_env("telegram_bot_token", token)
    # Цикл бота перечитывает токен сам, но список команд и снятие вебхука —
    # разовые действия: без них меню в клиенте пустое, а polling ловит 409.
    try:
        from core.telegram_bot import setup_bot_commands
        await setup_bot_commands()
    except Exception:
        pass
    return {**info, "saved": True, "polling": "запустится в течение 10 секунд"}


@router.get("/channels")
async def channels():
    from core.telegram_channels import list_channels, default_channel
    return {"items": await list_channels(), "default": await default_channel()}


@router.get("/channels/discover")
async def channels_discover():
    """Шаг 2 — выбор канала: какие каналы бот уже видит."""
    from core.telegram_channels import discover
    return await discover()


class ChannelBody(BaseModel):
    chat_id: str


@router.post("/channels/check")
async def channels_check(body: ChannelBody):
    """Шаги 3–4 — проверка прав и возможности публикации."""
    from core.telegram_channels import check_channel
    return await check_channel(body.chat_id)


class TestBody(BaseModel):
    chat_id: str
    keep: bool = False               # оставить тестовое сообщение в канале


@router.post("/channels/test")
async def channels_test(body: TestBody):
    """Шаг 5 — тестовая публикация (по умолчанию удаляется)."""
    from core.telegram_channels import test_publish
    return await test_publish(body.chat_id, keep=body.keep)


@router.post("/channels/add")
async def channels_add(body: ChannelBody):
    """Сохранить канал как подключённый (после успешных проверок)."""
    from core.telegram_channels import add_channel
    return await add_channel(body.chat_id)


@router.post("/channels/default")
async def channels_default(body: ChannelBody):
    from core.telegram_channels import set_default
    return await set_default(body.chat_id)


@router.post("/channels/remove")
async def channels_remove(body: ChannelBody):
    from core.telegram_channels import remove_channel
    return await remove_channel(body.chat_id)


# ─────────────────────────── публикация ───────────────────────────

class PublishBody(BaseModel):
    text: str = ""
    image_url: str | None = None
    video_url: str | None = None
    images: list[str] | None = None          # несколько картинок — уйдут альбомом
    buttons: list[dict] | None = None        # [{"text": "...", "url": "https://..."}]
    chat_id: str | None = None               # пусто — канал по умолчанию
    when: str | None = None                  # ISO-время UTC: пусто — сразу
    silent: bool = False


async def _resolve_chat(chat_id: str | None) -> str:
    from core.telegram_channels import default_channel
    return (chat_id or "").strip() or await default_channel()


@router.post("/publish")
async def publish(body: PublishBody):
    """Публикация поста: текст, картинка или видео. С `when` — планирование.

    Планирование идёт через общую очередь публикаций, а не через свой таймер:
    иначе запланированное из Telegram не было бы видно на сайте.
    """
    from publishers import telegram_pub as tg
    from core.command_center import log_event

    chat = await _resolve_chat(body.chat_id)
    if not chat:
        return {"ok": False, "error": "канал не подключён — Подключения → Telegram"}

    if body.when:
        from datetime import datetime
        from core.publish_queue import enqueue
        try:
            when = datetime.fromisoformat(body.when.replace("Z", ""))
        except ValueError:
            return {"ok": False, "error": "when: ожидается ISO-время, например 2026-08-20T19:00"}
        pub_id = await enqueue("telegram", body.text or "", body.image_url or "",
                               video_url=body.video_url or "", when=when, approved=True)
        await log_event("web", "agent", f"📅 Telegram: публикация запланирована на {body.when}")
        return {"ok": True, "publication_id": pub_id, "status": "scheduled",
                "scheduled_at": when.isoformat()}

    images = [u for u in (body.images or []) if u]
    if len(images) > 1:
        # Набор картинок одним сообщением: раньше их пришлось бы слать по одной,
        # и в канале это выглядело как несколько отдельных постов.
        res = await tg.send_album(chat, images, body.text or "", silent=body.silent)
    elif body.video_url:
        res = await tg.send_video(chat, body.video_url, body.text or "",
                                  silent=body.silent, buttons=body.buttons)
    elif body.image_url or images:
        res = await tg.send_photo(chat, body.image_url or images[0], body.text or "",
                                  silent=body.silent, buttons=body.buttons)
    else:
        res = await tg.send_message(chat, body.text or "", silent=body.silent,
                                    buttons=body.buttons)

    # Публикация видна и на сайте, и в ленте бота — обе «головы» смотрят в одну
    # ленту. Провал записывается тоже: раньше неудачная публикация из веба
    # нигде не оставляла следа, и на сайте её просто не существовало.
    await _record(chat, body, res)
    if res.get("ok"):
        note = " (текст сокращён)" if res.get("truncated") else ""
        await log_event("web", "agent",
                        f"📢 Telegram: опубликовано ({res.get('message_id')}){note}")
    else:
        await log_event("web", "agent",
                        f"⚠️ Telegram: публикация не прошла — {res.get('error')}")
    return res


async def _record(chat: str, body: PublishBody, res: dict):
    """Запись факта публикации — и удачной, и нет: сайт должен показывать обе."""
    from datetime import datetime
    from database.db import AsyncSessionLocal
    from database.models import Publication
    from core.publish_queue import PUBLISHED, BLOCKED, FAILED

    ok = bool(res.get("ok"))
    if ok:
        status = PUBLISHED
    else:
        status = BLOCKED if res.get("blocked_by_api") else FAILED
    async with AsyncSessionLocal() as db:
        db.add(Publication(
            platform="telegram", status=status,
            published_at=datetime.utcnow() if ok else None,
            external_id=str(res.get("message_id") or ""), post_url=res.get("post_url") or "",
            text=body.text or "", image_url=body.image_url or "",
            video_url=body.video_url or "", topic=(body.text or "")[:300],
            last_error=None if ok else str(res.get("error") or "")[:500],
            attempts=1, scheduled_at=datetime.utcnow()))
        await db.commit()


class MessageBody(BaseModel):
    text: str
    chat_id: str | None = None


@router.post("/message")
async def message(body: MessageBody):
    """Служебное сообщение (не пост): уведомление в личку или в канал."""
    import os
    from publishers import telegram_pub as tg
    chat = (body.chat_id or "").strip() or os.getenv("TELEGRAM_CHAT_ID", "").strip() \
        or await _resolve_chat(None)
    if not chat:
        return {"ok": False, "error": "не задан получатель"}
    return await tg.send_message(chat, body.text)


@router.get("/publication/{pub_id}")
async def publication_status(pub_id: str):
    """Статус публикации: что с ней сейчас и почему."""
    from sqlalchemy import select
    from database.db import AsyncSessionLocal
    from database.models import Publication
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Publication).where(Publication.id == pub_id))
        p = r.scalar_one_or_none()
    if not p:
        return {"ok": False, "error": "публикация не найдена"}
    return {"ok": True, "id": p.id, "platform": p.platform, "status": p.status,
            "attempts": int(p.attempts or 0), "error": p.last_error,
            "post_url": p.post_url, "external_id": p.external_id,
            "scheduled_at": p.scheduled_at.isoformat() if p.scheduled_at else None,
            "published_at": p.published_at.isoformat() if p.published_at else None}
