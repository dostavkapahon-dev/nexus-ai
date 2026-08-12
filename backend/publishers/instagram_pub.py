import os
import httpx

from connectors import ig_api


async def publish_instagram(text: str, image_url: str = None) -> dict:
    """Публикация в Instagram: контейнер → publish.

    Адрес и путь зависят от типа токена: у Instagram Login это
    `graph.instagram.com/me/media`, у Facebook — `graph.facebook.com/{id}/media`.
    Раньше путь был зашит под Facebook, и токен IGAA… не работал вовсе.
    """
    token = ig_api.token()

    if not ig_api.configured():
        raise ValueError("не заданы " + ", ".join(ig_api.missing()))

    async with httpx.AsyncClient() as client:
        if image_url:
            # Step 1: create media container with image
            r = await client.post(
                ig_api.url(ig_api.me_path("media")),
                params={
                    "image_url": image_url,
                    "caption": text,
                    "access_token": token
                }
            )
        else:
            # Text-only not supported by Instagram — use placeholder image
            r = await client.post(
                ig_api.url(ig_api.me_path("media")),
                params={
                    "image_url": "https://image.pollinations.ai/prompt/abstract%20background%20minimal?width=1080&height=1080&nologo=true",
                    "caption": text,
                    "access_token": token
                }
            )

        data = r.json()
        if "error" in data:
            raise RuntimeError(f"Instagram error: {data['error']['message']}")

        creation_id = data["id"]

        # Step 2: publish the container
        r2 = await client.post(
            ig_api.url(ig_api.me_path("media_publish")),
            params={
                "creation_id": creation_id,
                "access_token": token
            }
        )
        data2 = r2.json()
        if "error" in data2:
            raise RuntimeError(f"Instagram publish error: {data2['error']['message']}")

        return {"post_id": data2.get("id")}
