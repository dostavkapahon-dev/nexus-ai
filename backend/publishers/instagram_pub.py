import os
import httpx

GRAPH_URL = "https://graph.facebook.com/v19.0"

async def publish_instagram(text: str, image_url: str = None) -> dict:
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    account_id = os.getenv("INSTAGRAM_ACCOUNT_ID")

    if not token or not account_id:
        raise ValueError("INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_ACCOUNT_ID not set")

    async with httpx.AsyncClient() as client:
        if image_url:
            # Step 1: create media container with image
            r = await client.post(
                f"{GRAPH_URL}/{account_id}/media",
                params={
                    "image_url": image_url,
                    "caption": text,
                    "access_token": token
                }
            )
        else:
            # Text-only not supported by Instagram — use placeholder image
            r = await client.post(
                f"{GRAPH_URL}/{account_id}/media",
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
            f"{GRAPH_URL}/{account_id}/media_publish",
            params={
                "creation_id": creation_id,
                "access_token": token
            }
        )
        data2 = r2.json()
        if "error" in data2:
            raise RuntimeError(f"Instagram publish error: {data2['error']['message']}")

        return {"post_id": data2.get("id")}
