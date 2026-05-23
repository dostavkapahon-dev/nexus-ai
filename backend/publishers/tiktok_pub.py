"""
TikTok Content Posting API v2.
Requires: TIKTOK_ACCESS_TOKEN (from TikTok for Developers → Content Posting API).
Supports photo posts (carousel) and video posts.
"""
import os
import httpx

TIKTOK_API = "https://open.tiktokapis.com/v2"

async def publish_tiktok_photo(text: str, image_url: str) -> dict:
    """Publish a photo post to TikTok via Content Posting API."""
    token = os.getenv("TIKTOK_ACCESS_TOKEN")
    if not token:
        raise ValueError("TIKTOK_ACCESS_TOKEN not configured")

    async with httpx.AsyncClient(timeout=30) as client:
        # Step 1: Init photo post
        r = await client.post(
            f"{TIKTOK_API}/post/publish/content/init/",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
            json={
                "post_info": {
                    "title": text[:150],
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                },
                "source_info": {
                    "source": "PULL_FROM_URL",
                    "photo_cover_index": 0,
                    "photo_images": [image_url],
                },
                "post_mode": "DIRECT_POST",
                "media_type": "PHOTO",
            }
        )
        data = r.json()
        if "error" in data and data["error"].get("code") != "ok":
            raise RuntimeError(f"TikTok error: {data['error'].get('message')}")

        return {"publish_id": data.get("data", {}).get("publish_id"), "status": "published"}

async def get_tiktok_creator_info() -> dict:
    """Fetch TikTok creator info to validate token."""
    token = os.getenv("TIKTOK_ACCESS_TOKEN")
    if not token:
        raise ValueError("TIKTOK_ACCESS_TOKEN not configured")

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"{TIKTOK_API}/post/publish/creator_info/query/",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
            json={}
        )
        return r.json()
