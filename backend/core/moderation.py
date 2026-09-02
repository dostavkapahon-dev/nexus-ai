"""
Согласование контента перед публикацией.

Поток: сгенерированный пост/ролик → отправляется в Telegram админу с превью и
кнопками [✅ Опубликовать] [✏️ Правки] [❌ Отклонить]. На «Правки» админ пишет
текстом что поправить → контент перегенерируется и снова уходит на согласование.
На «Опубликовать» → публикуется во все площадки.

Очередь ожидающих хранится в таблице Connection (ключ moderation_queue, JSON) —
без миграций схемы. Правки идут через `core/kv`: очередь читали и переписывали
целиком, и параллельная задача успевала вклиниться между чтением и записью —
пост исчезал с согласования без следа в логах.
"""
import os
import uuid
from sqlalchemy import select
from core import kv
from database.db import AsyncSessionLocal

QUEUE_KEY = "moderation_queue"     # {pid: {text, media_url, platforms, kind, ref}}
PENDING_FIX_KEY = "pending_fix"    # pid, для которого админ сейчас пишет правки


# Слова, по которым видно, что замечание относится к картинке, а не к тексту.
# Перерисовывать кадр на каждую правку подписи — жечь деньги впустую.
_IMAGE_WORDS = ("картин", "фото", "изображ", "визуал", "кадр", "обложк", "фон",
                "цвет", "свет", "ракурс", "план", "сцен", "перерисуй", "перегенер",
                "image", "photo", "background", "colour", "color", "lighting")


def _about_image(correction: str) -> bool:
    low = (correction or "").lower()
    return any(w in low for w in _IMAGE_WORDS)


async def _tg(method: str, payload: dict) -> dict:
    """Вызов Telegram. Возвращает ответ API: `{"ok": bool, "description": str}`.

    Раньше здесь стоял голый `except: pass`, да и сам ответ не читался. А
    Telegram отвечает `HTTP 200` с `ok:false` — например «failed to get HTTP URL
    content», когда картинка по ссылке не отдалась. То есть отправка падала,
    а система считала, что материал доставлен, и молчала.
    """
    import httpx
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return {"ok": False, "description": "нет TELEGRAM_BOT_TOKEN"}
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"https://api.telegram.org/bot{token}/{method}",
                             json=payload)
        data = r.json()
    except Exception as e:
        return {"ok": False, "description": f"{type(e).__name__}: {str(e)[:150]}"}
    if not data.get("ok"):
        print(f"[NEXUS] Telegram {method}: {str(data.get('description'))[:200]}",
              flush=True)
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
    item = await _get_item(pid)
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
                            kind: str = "plan", ref: str = None,
                            image_prompt: str = "") -> str | None:
    """Кладёт контент в очередь и шлёт админу превью с кнопками. Возвращает pid."""
    # Владелец мог подключить бота через /start, не задавая TELEGRAM_CHAT_ID —
    # это штатный путь. Раньше в таком случае материал молча оседал в очереди
    # и не доходил до человека: «сгенерировал, а в Telegram ничего не прислал».
    from core import notify
    admin = await notify.owner_chat()
    if not admin:
        return None

    pid = uuid.uuid4().hex[:8]
    async with kv.update(QUEUE_KEY, {}) as queue:
        queue[pid] = {"text": text, "media_url": media_url,
                      "platforms": platforms or ["instagram"], "kind": kind,
                      "ref": ref,
                      # Замысел сцены нужен для правки: без него «поменяй фон»
                      # рисуется без всякого представления, что было в кадре.
                      "image_prompt": image_prompt}

    caption = ("🆕 <b>На согласование</b>\n\n" + (text or ""))[:1024]
    kb = _kb(pid)
    if media_url and str(media_url).lower().endswith((".mp4", ".mov", ".webm")):
        res = await _tg("sendVideo", {"chat_id": admin, "video": media_url,
                                      "caption": caption, "parse_mode": "HTML",
                                      "reply_markup": kb})
    elif media_url:
        res = await _tg("sendPhoto", {"chat_id": admin, "photo": media_url,
                                      "caption": caption, "parse_mode": "HTML",
                                      "reply_markup": kb})
    else:
        res = await _tg("sendMessage", {"chat_id": admin, "text": caption,
                                        "parse_mode": "HTML", "reply_markup": kb})

    if not res.get("ok") and media_url:
        # Telegram не смог забрать медиа по ссылке (чаще всего генератор не
        # отдал картинку вовремя). Текст с кнопками важнее картинки: без этого
        # запаса вся работа пропадала молча.
        res = await _tg("sendMessage", {
            "chat_id": admin,
            "text": caption + f"\n\n🖼 Медиа не вложилось: {media_url}\n"
                              f"<i>Причина: {str(res.get('description'))[:150]}</i>",
            "parse_mode": "HTML", "reply_markup": kb})
    if not res.get("ok"):
        print(f"[NEXUS] материал {pid} не доставлен владельцу: "
              f"{str(res.get('description'))[:200]}", flush=True)
    return pid


