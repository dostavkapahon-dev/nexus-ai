"""
YouTube publisher — uploads Shorts via YouTube Data API v3.
Requires YOUTUBE_API_KEY (for search) and OAuth credentials for uploads.
For automated uploads, uses youtube-upload approach via service account.
"""
import os
import httpx

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"

async def publish_youtube_short(title: str, description: str, video_path: str = None,
                                  video_url: str = None, tags: list = None) -> dict:
    """Upload a YouTube Short. Returns video ID."""
    api_key = os.getenv("YOUTUBE_API_KEY", "")
    if not api_key:
        raise ValueError("YOUTUBE_API_KEY not set")

    # For full upload we need OAuth — for now log the intent and return placeholder
    # Real upload requires google-auth + google-api-python-client with OAuth2 credentials
    # TODO: implement full OAuth upload when YOUTUBE_OAUTH_JSON is set
    tags = tags or []
    return {
        "ok": False,
        "message": "YouTube upload requires OAuth2 credentials. Add YOUTUBE_OAUTH_JSON to settings.",
        "title": title,
        "tags": tags,
    }

async def search_trending(niche: str, api_key: str = None) -> list:
    """Search YouTube for trending videos in niche."""
    key = api_key or os.getenv("YOUTUBE_API_KEY", "")
    if not key:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{YOUTUBE_API}/search", params={
                "part": "snippet", "q": niche, "type": "video",
                "order": "viewCount", "maxResults": 5,
                "videoDuration": "short", "key": key
            })
            items = r.json().get("items", [])
            return [{"title": i["snippet"]["title"], "channel": i["snippet"]["channelTitle"]} for i in items]
    except Exception:
        return []
