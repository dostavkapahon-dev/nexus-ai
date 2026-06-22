"""
SKILLS — навыки экономной генерации и комбинирования ИИ.
========================================================
Принципы:
  • НЕ жечь токены: тяжёлую/массовую генерацию текста гнать на бесплатный Gemini,
    дорогой «мозг» (Claude) — только для ключевых креативных решений.
  • Картинки/кадры — бесплатно через Pollinations (безлимит), их же использовать
    как сид-кадр для HiggsField (платим только за анимацию, не за фото).
  • Комбинировать провайдеров по задаче, а не звать всё подряд.
"""
import os
from urllib.parse import quote

# Какой провайдер дешевле для какой задачи (берётся первый доступный по ключу).
TEXT_TASK_MODELS = {
    # критический креатив (хук, концепция) — лучший доступный «мозг»
    "creative": ["claude-sonnet-4-6", "gemini-2.0-flash", "deepseek-chat"],
    # массовый текст (подписи, хэштеги, описания) — самый дешёвый/бесплатный
    "bulk": ["gemini-2.0-flash", "deepseek-chat", "gpt-4o-mini", "claude-sonnet-4-6"],
}


def _has_key_for(model: str) -> bool:
    from core.ai_router import AI_ROUTING
    prov = AI_ROUTING.get(model, "")
    return bool(os.getenv({
        "anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY",
        "google": "GEMINI_API_KEY", "perplexity": "PERPLEXITY_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
    }.get(prov, ""), ""))


def pick_text_model(task: str = "bulk") -> str:
    """Самый дешёвый ДОСТУПНЫЙ провайдер под задачу (экономия токенов)."""
    for m in TEXT_TASK_MODELS.get(task, TEXT_TASK_MODELS["bulk"]):
        if _has_key_for(m):
            return m
    return "gemini-2.0-flash"  # ai_router сам уйдёт в фолбэк, если ключа нет


async def smart_text(task: str, system: str, prompt: str) -> str:
    """Текст через самый дешёвый подходящий провайдер."""
    from core.ai_router import ai_router
    model = pick_text_model(task)
    try:
        res = await ai_router.call(model, system, prompt)
        return res.get("text", "")
    except Exception:
        return ""


def free_image(prompt: str, vertical: bool = True) -> str:
    """Бесплатная картинка (Pollinations, безлимит). 0 токенов, 0 денег."""
    w, h = ("1080", "1920") if vertical else ("1080", "1080")
    return (f"https://image.pollinations.ai/prompt/{quote(prompt[:480])}"
            f"?width={w}&height={h}&nologo=true&enhance=true")


async def higgsfield_reel(motion_prompt: str, seed_image: str = None,
                          fallback_image_prompt: str = "") -> dict:
    """СКИЛЛ HiggsField: анимация Reels из БЕСПЛАТНОГО сид-кадра.

    Платим только за анимацию: сид-картинку берём бесплатно (Pollinations),
    HiggsField оживляет её. Промт движения короткий — экономим всё.
    """
    if not os.getenv("HIGGSFIELD_API_KEY"):
        return {"ok": False, "error": "HIGGSFIELD_API_KEY не задан"}
    from core.higgsfield import create_video, poll_video

    seed = seed_image or free_image(fallback_image_prompt or "dark cinematic AI tech, gold neon")
    motion = (motion_prompt or "slow cinematic push-in, subtle parallax, dynamic light")[:400]
    started = await create_video(prompt=motion, image_url=seed, ratio="9:16")
    if not started.get("ok"):
        return {"ok": False, "error": started.get("error", "higgsfield start failed")}
    done = await poll_video(started["job_id"])
    if done.get("ok"):
        return {"ok": True, "url": done["url"], "provider": "higgsfield", "seed": seed}
    return {"ok": False, "error": done.get("error", "higgsfield poll failed")}
