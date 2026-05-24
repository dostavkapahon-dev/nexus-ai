"""
Threads publisher via Meta Threads API.
Requires THREADS_ACCESS_TOKEN and THREADS_USER_ID.
"""
import os
import httpx

GRAPH = "https://graph.threads.net/v1.0"

async def publish_threads(text: str, image_url: str = None) -> dict:
    token = os.getenv("THREADS_ACCESS_TOKEN", "")
    user_id = os.getenv("THREADS_USER_ID", "")
    if not token or not user_id:
        raise ValueError("THREADS_ACCESS_TOKEN and THREADS_USER_ID not set")

    async with httpx.AsyncClient(timeout=20) as c:
        # Step 1: create media container
        params = {"text": text, "access_token": token}
        if image_url:
            params["media_type"] = "IMAGE"
            params["image_url"] = image_url
        else:
            params["media_type"] = "TEXT"

        r = await c.post(f"{GRAPH}/{user_id}/threads", params=params)
        data = r.json()
        if "error" in data:
            raise RuntimeError(f"Threads error: {data['error']['message']}")
        container_id = data["id"]

        # Step 2: publish
        r2 = await c.post(f"{GRAPH}/{user_id}/threads_publish",
                          params={"creation_id": container_id, "access_token": token})
        data2 = r2.json()
        if "error" in data2:
            raise RuntimeError(f"Threads publish error: {data2['error']['message']}")
        return {"post_id": data2["id"]}
