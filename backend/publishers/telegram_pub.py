"""
Публикация в Telegram через своего бота.

Раньше здесь была одна функция на текст и картинку. Но канал — это не только
пост: нужны видео, служебные сообщения и возможность удалить тестовую
публикацию, не оставляя мусора в канале. Поэтому методы Bot API вынесены в
тонкие обёртки с общей обработкой ошибок: наверх всегда уходит либо
`{"ok": True, "message_id": ...}`, либо понятная причина отказа.
"""
import asyncio
import html
import os

import httpx

API = "https://api.telegram.org/bot{token}/{method}"

# Telegram режет подпись к медиа на 1024 символах, а обычный текст — на 4096.
CAPTION_LIMIT = 1024
TEXT_LIMIT = 4096


def bot_token() -> str:
    return (os.getenv("TELEGRAM_BOT_TOKEN", "") or "").strip()


# Формулировки Telegram, при которых повторять бессмысленно: дело не в связи,
# а в правах или в самом канале.
_PERMANENT_ERRORS = ("not enough rights", "chat not found", "bot was blocked",
                     "bot is not a member", "user is deactivated",
                     "have no rights", "chat_write_forbidden", "need administrator")


def _is_permanent(description: str, code: int | None) -> bool:
    low = (description or "").lower()
    return code == 403 or any(w in low for w in _PERMANENT_ERRORS)


async def call(method: str, payload: dict, *, token: str = "", timeout: float = 30,
               retries: int = 2) -> dict:
    """Один вызов Bot API. Возвращает распакованный ответ Telegram.

    Телеграм и на ошибке отвечает 200 с `ok: false`, поэтому статус HTTP здесь
    ничего не решает — смотрим на тело. Два случая разбираются отдельно:
      * 429 — Telegram сам говорит, сколько ждать (`retry_after`); ждём и
        повторяем, вместо того чтобы отдавать наверх «не получилось»;
      * 403 и «нет прав» — повторять нечего, помечаем отказ окончательным,
        иначе очередь пять раз долбится в канал, откуда бота выгнали.
    """
    tok = (token or bot_token()).strip()
    if not tok:
        return {"ok": False, "error": "не задан TELEGRAM_BOT_TOKEN"}

    attempt = 0
    while True:
        try:
            async with httpx.AsyncClient(timeout=timeout) as c:
                r = await c.post(API.format(token=tok, method=method), json=payload)
                data = r.json()
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}

        if data.get("ok"):
            return {"ok": True, "result": data.get("result")}

        desc = str(data.get("description") or "Telegram отказал")
        code = data.get("error_code")
        retry_after = int((data.get("parameters") or {}).get("retry_after") or 0)

        if retry_after and attempt < retries:
            # Ждать столько, сколько просит Telegram, — единственный способ не
            # усугубить лимит собственными повторами.
            await asyncio.sleep(min(retry_after, 60))
            attempt += 1
            continue

        out = {"ok": False, "error": desc[:300], "error_code": code}
        if retry_after:
            out["retry_after"] = retry_after
        if _is_permanent(desc, code):
            out["blocked_by_api"] = True
            out["error"] = _explain(desc)
        return out


def _explain(description: str) -> str:
    """Человеческая причина вместо телеграмовской формулировки."""
    low = (description or "").lower()
    if "not enough rights" in low or "have no rights" in low or "need administrator" in low:
        return "у бота нет прав публиковать в этом канале — сделайте его администратором"
    if "chat not found" in low:
        return "канал не найден — проверьте, что бот всё ещё в нём состоит"
    if "bot was blocked" in low:
        return "пользователь заблокировал бота"
    if "bot is not a member" in low:
        return "бота удалили из канала"
    return description[:300]


