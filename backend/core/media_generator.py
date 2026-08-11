"""
Unified media generation: images and video.
Providers: DALL-E 3, Stability AI, Pollinations (free), Runway ML, ElevenLabs (audio).

Генерация медиа — самая дорогая часть системы (видео стоит в разы больше текста),
но раньше она проходила мимо учёта: в кассу попадали только текстовые вызовы.
Теперь каждая генерация записывается с ценой и причиной отказа.
"""
import os
import time
import httpx
import asyncio
import base64
from urllib.parse import quote

# Ориентировочная цена одной генерации, $. Точные тарифы у провайдеров плавают,
# поэтому это оценка для контроля бюджета, а не бухгалтерия.
MEDIA_COST = {
    "pollinations": 0.0,      # бесплатно и без лимитов
    "imagen": 0.03,
    "dalle3": 0.04,
    "stability": 0.01,
    "heygen": 0.30,           # видео с аватаром — самое дорогое
    "higgsfield": 0.20,
    "runway": 0.25,
    "elevenlabs": 0.02,
}


async def _track_media(provider: str, kind: str, ok: bool,
                       duration: float = 0.0, error: str = ""):
    """Записывает генерацию в общую кассу — ту же, что считает текстовые вызовы."""
    try:
        from core.cost_tracker import record
        await record(model=f"{provider}:{kind}", tokens=0,
                     cost=MEDIA_COST.get(provider, 0.0) if ok else 0.0,
                     status="success" if ok else "error",
                     duration=duration, error=error, agent="media")
    except Exception:
        pass

async def generate_image(prompt: str, provider: str = "auto", platform: str = "telegram") -> str:
    """Returns image URL. Provider: auto/imagen/dalle3/stability/pollinations.

    По ТЗ Pakhon Studio primary — Gemini Imagen, fallback — остальные.
    """
    size = "1080x1920" if platform in ("tiktok", "instagram", "youtube") else "1080x1080"

    # Порядок: платные по наличию ключа → бесплатный Pollinations как гарантия.
    chain = []
    if provider == "imagen" or (provider == "auto" and os.getenv("GEMINI_API_KEY")):
        chain.append(("imagen", lambda: _gemini_imagen(prompt, size)))
    if provider == "dalle3" or (provider == "auto" and os.getenv("OPENAI_API_KEY")):
        chain.append(("dalle3", lambda: _dalle3(prompt, size)))
    if provider == "stability" or (provider == "auto" and os.getenv("STABILITY_API_KEY")):
        chain.append(("stability", lambda: _stability(prompt, size)))

    for name, call in chain:
        t0 = time.time()
        try:
            url = await call()
        except Exception as e:
            await _track_media(name, "image", False, time.time() - t0, str(e)[:200])
            continue
        if url:
            await _track_media(name, "image", True, time.time() - t0)
            return url
        # Провайдер вернул пусто — платить не за что, но знать об этом полезно.
        await _track_media(name, "image", False, time.time() - t0, "пустой ответ провайдера")

    # Бесплатный путь работает всегда — картинка будет в любом случае.
    url = _pollinations(prompt, size)
    await _track_media("pollinations", "image", True)
    return url

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
    # Раньше причина отказа каждого провайдера терялась, и наверх уходило общее
    # «нет провайдера» — чинить по такому сообщению было невозможно.
    attempts = {}
    for p in order:
        t0 = time.time()
        try:
            if p == "heygen" and os.getenv("HEYGEN_API_KEY"):
                from core.heygen import create_avatar_video, poll_avatar_video
                started = await create_avatar_video(script or prompt, ratio=ratio)
                if not started.get("ok"):
                    attempts[p] = str(started.get("error", "не удалось запустить"))[:200]
                else:
                    done = await poll_avatar_video(started["video_id"])
                    if done.get("ok"):
                        await _track_media(p, "video", True, time.time() - t0)
                        return {"ok": True, "url": done["url"], "provider": "heygen"}
                    attempts[p] = str(done.get("error", "видео не готово"))[:200]
            elif p == "higgsfield" and os.getenv("HIGGSFIELD_API_KEY"):
                from core.higgsfield import create_video, poll_video as hf_poll
                started = await create_video(prompt, image_url=image_url, ratio=ratio, model=model)
                if not started.get("ok"):
                    attempts[p] = str(started.get("error", "не удалось запустить"))[:200]
                else:
                    done = await hf_poll(started["job_id"])
                    if done.get("ok"):
                        await _track_media(p, "video", True, time.time() - t0)
                        return {"ok": True, "url": done["url"], "provider": "higgsfield"}
                    attempts[p] = str(done.get("error", "видео не готово"))[:200]
            elif p == "runway" and os.getenv("RUNWAY_API_KEY"):
                task_id = await generate_video(prompt, image_url)
                if not task_id:
                    attempts[p] = "не удалось создать задачу"
                else:
                    for _ in range(30):
                        await asyncio.sleep(10)
                        url = await poll_video(task_id)
                        if url:
                            await _track_media(p, "video", True, time.time() - t0)
                            return {"ok": True, "url": url, "provider": "runway"}
                    attempts[p] = "истекло время ожидания рендера"
            else:
                attempts[p] = "нет ключа провайдера"
                continue
        except Exception as e:
            attempts[p] = f"{type(e).__name__}: {str(e)[:150]}"
        await _track_media(p, "video", False, time.time() - t0, attempts.get(p, ""))
    # Показываем, что именно случилось у каждого провайдера: без этого
    # сообщение «нет провайдера» одинаково для отсутствия ключа и для сбоя рендера.
    if attempts and any(v != "нет ключа провайдера" for v in attempts.values()):
        detail = "; ".join(f"{p}: {err}" for p, err in attempts.items())
        return {"ok": False, "error": f"Видео не сгенерировано. {detail}",
                "provider": None, "attempts": attempts}
    return {"ok": False, "error": "Нет доступного видео-провайдера (HeyGen/HiggsField/Runway). "
                                   "Добавьте ключ в Подключениях.",
            "provider": None, "attempts": attempts}