async def _get_item(pid: str) -> dict | None:
    queue = await kv.get(QUEUE_KEY, {})
    return queue.get(pid)


async def _remove(pid: str):
    async with kv.update(QUEUE_KEY, {}) as queue:
        queue.pop(pid, None)


async def approve(pid: str) -> str:
    """Публикует согласованный контент во все его площадки."""
    from core.orchestrator import nexus_core
    item = await _get_item(pid)
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
        async with AsyncSessionLocal() as db:
            pr = await db.execute(select(ContentPlan).where(ContentPlan.id == item["ref"]))
            p = pr.scalar_one_or_none()
            if p:
                p.status = "published"
                await db.commit()
    await _remove(pid)
    return "📤 <b>Опубликовано</b>\n" + "\n".join(results)


async def reject(pid: str) -> str:
    await _remove(pid)
    return "❌ Отклонено, публиковать не буду."


async def request_fix(pid: str) -> str:
    """Помечает, что админ сейчас будет писать правки для pid."""
    item = await _get_item(pid)
    if not item:
        return "❌ Элемент не найден"
    await kv.set(PENDING_FIX_KEY, pid)
    return "✏️ Напиши одним сообщением, что поправить — я перегенерирую и снова пришлю на согласование."


async def pending_fix_id() -> str | None:
    """Элемент, для которого админ сейчас пишет правки (пусто — таких нет)."""
    return (await kv.get(PENDING_FIX_KEY, "")) or None


async def apply_fix(correction: str) -> str:
    """Применяет текстовые правки к ожидающему элементу и снова шлёт на согласование."""
    pid = await pending_fix_id()
    if not pid:
        return ""
    item = await _get_item(pid)
    await kv.set(PENDING_FIX_KEY, "")  # снимаем флаг
    if not item:
        return "❌ Элемент устарел"
    await _remove(pid)

    kind = item.get("kind", "plan")
    ref = item.get("ref")
    if kind == "plan" and ref:
        from core.orchestrator import nexus_core
        await nexus_core.generate_content_for_plan(ref, corrections=correction)
        return "🔄 Перегенерировал с правками — прислал новую версию на согласование."
    # kind == factory или без ref. Правка может касаться и картинки: раньше
    # сюда просто дописывался текст, а media_url переотправлялся тот же самый —
    # то есть замечание по визуалу не делало ничего, и это выглядело как
    # «картинка не редактируется».
    media = item.get("media_url")
    note = ""
    if media and _about_image(correction):
        from core.media_generator import revise_image
        res = await revise_image(media, correction,
                                 base_prompt=item.get("image_prompt", ""))
        if res.get("ok"):
            media = res["url"]
            note = f"\n🖼 Картинку перерисовал ({res.get('model', 'higgsfield')})."
        else:
            note = f"\n⚠️ Картинку поправить не вышло: {str(res.get('error'))[:150]}"

    new_text = (item.get("text", "") + f"\n\n[Правки: {correction}]")
    await send_for_approval(new_text, media_url=media,
                            platforms=item.get("platforms"), kind=kind, ref=ref,
                            image_prompt=item.get("image_prompt", ""))
    return "🔄 Обновил с учётом правок — на согласовании." + note
