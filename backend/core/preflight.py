"""
Проверка готовности перед запуском: сможем ли мы это сделать прямо сейчас.

Раньше «Создать» всегда отвечало «запускаю», а конвейер молча падал на первом
шаге, если не было ни одного ключа ИИ. Со стороны это выглядит как «нажал —
ничего не происходит»: подсказка про ключ жила внутри отчёта, который в такой
ситуации мог и не дойти.

Здесь один вопрос — чего не хватает — и честный ответ до начала работы.
Различаем две вещи:
  * blockers — без этого начинать бессмысленно (конвейер упрётся сразу);
  * warnings — сделаем, но хуже (например, без видеогенератора соберём
    слайд-шоу вместо кинематографичного клипа).
"""
import os

VIDEO_KEYS = ("HEYGEN_API_KEY", "HIGGSFIELD_API_KEY", "RUNWAY_API_KEY")


async def check(kind: str = "video") -> dict:
    """Готовность к созданию контента вида `kind` (video|image|post|carousel)."""
    blockers: list[str] = []
    warnings: list[str] = []
    ready: list[str] = []

    # 1. Модель ИИ. Без неё нет ни темы, ни сценария, ни текста — то есть
    #    буквально нечего создавать, картинка одна погоды не сделает.
    from core.ai_router import available_providers, FREE_SIGNUP_HINT
    providers = available_providers()
    if providers:
        ready.append(f"ИИ: {', '.join(providers)}")
    else:
        # Без моделей работа не останавливается: собирается заготовка по
        # шаблонам с бесплатными картинками. Это хуже, но это результат, а не
        # отказ — поэтому предупреждение, а не блокировка.
        warnings.append("Нет ни одной модели ИИ — соберу заготовку по шаблону "
                        "(тексты стоит доработать).\n" + FREE_SIGNUP_HINT)

    # 2. Картинки. Бесплатный путь работает без ключей всегда, поэтому это не
    #    блокер ни при каких настройках.
    ready.append("Изображения: бесплатный генератор доступен")

    # 3. Видео — только для роликов.
    if kind == "video":
        from core.production_queue import producer, CLAUDE
        keys = [k for k in VIDEO_KEYS if os.getenv(k, "").strip()]
        if keys:
            ready.append("Видео: " + ", ".join(k.split("_")[0].title() for k in keys))
        elif await producer() == CLAUDE:
            ready.append("Видео: делает внешний исполнитель")
        else:
            warnings.append("Нет ключа видеогенератора (HeyGen / Higgsfield / "
                            "Runway) — соберу слайд-шоу из кадров.")

    # 4. Кому показывать результат.
    from core.telegram_owner import owner_id
    if await owner_id():
        ready.append("Согласование: Telegram подключён")
    else:
        warnings.append("Telegram не подключён — готовое будет видно только на сайте.")

    # 5. Переживёт ли результат перезапуск.
    from database.db import storage_info
    st = storage_info()
    if st["persistent"]:
        ready.append("База: постоянная")
    else:
        warnings.append("Временная база: созданное и ключи пропадут при "
                        "следующем перезапуске сервиса.")

    return {"ok": not blockers, "blockers": blockers,
            "warnings": warnings, "ready": ready}


def as_text(report: dict) -> str:
    """Отчёт словами — его показывают человеку в чате и в вебе."""
    lines = []
    if report.get("blockers"):
        lines.append("🚫 <b>Не могу начать:</b>")
        lines += [f"• {b}" for b in report["blockers"]]
    if report.get("warnings"):
        lines.append("\n⚠️ <b>Сделаю, но с оговорками:</b>")
        lines += [f"• {w}" for w in report["warnings"]]
    if report.get("ready"):
        lines.append("\n✅ <b>Готово к работе:</b>")
        lines += [f"• {r}" for r in report["ready"]]
    return "\n".join(lines)
