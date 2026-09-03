"""
Создание контента без единого ключа: «нечем генерировать» — не повод молчать.

Когда не отвечает ни одна модель, система всё равно способна собрать рабочую
заготовку: хук по проверенным формулам, структура ролика по секундам, подпись с
призывом, кадры бесплатным генератором картинок и слайд-шоу из них. Это не
заменяет модель — это разница между «ничего» и «черновик, который можно
доработать руками за пять минут».

Ничего не выдумываем про качество: результат честно помечен как офлайн-заготовка.
"""
from core.skills import free_image

# Формулы хуков, работающие без «понимания» темы: тема подставляется как есть.
HOOKS = [
    "Вы делаете это неправильно: {topic}",
    "{topic} — за 15 секунд объясняю главное",
    "Никто не говорит правду про {topic}",
    "3 ошибки в теме «{topic}», которые видно сразу",
    "Как выглядит {topic}, когда всё сделано правильно",
]

# Каркас короткого ролика: секунды и назначение кадра.
SHOTS = [
    ("0-3", "Хук крупным планом", "cinematic close-up, {topic}, bold text overlay"),
    ("3-7", "Показ проблемы", "{topic}, problem shown clearly, dramatic lighting"),
    ("7-12", "Решение в действии", "{topic}, process in action, dynamic angle"),
    ("12-15", "Результат и призыв", "{topic}, satisfying final result, warm light"),
]

CTA = "Сохраните, чтобы не потерять. Пишите в директ — расскажем подробнее."


def draft(topic: str, platform: str = "instagram", kind: str = "video") -> dict:
    """Заготовка контента без обращения к моделям."""
    # Тема может приехать с довеском: конвейер подмешивает в неё память агента и
    # рецепты разведки. Человеку в хук нужна только первая строка — его тема.
    topic = (topic or "").split("\n")[0].split("[")[0].strip() or "ваша тема"
    hook = HOOKS[len(topic) % len(HOOKS)].format(topic=topic)

    storyboard = [{"t": t, "overlay": overlay.format(topic=topic),
                   "image_prompt": prompt.format(topic=topic)}
                  for t, overlay, prompt in SHOTS]

    caption = (f"{hook}\n\n"
               f"Разбираем «{topic}» по шагам: что не работает, почему и как "
               f"сделать иначе.\n\n{CTA}")

    return {
        "theme": topic,
        "hook_text": hook,
        "offline": True,
        "note": "Заготовка собрана без моделей ИИ — текст стоит доработать.",
        "storyboard": storyboard if kind == "video" else [],
        "cover_prompt": f"cinematic photo, {topic}, vertical, high detail",
        "caption": caption,
        "platform": platform,
    }


async def build(topic: str, platform: str = "instagram", kind: str = "video") -> dict:
    """Заготовка + бесплатные картинки, а для ролика — слайд-шоу из кадров."""
    plan = draft(topic, platform, kind)

    cover = free_image(plan["cover_prompt"])
    frames = [{"t": s["t"], "overlay": s["overlay"], "image": free_image(s["image_prompt"])}
              for s in plan["storyboard"]]

    assets = {"cover": cover, "frames": frames}
    if kind == "video" and frames:
        from core.video_assembly import assemble_slideshow
        video = await assemble_slideshow(frames, cta_text=plan["hook_text"][:40])
        assets["video"] = video
        if not video.get("ok"):
            # ffmpeg может отсутствовать на бесплатном тарифе — тогда остаются
            # кадры и подпись, и это надо сказать прямо, а не выдать за ролик.
            plan["note"] += f" Видео не собрано: {video.get('error', 'нет ffmpeg')}."

    return {"ok": True, "offline": True, "plan": plan, "assets": assets}
