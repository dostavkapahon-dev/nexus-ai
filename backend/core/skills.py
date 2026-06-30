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

    Два пути:
      1) API-ключ HIGGSFIELD_API_KEY → прямой вызов API
      2) нет ключа, но подключён браузер-агент → генерация ЧЕРЕЗ ВАШ АККАУНТ
         higgsfield.ai руками агента (MCP/account-вход, без ключа)
    """
    seed = seed_image or free_image(fallback_image_prompt or "dark cinematic AI tech, gold neon")

    if not os.getenv("HIGGSFIELD_API_KEY"):
        # Путь через браузер-агента и ваш залогиненный аккаунт higgsfield.ai
        return await higgsfield_via_browser(motion_prompt or "", seed)

    from core.higgsfield import create_video, poll_video
    motion = (motion_prompt or "slow cinematic push-in, subtle parallax, dynamic light")[:400]
    started = await create_video(prompt=motion, image_url=seed, ratio="9:16")
    if not started.get("ok"):
        return {"ok": False, "error": started.get("error", "higgsfield start failed")}
    done = await poll_video(started["job_id"])
    if done.get("ok"):
        return {"ok": True, "url": done["url"], "provider": "higgsfield", "seed": seed}
    return {"ok": False, "error": done.get("error", "higgsfield poll failed")}


async def higgsfield_via_browser(motion_prompt: str, seed_image: str = None,
                                 max_steps: int = 32) -> dict:
    """Генерация видео ЧЕРЕЗ ВАШ аккаунт higgsfield.ai руками браузер-агента.

    Не нужен API-ключ: агент работает в вашем залогиненном браузере (start_agent.bat).
    Подходит, когда HiggsField даёт доступ только через аккаунт/MCP, без ключа.
    """
    from api.routes_desktop import desktop_connected
    if not desktop_connected():
        return {"ok": False, "provider": "higgsfield_browser",
                "error": "Браузер-агент не подключён. Запусти start_agent.bat и войди в higgsfield.ai."}

    from core.browser_agent import run_agent
    motion = (motion_prompt or "slow cinematic push-in, dynamic light, parallax")[:400]
    task = (
        "Ты в аккаунте higgsfield.ai (уже залогинен). Сгенерируй короткое вертикальное видео 9:16:\n"
        "1. Открой создание видео (image-to-video или text-to-video).\n"
        f"2. Вставь промт движения: {motion}\n"
        + (f"3. Если можно задать первый кадр по ссылке — используй: {seed_image}\n" if seed_image else "")
        + "4. Выбери формат 9:16 (вертикальный) и запусти генерацию.\n"
        "5. Дождись готовности: делай wait по 10-15 сек и периодически скриншоть, пока видео не появится.\n"
        "6. Когда готово — открой/скопируй ссылку на видео (кнопка Download/Share) и вызови done "
        "с этой ссылкой в summary. Если требуется оплата/кредиты или вход — вызови ask."
    )
    res = await run_agent(task=task, start_url="https://higgsfield.ai/create", max_steps=max_steps)
    ok = res.get("status") == "done"
    return {"ok": ok, "provider": "higgsfield_browser",
            "url": res.get("summary") if ok else None,
            "status": res.get("status"), "detail": res.get("summary") or res.get("question"),
            "steps": res.get("steps")}


async def higgsfield_photo(prompt: str, ratio: str = "1:1") -> dict:
    """СКИЛЛ HiggsField: генерация ФОТО (модель Soul) по текстовому описанию.

    Два пути (как и для видео):
      1) API-ключ HIGGSFIELD_API_KEY → прямой вызов API
      2) нет ключа, но подключён браузер-агент → генерация ЧЕРЕЗ ВАШ АККАУНТ
         higgsfield.ai руками агента (account-вход, без ключа)
    """
    if not os.getenv("HIGGSFIELD_API_KEY"):
        return await higgsfield_image_via_browser(prompt or "", ratio)

    from core.higgsfield import create_image, poll_image
    started = await create_image(prompt=(prompt or "")[:1000], ratio=ratio)
    if not started.get("ok"):
        return {"ok": False, "provider": "higgsfield", "error": started.get("error", "higgsfield image start failed")}
    done = await poll_image(started["job_id"])
    if done.get("ok"):
        return {"ok": True, "url": done["url"], "provider": "higgsfield"}
    return {"ok": False, "provider": "higgsfield", "error": done.get("error", "higgsfield image poll failed")}


async def higgsfield_image_via_browser(prompt: str, ratio: str = "1:1",
                                       max_steps: int = 32) -> dict:
    """Генерация ФОТО ЧЕРЕЗ ВАШ аккаунт higgsfield.ai руками браузер-агента.

    Не нужен API-ключ: агент работает в вашем залогиненном браузере (start_agent.bat).
    """
    from api.routes_desktop import desktop_connected
    if not desktop_connected():
        return {"ok": False, "provider": "higgsfield_browser",
                "error": "Браузер-агент не подключён. Запусти start_agent.bat и войди в higgsfield.ai."}

    from core.browser_agent import run_agent
    desc = (prompt or "cinematic realistic photo")[:600]
    vertical = ratio in ("9:16", "2:3", "3:4")
    task = (
        "Ты в аккаунте higgsfield.ai (уже залогинен). Сгенерируй ФОТО (image generation, модель Soul):\n"
        "1. Открой создание изображения (Soul / Image / text-to-image).\n"
        f"2. Вставь промт описания кадра: {desc}\n"
        f"3. Выбери формат {'9:16 (вертикальный)' if vertical else '1:1 (квадрат)'} и запусти генерацию.\n"
        "4. Дождись готовности: делай wait по 5-10 сек и периодически скриншоть, пока фото не появится.\n"
        "5. Когда готово — открой/скопируй ссылку на изображение (Download/Share) и вызови done "
        "с этой ссылкой в summary. Если требуется оплата/кредиты или вход — вызови ask."
    )
    res = await run_agent(task=task, start_url="https://higgsfield.ai/create", max_steps=max_steps)
    ok = res.get("status") == "done"
    return {"ok": ok, "provider": "higgsfield_browser",
            "url": res.get("summary") if ok else None,
            "status": res.get("status"), "detail": res.get("summary") or res.get("question"),
            "steps": res.get("steps")}
