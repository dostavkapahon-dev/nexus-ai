"""
Согласование контента перед публикацией.

Поток: сгенерированный пост/ролик → отправляется в Telegram админу с превью и
кнопками [✅ Опубликовать] [✏️ Правки] [❌ Отклонить]. На «Правки» админ пишет
текстом что поправить → контент перегенерируется и снова уходит на согласование.
На «Опубликовать» → публикуется во все площадки.

Очередь ожидающих хранится в таблице Connection (ключ moderation_queue, JSON) —
без миграций схемы.
"""
import os
import json
import uuid
from sqlalchemy import select
from database.db import AsyncSessionLocal
from database.models import Connection

QUEUE_KEY = "moderation_queue"     # {pid: {text, media_url, platforms, kind, ref}}
PENDING_FIX_KEY = "pending_fix"    # pid, для которого админ сейчас пишет правки


async def _load(db, key: str) -> dict:
    r = await db.execute(select(Connection).where(Connection.key_name == key))
    c = r.scalar_one_or_none()
    if c and c.key_value:
        try:
            return json.loads(c.key_value)
        except Exception:
            return {}
    return {}


async def _save(db, key: str, value):
    r = await db.execute(select(Connection).where(Connection.key_name == key))
    c = r.scalar_one_or_none()
    payload = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    if c:
        c.key_value = payload
    else:
        db.add(Connection(key_name=key, key_value=payload))
    await db.commit()


async def _tg(method: str, payload: dict):
    """Вызов Telegram. Неудача поднимается наверх, а не проглатывается.

    Раньше здесь стоял `except Exception: pass`, и ответ Telegram даже не
    читался. Поэтому «✅ ролик отправлен в Telegram на согласование» писалось и
    тогда, когда Telegram отказался: не та ссылка на картинку, не тот чат,
    слишком большой файл. Человек видел зелёную галочку и пустой чат — ровно
    та ложь, от которой уходим.
    """
    import httpx
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан — отправлять нечем")
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"https://api.telegram.org/bot{token}/{method}",
                         json=payload)
    try:
        data = r.json()
    except Exception:
        data = {}
    if r.status_code >= 400 or not data.get("ok", r.status_code < 400):
        raise RuntimeError(
            f"Telegram отклонил {method}: "
            f"{data.get('description') or r.text[:200] or r.status_code}")
    return data


def _kb(pid: str) -> dict:
    return {"inline_keyboard": [
        [{"text": "✅ Опубликовать", "callback_data": f"pub_{pid}"},
         {"text": "✏️ Правки", "callback_data": f"fix_{pid}"}],
        [{"text": "🔍 Разбор визуала", "callback_data": f"see_{pid}"},
         {"text": "❌ Отклонить", "callback_data": f"rej_{pid}"}],
    ]}


async def analyze_media_for(pid: str) -> str:
    """Разбирает визуал (картинку/ролик) элемента на согласовании через vision."""
    async with AsyncSessionLocal() as db:
        item = await _get_item(db, pid)
    if not item:
        return "❌ Элемент не найден"
    media = item.get("media_url")
    if not media:
        return "❌ У этого поста нет медиа для разбора"
    from core.vision import analyze_media
    res = await analyze_media(media)
    if res.get("ok"):
        return "🔍 <b>Разбор визуала</b>\n\n" + res["analysis"]
    return f"⚠️ {res.get('error')}"


async def send_for_approval(text: str, media_url: str = None, platforms: list = None,
                            kind: str = "plan", ref: str = None) -> str | None:
    """Кладёт контент в очередь и шлёт админу превью с кнопками. Возвращает pid."""
    # Владельца берём и из закрепления первым /start: без TELEGRAM_CHAT_ID
    # согласование молча уходило в никуда, а шаг оставался зелёным.
    admin = os.getenv("TELEGRAM_CHAT_ID", "")
    if not admin:
        try:
            from core.telegram_owner import owner_id
            admin = await owner_id()
        except Exception:
            admin = ""
    if not admin:
        raise RuntimeError("некому отправлять согласование: не задан "
                           "TELEGRAM_CHAT_ID и бот не знает владельца")

    pid = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        queue = await _load(db, QUEUE_KEY)
        queue[pid] = {"text": text, "media_url": media_url,
                      "platforms": platforms or ["instagram"], "kind": kind, "ref": ref}
        await _save(db, QUEUE_KEY, queue)

    # Называем, ЧТО именно отправлено. «Ролик» при отправленной картинке —
    # это обещание, которого в чате не окажется, и человек ищет несуществующее.
    is_video = bool(media_url) and str(media_url).lower().endswith(
        (".mp4", ".mov", ".webm"))
    head = ("🆕 <b>На согласование — ролик</b>" if is_video else
            "🆕 <b>На согласование — кадр</b>" if media_url else
            "🆕 <b>На согласование — только текст</b>")
    caption = (head + "\n\n" + (text or ""))[:1024]
    kb = _kb(pid)
    if is_video:
        await _tg("sendVideo", {"chat_id": admin, "video": media_url,
                                "caption": caption, "parse_mode": "HTML", "reply_markup": kb})
    elif media_url:
        try:
            await _tg("sendPhoto", {"chat_id": admin, "photo": media_url,
                                    "caption": caption, "parse_mode": "HTML",
                                    "reply_markup": kb})
        except Exception as e:
            # Файл создан и сохранён — терять его из-за отказа доставки нельзя
            # (§29). Отдаём ссылкой и честно говорим, что картинка не прошла.
            await _tg("sendMessage", {
                "chat_id": admin,
                "text": f"{caption}\n\n🔗 {media_url}\n"
                        f"<i>Картинку чат не принял: {str(e)[:150]}</i>",
                "parse_mode": "HTML", "reply_markup": kb})
    else:
        await _tg("sendMessage", {"chat_id": admin, "text": caption,
                                  "parse_mode": "HTML", "reply_markup": kb})
    return pid


