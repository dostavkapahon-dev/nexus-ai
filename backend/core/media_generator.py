"""
Unified media generation: images and video.
Providers: DALL-E 3, Stability AI, Pollinations (free), Runway ML, ElevenLabs (audio).
"""
import os
import httpx
import asyncio
import base64
from urllib.parse import quote

async def generate_image(prompt: str, provider: str = "auto", platform: str = "telegram") -> str:
    """Returns image URL. Provider: auto/imagen/dalle3/stability/pollinations.

    По ТЗ Pakhon Studio primary — Gemini Imagen, fallback — остальные.
    """
    size = "1080x1920" if platform in ("tiktok", "instagram", "youtube") else "1080x1080"

    if provider == "imagen" or (provider == "auto" and os.getenv("GEMINI_API_KEY")):
        url = await _gemini_imagen(prompt, size)
        if url:
            return url

    if provider == "dalle3" or (provider == "auto" and os.getenv("OPENAI_API_KEY")):
        url = await _dalle3(prompt, size)
        if url:
            return url

    if provider == "stability" or (provider == "auto" and os.getenv("STABILITY_API_KEY")):
        url = await _stability(prompt, size)
        if url:
            return url

    # Always works, free fallback
    return _pollinations(prompt, size)

async def _gemini_imagen(prompt: str, size: str) -> str | None:
    """Gemini Imagen 3 через REST. Возвращает data-URI PNG или None."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    w, h = size.split("x")
    ratio = "9:16" if int(h) > int(w) else ("1:1" if w == h else "16:9")
    model = os.getenv("IMAGEN_MODEL", "imagen-3.0-generate-002")
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:predict",
                params={"key": api_key},
                json={"instances": [{"prompt": prompt[:2000]}],
                      "parameters": {"sampleCount": 1, "aspectRatio": ratio}},
            )
            if r.status_code != 200:
                return None
            preds = r.json().get("predictions", [])
            if preds and preds[0].get("bytesBase64Encoded"):
                return f"data:image/png;base64,{preds[0]['bytesBase64Encoded']}"
            return None
    except Exception:
        return None


def _pollinations(prompt: str, size: str = "1080x1080") -> str:
    w, h = size.split("x")
    encoded = quote(prompt[:500])
    return f"https://image.pollinations.ai/prompt/{encoded}?width={w}&height={h}&nologo=true&enhance=true"

async def _dalle3(prompt: str, size: str) -> str | None:
    try:
        import openai
        # DALL-E 3 supports: 1024x1024, 1792x1024, 1024x1792
        dalle_size = "1024x1792" if "1920" in size else "1024x1024"
        client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = await client.images.generate(
            model="dall-e-3",
            prompt=prompt[:4000],
            size=dalle_size,
            quality="standard",
            n=1
        )
        return resp.data[0].url
    except Exception:
        return None

async def _stability(prompt: str, size: str) -> str | None:
    try:
        api_key = os.getenv("STABILITY_API_KEY")
        w, h = size.split("x")
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://api.stability.ai/v2beta/stable-image/generate/sd3",
                headers={"Authorization": f"Bearer {api_key}", "Accept": "image/*"},
                data={"prompt": prompt[:2000], "output_format": "webp",
                      "width": min(int(w), 1440), "height": min(int(h), 1440)},
            )
            if r.status_code == 200:
                # Upload to tmp public URL via base64 data URI (works in modern browsers)
                b64 = base64.b64encode(r.content).decode()
                return f"data:image/webp;base64,{b64}"
            return None
    except Exception:
        return None

async def generate_voice(text: str, voice_id: str = "21m00Tcm4TlvDq8ikWAM") -> str | None:
    """Generate voice using ElevenLabs. Returns audio URL or None."""
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={"xi-api-key": api_key, "Content-Type": "application/json"},
                json={"text": text[:5000], "model_id": "eleven_multilingual_v2",
                      "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}
            )
            if r.status_code == 200:
                b64 = base64.b64encode(r.content).decode()
                return f"data:audio/mpeg;base64,{b64}"
            return None
    except Exception:
        return None

async def generate_video(prompt: str, image_url: str = None) -> str | None:
    """Generate video using Runway ML Gen-3 Alpha. Returns task_id to poll."""
    api_key = os.getenv("RUNWAY_API_KEY")
    if not api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            payload = {
                "promptText": prompt[:512],
                "model": "gen3a_turbo",
                "duration": 5,
                "ratio": "768:1344",
            }
            if image_url and image_url.startswith("http"):
                payload["promptImage"] = image_url

            r = await client.post(
                "https://api.dev.runwayml.com/v1/image_to_video",
                headers={"Authorization": f"Bearer {api_key}", "X-Runway-Version": "2024-11-06",
                         "Content-Type": "application/json"},
                json=payload
            )
            if r.status_code == 200:
                return r.json().get("id")  # task_id to poll
            return None
    except Exception:
        return None

async def poll_video(task_id: str) -> str | None:
    """Poll Runway task for completion. Returns video URL or None."""
    api_key = os.getenv("RUNWAY_API_KEY")
    if not api_key or not task_id:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"https://api.dev.runwayml.com/v1/tasks/{task_id}",
                headers={"Authorization": f"Bearer {api_key}", "X-Runway-Version": "2024-11-06"}
            )
            d = r.json()
            if d.get("status") == "SUCCEEDED":
                return d.get("output", [None])[0]
            return None
    except Exception:
        return None


async def generate_clip(prompt: str, script: str = "", image_url: str = None,
                        provider: str = "auto", ratio: str = "9:16", model: str = None) -> dict:
    """Единая точка генерации видео-клипа для Reels/Shorts/TikTok/VK.

    provider:
      - heygen      → говорящий AI-аватар, озвучивает `script` (нужен HEYGEN_API_KEY)
      - higgsfield  → кинематографичный клип из `prompt`/image (HIGGSFIELD_API_KEY)
      - runway      → image-to-video (RUNWAY_API_KEY)
      - auto        → первый доступный по наличию ключа
    Возвращает {'ok': bool, 'url'|'error', 'provider'}.
    """
    order = (
        [provider] if provider != "auto"
        else ["heygen", "higgsfield", "runway"]
    )
    for p in order:
        if p == "heygen" and os.getenv("HEYGEN_API_KEY"):
            from core.heygen import create_avatar_video, poll_avatar_video
            started = await create_avatar_video(script or prompt, ratio=ratio)
            if started.get("ok"):
                done = await poll_avatar_video(started["video_id"])
                if done.get("ok"):
                    return {"ok": True, "url": done["url"], "provider": "heygen"}
        elif p == "higgsfield" and os.getenv("HIGGSFIELD_API_KEY"):
            from core.higgsfield import create_video, poll_video as hf_poll
            started = await create_video(prompt, image_url=image_url, ratio=ratio, model=model)
            if started.get("ok"):
                done = await hf_poll(started["job_id"])
                if done.get("ok"):
                    return {"ok": True, "url": done["url"], "provider": "higgsfield"}
        elif p == "runway" and os.getenv("RUNWAY_API_KEY"):
            task_id = await generate_video(prompt, image_url)
            if task_id:
                for _ in range(30):
                    await asyncio.sleep(10)
                    url = await poll_video(task_id)
                    if url:
                        return {"ok": True, "url": url, "provider": "runway"}
    return {"ok": False, "error": "Нет доступного видео-провайдера (HeyGen/HiggsField/Runway). "
                                   "Добавьте ключ в Подключениях.", "provider": None}