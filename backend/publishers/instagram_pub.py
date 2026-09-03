"""
Публикация в Instagram: фото, Reels, карусель, сторис.

Как это устроено у Meta: сначала создаётся «контейнер» (`/media`), затем он
публикуется (`/media_publish`). Для видео между этими шагами обязательна пауза —
Meta должна дожать ролик, и до статуса `FINISHED` публиковать его нельзя.

Что здесь было раньше и почему это чинится:
  * видео не публиковалось вовсе — параметр молча терялся, а пользователю
    сообщалось об успехе;
  * пост без картинки подменялся случайным изображением с чужого сервиса:
    в аккаунт клиента уходила абстракция вместо задуманного;
  * готовность контейнера не проверялась — при медленной картинке Meta отвечала
    «Media ID is not available»;
  * запросы шли без таймаута, и зависание Meta вешало публикацию навсегда.
"""
import asyncio

import httpx

from connectors import ig_api

TIMEOUT = 60
# Meta дожимает видео обычно за 10–40 секунд; ждём до трёх минут, дальше честно
# отвечаем, что площадка не успела, — это лучше, чем публиковать «пустой» id.
READY_TIMEOUT = 180
READY_STEP = 5


class InstagramError(RuntimeError):
    """Отказ Instagram с человеческой причиной."""


async def _post(client: httpx.AsyncClient, path: str, params: dict) -> dict:
    r = await client.post(ig_api.url(path), params={**params, "access_token": ig_api.token()})
    data = r.json()
    if "error" in data:
        raise InstagramError(str(data["error"].get("message") or data["error"])[:300])
    return data


async def _container(client: httpx.AsyncClient, params: dict) -> str:
    data = await _post(client, ig_api.me_path("media"), params)
    return data["id"]


async def _wait_ready(client: httpx.AsyncClient, creation_id: str) -> None:
    """Ждёт, пока Meta дожмёт медиа. Без этого видео опубликовать невозможно."""
    waited = 0
    while waited < READY_TIMEOUT:
        r = await client.get(ig_api.url(creation_id),
                             params={"fields": "status_code,status",
                                     "access_token": ig_api.token()})
        data = r.json()
        status = (data.get("status_code") or "").upper()
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise InstagramError("Instagram не смог обработать медиа: "
                                 + str(data.get("status") or "")[:200])
        if status == "PUBLISHED":
            return
        await asyncio.sleep(READY_STEP)
        waited += READY_STEP
    raise InstagramError(f"Instagram не обработал медиа за {READY_TIMEOUT} секунд — "
                         f"попробуйте ролик меньшего размера или повторите позже")


async def _publish(client: httpx.AsyncClient, creation_id: str) -> dict:
    data = await _post(client, ig_api.me_path("media_publish"), {"creation_id": creation_id})
    return {"post_id": data.get("id")}


async def quota_left() -> dict:
    """Сколько публикаций осталось в суточной квоте Instagram (лимит — 25).

    Раньше в лимит упирались вслепую: очередь повторяла публикацию, а Meta
    отказывала снова и снова.
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(ig_api.url(ig_api.me_path("content_publishing_limit")),
                                 params={"fields": "config,quota_usage",
                                         "access_token": ig_api.token()})
            data = (r.json().get("data") or [{}])[0]
    except Exception:
        return {"known": False}
    used = data.get("quota_usage")
    total = (data.get("config") or {}).get("quota_total", 25)
    if used is None:
        return {"known": False}
    return {"known": True, "used": int(used), "total": int(total),
            "left": max(int(total) - int(used), 0)}


async def publish_instagram(text: str, image_url: str = None, video_url: str = None,
                            images: list[str] | None = None,
                            as_story: bool = False) -> dict:
    """Публикация в Instagram.

    Тип определяется тем, что передали: несколько картинок — карусель,
    видео — Reels (или сторис), одна картинка — обычный пост.
    Текста без медиа в Instagram не существует — так и отвечаем.
    """
    if not ig_api.configured():
        raise InstagramError("не заданы " + ", ".join(ig_api.missing()))

    images = [u for u in (images or []) if u]
    if not (image_url or video_url or images):
        raise InstagramError(
            "Instagram не публикует текст без медиа — нужна картинка или видео")

    quota = await quota_left()
    if quota.get("known") and quota.get("left", 1) <= 0:
        raise InstagramError(
            f"исчерпана суточная квота Instagram ({quota['used']}/{quota['total']} "
            f"публикаций) — площадка не примет пост до обновления лимита")

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # ── карусель: сперва дети, потом контейнер-обёртка ──
        if len(images) > 1:
            children = []
            for url in images[:10]:            # Instagram принимает до 10 элементов
                child = await _container(client, {"image_url": url,
                                                  "is_carousel_item": "true"})
                children.append(child)
            creation_id = await _container(client, {
                "media_type": "CAROUSEL", "children": ",".join(children),
                "caption": text or ""})
            await _wait_ready(client, creation_id)
            return {**await _publish(client, creation_id), "kind": "carousel",
                    "items": len(children)}

        # ── видео: Reels или сторис ──
        if video_url:
            params = {"video_url": video_url,
                      "media_type": "STORIES" if as_story else "REELS"}
            if not as_story:
                params["caption"] = text or ""
            creation_id = await _container(client, params)
            # Обязательное ожидание: свежий контейнер видео публиковать нельзя.
            await _wait_ready(client, creation_id)
            return {**await _publish(client, creation_id),
                    "kind": "story" if as_story else "reel"}

        # ── одна картинка ──
        url = image_url or images[0]
        params = {"image_url": url}
        if as_story:
            params["media_type"] = "STORIES"
        else:
            params["caption"] = text or ""
        creation_id = await _container(client, params)
        await _wait_ready(client, creation_id)
        return {**await _publish(client, creation_id),
                "kind": "story" if as_story else "photo"}
