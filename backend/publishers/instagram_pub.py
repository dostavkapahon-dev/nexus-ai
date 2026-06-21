import os
import asyncio
import httpx

GRAPH_URL = "https://graph.facebook.com/v19.0"

PLACEHOLDER_IMAGE = (
    "https://image.pollinations.ai/prompt/abstract%20background%20minimal"
    "?width=1080&height=1080&nologo=true"
)


async def publish_instagram(text: str, image_url: str = None, video_url: str = None) -> dict:
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    account_id = os.getenv("INSTAGRAM_ACCOUNT_ID")

    if not token or not account_id:
        raise ValueError("INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_ACCOUNT_ID not set")

    async with httpx.AsyncClient(timeout=60) as client:
        # Step 1: create a media container (Reel for video, photo otherwise).
        if video_url:
            params = {"media_type": "REELS", "video_url": video_url,
                      "caption": text, "access_token": token}
        else:
            params = {"image_url": image_url or PLACEHOLDER_IMAGE,
                      "caption": text, "access_token": token}

        r = await client.post(f"{GRAPH_URL}/{account_id}/media", params=params)
        data = r.json()
        if "error" in data:
            raise RuntimeError(f"Instagram error: {data['error']['message']}")
        creation_id = data["id"]

        # Step 2: video containers must finish processing before publish.
        if video_url:
            for _ in range(30):
                s = await client.get(
                    f"{GRAPH_URL}/{creation_id}",
                    params={"fields": "status_code", "access_token": token},
                )
                if s.json().get("status_code") == "FINISHED":
                    break
                await asyncio.sleep(5)

        # Step 3: publish the container.
        r2 = await client.post(
            f"{GRAPH_URL}/{account_id}/media_publish",
            params={"creation_id": creation_id, "access_token": token},
        )
        data2 = r2.json()
        if "error" in data2:
            raise RuntimeError(f"Instagram publish error: {data2['error']['message']}")

        return {"post_id": data2.get("id")}