def _msg(res: dict, chat_id: str, truncated: bool = False) -> dict:
    """Единый вид успешного ответа: id сообщения и ссылка, если канал публичный."""
    if not res.get("ok"):
        return res if not truncated else {**res, "truncated": True}
    result = res.get("result") or {}
    message_id = result.get("message_id")
    chat = result.get("chat") or {}
    username = chat.get("username") or ""
    url = f"https://t.me/{username}/{message_id}" if username and message_id else ""
    out = {"ok": True, "message_id": message_id, "post_url": url,
           "chat_id": str(chat.get("id") or chat_id)}
    if truncated:
        out["truncated"] = True
        out["note"] = "текст был длиннее лимита Telegram и опубликован сокращённым"
    return out


def fit(text: str, limit: int) -> tuple[str, bool]:
    """Подрезает текст под лимит Telegram и говорит, пришлось ли это сделать.

    Молчаливая обрезка означала «опубликовано» для поста, у которого отрезали
    половину: пользователь узнавал об этом, только открыв канал.
    """
    text = text or ""
    if len(text) <= limit:
        return text, False
    return text[:limit - 1].rstrip() + "…", True


def safe(text: str) -> str:
    """Экранирует то, что уедет с parse_mode=HTML.

    Один символ `<` или `&` в тексте от модели превращал отправку в ошибку
    «can't parse entities», и сообщение просто исчезало.
    """
    return html.escape(text or "", quote=False)


async def send_message(chat_id: str, text: str, *, token: str = "",
                       silent: bool = False, escape: bool = False) -> dict:
    body, cut = fit(safe(text) if escape else text, TEXT_LIMIT)
    res = await call("sendMessage", {
        "chat_id": chat_id, "text": body,
        "parse_mode": "HTML", "disable_notification": silent}, token=token)
    return _msg(res, chat_id, truncated=cut)


async def send_photo(chat_id: str, photo: str, caption: str = "", *, token: str = "",
                     silent: bool = False) -> dict:
    body, cut = fit(caption, CAPTION_LIMIT)
    res = await call("sendPhoto", {
        "chat_id": chat_id, "photo": photo, "caption": body,
        "parse_mode": "HTML", "disable_notification": silent}, token=token)
    return _msg(res, chat_id, truncated=cut)


async def send_video(chat_id: str, video: str, caption: str = "", *, token: str = "",
                     silent: bool = False) -> dict:
    # Загрузка видео по ссылке у Telegram дольше картинки — таймаут отдельный,
    # иначе нормальный ролик обрывается на середине и выглядит как отказ канала.
    body, cut = fit(caption, CAPTION_LIMIT)
    res = await call("sendVideo", {
        "chat_id": chat_id, "video": video, "caption": body,
        "parse_mode": "HTML", "supports_streaming": True,
        "disable_notification": silent}, token=token, timeout=120)
    if not res.get("ok") and "file" in str(res.get("error", "")).lower():
        # Бот загружает по ссылке не больше 50 МБ — самая частая причина отказа,
        # и без пояснения она выглядит как «Telegram сломался».
        res["hint"] = ("Telegram принимает по ссылке видео до 50 МБ — "
                       "сожмите ролик или дайте прямую ссылку меньшего размера")
    return _msg(res, chat_id, truncated=cut)


async def delete_message(chat_id: str, message_id: int, *, token: str = "") -> dict:
    return await call("deleteMessage", {"chat_id": chat_id, "message_id": message_id},
                      token=token)


async def publish_telegram(chat_id: str, text: str, image_url: str = None,
                           video_url: str = None) -> dict:
    """Публикация поста: видео → фото → просто текст.

    Совместимость: функция исторически бросала исключение при отказе — так её
    и вызывает `TelegramConnector.publish`, оборачивая в try. Поведение оставлено.
    """
    if video_url:
        res = await send_video(chat_id, video_url, text or "")
    elif image_url:
        res = await send_photo(chat_id, image_url, text or "")
    else:
        res = await send_message(chat_id, text or "")
    if not res.get("ok"):
        raise RuntimeError(f"Telegram error: {res.get('error')}")
    return {"message_id": res.get("message_id"), "post_url": res.get("post_url", "")}