async def _get_item(db, pid: str) -> dict | None:
    queue = await _load(db, QUEUE_KEY)
    return queue.get(pid)


async def _remove(db, pid: str):
    queue = await _load(db, QUEUE_KEY)
    if pid in queue:
        queue.pop(pid)
        await _save(db, QUEUE_KEY, queue)


async def approve(pid: str) -> str:
    """Публикует согласованный контент во все его площадки."""
    from core.orchestrator import nexus_core
    async with AsyncSessionLocal() as db:
        item = await _get_item(db, pid)
        if not item:
            return "❌ Элемент не найден или уже обработан"
        results = []
        for pf in item.get("platforms", ["instagram"]):
            try:
                r = await nexus_core._publish_one(pf, item.get("text", ""), item.get("media_url") or "")
                results.append(f"{'✅' if r.get('ok') else '❌'} {pf}" + ("" if r.get("ok") else f": {str(r.get('error'))[:60]}"))
            except Exception as e:
                results.append(f"❌ {pf}: {str(e)[:60]}")
        # Отметим план опубликованным.
        if item.get("kind") == "plan" and item.get("ref"):
            from database.models import ContentPlan
            pr = await db.execute(select(ContentPlan).where(ContentPlan.id == item["ref"]))
            p = pr.scalar_one_or_none()
            if p:
                p.status = "published"
                await db.commit()
        await _remove(db, pid)
    return "📤 <b>Опубликовано</b>\n" + "\n".join(results)


async def reject(pid: str) -> str:
    async with AsyncSessionLocal() as db:
        await _remove(db, pid)
    return "❌ Отклонено, публиковать не буду."


async def request_fix(pid: str) -> str:
    """Помечает, что админ сейчас будет писать правки для pid."""
    async with AsyncSessionLocal() as db:
        item = await _get_item(db, pid)
        if not item:
            return "❌ Элемент не найден"
        await _save(db, PENDING_FIX_KEY, pid)
    return "✏️ Напиши одним сообщением, что поправить — я перегенерирую и снова пришлю на согласование."


async def pending_fix_id(db) -> str | None:
    r = await db.execute(select(Connection).where(Connection.key_name == PENDING_FIX_KEY))
    c = r.scalar_one_or_none()
    return (c.key_value or None) if c else None


async def apply_fix(correction: str) -> str:
    """Применяет текстовые правки к ожидающему элементу и снова шлёт на согласование."""
    async with AsyncSessionLocal() as db:
        pid = await pending_fix_id(db)
        if not pid:
            return ""
        item = await _get_item(db, pid)
        await _save(db, PENDING_FIX_KEY, "")  # снимаем флаг
        if not item:
            return "❌ Элемент устарел"
        await _remove(db, pid)

    kind = item.get("kind", "plan")
    ref = item.get("ref")
    if kind == "plan" and ref:
        from core.orchestrator import nexus_core
        await nexus_core.generate_content_for_plan(ref, corrections=correction)
        return "🔄 Перегенерировал с правками — прислал новую версию на согласование."
    # kind == factory или без ref: правим текст напрямую и снова на согласование
    new_text = (item.get("text", "") + f"\n\n[Правки: {correction}]")
    await send_for_approval(new_text, media_url=item.get("media_url"),
                            platforms=item.get("platforms"), kind=kind, ref=ref)
    return "🔄 Обновил с учётом правок — на согласовании."
