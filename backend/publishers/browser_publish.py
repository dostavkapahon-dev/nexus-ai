"""
Мост: публикация через автономного браузерного агента.
Используется как fallback, когда нет официального API-токена площадки
(или площадка без API, напр. ручная публикация Stories/Reels).

Связывает контент-пайплайн NEXUS с desktop_agent.py через browser_agent.run_agent.
"""
from api.routes_desktop import desktop_connected

# Стартовые URL и шаблоны задач для браузерного агента по платформам.
_PLATFORM_FLOWS = {
    "instagram": {
        "start_url": "https://www.instagram.com/",
        "task": "Опубликуй новый пост в Instagram. Нажми кнопку создания поста (плюс), "
                "загрузи изображение, в поле подписи вставь следующий текст и опубликуй.",
    },
    "vk": {
        "start_url": "https://vk.com/",
        "task": "Создай новую запись на стене сообщества во ВКонтакте с этим текстом "
                "и прикреплённым изображением, затем опубликуй.",
    },
    "tiktok": {
        "start_url": "https://www.tiktok.com/upload",
        "task": "Открой загрузку видео в TikTok, добавь описание из текста ниже. "
                "Если видео нет — остановись и спроси файл.",
    },
    "youtube": {
        "start_url": "https://studio.youtube.com/",
        "task": "Открой YouTube Studio, начни загрузку Shorts, заполни заголовок и описание "
                "из текста ниже. Если видеофайла нет — остановись и спроси.",
    },
}


async def publish_via_browser(platform: str, text: str, image_url: str = None,
                              max_steps: int = 30) -> dict:
    """Публикует контент на платформе руками браузерного агента.

    Возвращает {'ok': bool, 'status'|'error', ...}. Требует запущенного
    desktop_agent.py на ПК пользователя с активной сессией площадки.
    """
    if not desktop_connected():
        return {"ok": False, "error": "Desktop agent не подключён. Запусти desktop_agent.py на ПК."}

    flow = _PLATFORM_FLOWS.get(platform)
    if not flow:
        return {"ok": False, "error": f"Нет браузерного сценария для платформы '{platform}'."}

    # Импорт здесь, чтобы избежать циклов при загрузке модуля.
    from core.browser_agent import run_agent

    task = (
        f"{flow['task']}\n\n--- ТЕКСТ ДЛЯ ПУБЛИКАЦИИ ---\n{text}\n"
    )
    if image_url:
        task += f"\nИзображение (URL): {image_url}\n"
    task += ("\nДействуй аккуратно, маленькими шагами, проверяя экран. "
             "Когда пост опубликован — вызови done. Если нужен ввод/файл — вызови ask.")

    result = await run_agent(task=task, start_url=flow["start_url"], max_steps=max_steps)
    ok = result.get("status") == "done"
    return {"ok": ok, **result}
