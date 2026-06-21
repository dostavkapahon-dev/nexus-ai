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
    """Returns image URL. Provider: auto/dalle3/stability/pollinations."""
    size = "1080x1920" if platform == "tiktok" else "1080x1080"

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

async def generate_video(prompt: str, image_url: str = None, provider: str = "auto") -> str | None:
    """Generate a video and return a ready-to-use URL (or None).

    Providers: auto / heygen / higgsfield / runway.
    `auto` tries every provider that has an API key configured, in order.
    Each provider polls internally until the clip is ready, so callers get a
    final URL without having to manage task ids.
    """
    order = {
        "heygen": _heygen_video,
        "higgsfield": _higgsfield_video,
        "runway": _runway_video,
    }
    if provider != "auto":
        fn = order.get(provider)
        return await fn(prompt, image_url) if fn else None

    for name, fn in order.items():
        url = await fn(prompt, image_url)
        if url:
            return url
    return None


async def _poll(fn, attempts: int = 30, delay: float = 6.0):
    """Poll an async status callback until it returns a truthy value or times out."""
    for _ in range(attempts):
        result = await fn()
        if result:
            return result
        await asyncio.sleep(delay)
    return None


async def _heygen_video(prompt: str, image_url: str = None) -> str | None:
    """HeyGen avatar text-to-video. Avatar/voice are account-specific — override
    via HEYGEN_AVATAR_ID / HEYGEN_VOICE_ID env vars."""
    api_key = os.getenv("HEYGEN_API_KEY")
    if not api_key:
        return None
    avatar_id = os.getenv("HEYGEN_AVATAR_ID", "Daisy-inskirt-20220818")
    voice_id = os.getenv("HEYGEN_VOICE_ID", "2d5b0e6cf36f460aa7fc47e3eee4ba54")
    headers = {"X-Api-Key": api_key, "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.heygen.com/v2/video/generate",
                headers=headers,
                json={
                    "video_inputs": [{
                        "character": {"type": "avatar", "avatar_id": avatar_id, "avatar_style": "normal"},
                        "voice": {"type": "text", "input_text": prompt[:1500], "voice_id": voice_id},
                    }],
                    "dimension": {"width": 720, "height": 1280},
                },
            )
            data = r.json().get("data") or {}
            video_id = data.get("video_id")
            if not video_id:
                return None

        async def check():
            async with httpx.AsyncClient(timeout=15) as c:
                s = await c.get(
                    "https://api.heygen.com/v1/video_status.get",
                    headers=headers, params={"video_id": video_id},
                )
                d = s.json().get("data") or {}
                if d.get("status") == "completed":
                    return d.get("video_url")
                if d.get("status") == "failed":
                    return "FAILED"
                return None

        result = await _poll(check)
        return None if result == "FAILED" else result
    except Exception:
        return None


async def _higgsfield_video(prompt: str, image_url: str = None) -> str | None:
    """Higgsfield image/text-to-video. Endpoint is configurable via
    HIGGSFIELD_API_BASE since their API surface varies by plan."""
    api_key = os.getenv("HIGGSFIELD_API_KEY")
    if not api_key:
        return None
    base = os.getenv("HIGGSFIELD_API_BASE", "https://platform.higgsfield.ai/v1").rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        payload = {"prompt": prompt[:1500], "duration": 5, "aspect_ratio": "9:16"}
        if image_url and image_url.startswith("http"):
            payload["image_url"] = image_url
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{base}/video/generate", headers=headers, json=payload)
            if r.status_code not in (200, 201):
                return None
            data = r.json()
            # Some plans return the URL synchronously, others a job id to poll.
            direct = data.get("video_url") or data.get("url")
            if direct:
                return direct
            job_id = data.get("id") or data.get("job_id")
            if not job_id:
                return None

        async def check():
            async with httpx.AsyncClient(timeout=15) as c:
                s = await c.get(f"{base}/video/status/{job_id}", headers=headers)
                d = s.json()
                if d.get("status") in ("completed", "succeeded"):
                    return d.get("video_url") or d.get("url")
                if d.get("status") in ("failed", "error"):
                    return "FAILED"
                return None

        result = await _poll(check)
        return None if result == "FAILED" else result
    except Exception:
        return None


async def _runway_video(prompt: str, image_url: str = None) -> str | None:
    """Runway ML Gen-3. Polls internally and returns the final clip URL."""
    api_key = os.getenv("RUNWAY_API_KEY")
    if not api_key:
        return None
    headers = {"Authorization": f"Bearer {api_key}", "X-Runway-Version": "2024-11-06",
               "Content-Type": "application/json"}
    try:
        payload = {"promptText": prompt[:512], "model": "gen3a_turbo",
                   "duration": 5, "ratio": "768:1344"}
        if image_url and image_url.startswith("http"):
            payload["promptImage"] = image_url
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post("https://api.dev.runwayml.com/v1/image_to_video",
                                  headers=headers, json=payload)
            if r.status_code != 200:
                return None
            task_id = r.json().get("id")
            if not task_id:
                return None

        async def check():
            async with httpx.AsyncClient(timeout=15) as c:
                s = await c.get(f"https://api.dev.runwayml.com/v1/tasks/{task_id}", headers=headers)
                d = s.json()
                if d.get("status") == "SUCCEEDED":
                    return d.get("output", [None])[0]
                if d.get("status") == "FAILED":
                    return "FAILED"
                return None

        result = await _poll(check)
        return None if result == "FAILED" else result
    except Exception:
        return None