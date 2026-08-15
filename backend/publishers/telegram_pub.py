"""
Публикация в Telegram через своего бота.

Раньше здесь была одна функция на текст и картинку. Но канал — это не только
пост: нужны видео, служебные сообщения и возможность удалить тестовую
публикацию, не оставляя мусора в канале. Поэтому методы Bot API вынесены в
тонкие обёртки с общей обработкой ошибок: наверх всегда уходит либо
`{"ok": True, "message_id": ...}`, либо понятная причина отказа.
"""
import os

import httpx

API = "https://api.telegram.org/bot{token}/{method}"

# Telegram режет подпись к медиа на 1024 символах, а обычный текст — на 4096.
CAPTION_LIMIT = 1024
TEXT_LIMIT = 4096


def bot_token() -> str:
    return (os.getenv("TELEGRAM_BOT_TOKEN", "") or "").strip()


async def call(method: str, payload: dict, *, token: str = "", timeout: float = 30) -> dict:
    """Один вызов Bot API. Возвращает распакованный ответ Telegram.

    Телеграм и на ошибке отвечает 200 с `ok: false`, поэтому статус HTTP здесь
    ничего не решает — смотрим на тело.
    """
    tok = (token or bot_token()).strip()
    if not tok:
        return {"ok": False, "error": "не задан TELEGRAM_BOT_TOKEN"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(API.format(token=tok, method=method), json=payload)
            data = r.json()
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
    if not data.get("ok"):
        return {"ok": False, "error": str(data.get("description") or "Telegram отказал")[:300],
                "error_code": data.get("error_code")}
    return {"ok": True, "result": data.get("result")}


def _msg(res: dict, chat_id: str) -> dict:
    """Единый вид успешного ответа: id сообщения и ссылка, если канал публичный."""
    if not res.get("ok"):
        return res
    result = res.get("result") or {}
    message_id = result.get("message_id")
    chat = result.get("chat") or {}
    username = chat.get("username") or ""
    url = f"https://t.me/{username}/{message_id}" if username and message_id else ""
    return {"ok": True, "message_id": message_id, "post_url": url,
            "chat_id": str(chat.get("id") or chat_id)}


async def send_message(chat_id: str, text: str, *, token: str = "",
                       silent: bool = False) -> dict:
    res = await call("sendMessage", {
        "chat_id": chat_id, "text": (text or "")[:TEXT_LIMIT],
        "parse_mode": "HTML", "disable_notification": silent}, token=token)
    return _msg(res, chat_id)


async def send_photo(chat_id: str, photo: str, caption: str = "", *, token: str = "",
                     silent: bool = False) -> dict:
    res = await call("sendPhoto", {
        "chat_id": chat_id, "photo": photo, "caption": (caption or "")[:CAPTION_LIMIT],
        "parse_mode": "HTML", "disable_notification": silent}, token=token)
    return _msg(res, chat_id)


async def send_video(chat_id: str, video: str, caption: str = "", *, token: str = "",
                     silent: bool = False) -> dict:
    # Загрузка видео по ссылке у Telegram дольше картинки — таймаут отдельный,
    # иначе нормальный ролик обрывается на середине и выглядит как отказ канала.
    res = await call("sendVideo", {
        "chat_id": chat_id, "video": video, "caption": (caption or "")[:CAPTION_LIMIT],
        "parse_mode": "HTML", "supports_streaming": True,
        "disable_notification": silent}, token=token, timeout=120)
    return _msg(res, chat_id)


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
