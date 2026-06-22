"""
HeyGen — AI-аватары и говорящие видео.
Создаёт видео с цифровым аватаром, озвучивающим текст (идеально для Reels,
Shorts, TikTok, VK-клипов).
Docs: https://docs.heygen.com
Требует HEYGEN_API_KEY.
"""
import os
import asyncio
import httpx

HEYGEN_API = "https://api.heygen.com"


async def create_avatar_video(text: str, avatar_id: str = None, voice_id: str = None,
                              ratio: str = "9:16") -> dict:
    """Запускает генерацию видео с аватаром. Возвращает {'video_id': ...} для опроса."""
    api_key = os.getenv("HEYGEN_API_KEY", "")
    if not api_key:
        return {"ok": False, "error": "HEYGEN_API_KEY not set"}

    avatar_id = avatar_id or os.getenv("HEYGEN_AVATAR_ID", "Daisy-inskirt-20220818")
    voice_id = voice_id or os.getenv("HEYGEN_VOICE_ID", "1bd001e7e50f421d891986aad5158bc8")
    dimension = {"width": 720, "height": 1280} if ratio == "9:16" else {"width": 1280, "height": 720}

    payload = {
        "video_inputs": [{
            "character": {"type": "avatar", "avatar_id": avatar_id, "avatar_style": "normal"},
            "voice": {"type": "text", "input_text": text[:1500], "voice_id": voice_id},
        }],
        "dimension": dimension,
    }
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{HEYGEN_API}/v2/video/generate",
                         headers={"X-Api-Key": api_key, "Content-Type": "application/json"},
                         json=payload)
        data = r.json()
        if r.status_code >= 400 or data.get("error"):
            return {"ok": False, "error": str(data.get("error") or data)}
        return {"ok": True, "video_id": data.get("data", {}).get("video_id")}


async def poll_avatar_video(video_id: str, attempts: int = 30, delay: float = 10) -> dict:
    """Опрашивает статус. Возвращает {'ok': True, 'url': ...} когда готово."""
    api_key = os.getenv("HEYGEN_API_KEY", "")
    if not api_key or not video_id:
        return {"ok": False, "error": "no api key or video_id"}
    async with httpx.AsyncClient(timeout=15) as c:
        for _ in range(attempts):
            r = await c.get(f"{HEYGEN_API}/v1/video_status.get",
                            headers={"X-Api-Key": api_key}, params={"video_id": video_id})
            d = r.json().get("data", {})
            status = d.get("status")
            if status == "completed":
                return {"ok": True, "url": d.get("video_url")}
            if status in ("failed", "error"):
                return {"ok": False, "error": d.get("error", "generation failed")}
            await asyncio.sleep(delay)
    return {"ok": False, "error": "timeout waiting for HeyGen video"}
