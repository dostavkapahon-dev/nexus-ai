"""Task Specification: что именно человек попросил — одной структурой.

§6 ТЗ. До этого свободная фраза теряла почти всё, кроме темы: маршрутизатор
превращал «сделай вертикальное фото шашлыка для Instagram подешевле» в
`/factory шашлыка для Instagram подешевле`. Площадка, вид контента, формат,
режим качества и явный выбор модели просто исчезали — и дальше по цепочке
каждый шаг угадывал их заново, каждый по-своему.

Здесь фраза разбирается один раз, и дальше все шаги берут параметры отсюда.
Разбор — правилами, без вызова модели: он должен работать и когда ключей нет,
и стоить ноль. Что не сказано — остаётся None, а не выдуманным значением
(§8: не додумывать критические параметры).
"""
import re

from core import formats

# Вид контента. Порядок важен: «фото для рилс» — это всё-таки кадр, поэтому
# видео-слова проверяются после фото-слов только при явном «фото/кадр».
IMAGE_WORDS = ("фото", "фотограф", "изображен", "картинк", "кадр", "снимок",
               "обложк", "image", "photo", "постер", "баннер")
VIDEO_WORDS = ("видео", "ролик", "рилс", "reels", "reel", "shorts", "шортс",
               "клип", "video")
POST_WORDS = ("пост", "текст поста", "подпись", "caption")
CAROUSEL_WORDS = ("карусель", "карусел", "carousel", "слайд")
STORY_WORDS = ("сторис", "сторя", "stories", "story")

# Площадки: как человек их называет → ключ из core.formats.
PLATFORM_WORDS = {
    "instagram": ("инстаграм", "инста", "instagram", "ig", "рилс", "reels"),
    "tiktok": ("тикток", "tiktok", "тик-ток"),
    "shorts": ("шортс", "shorts", "ютуб шортс"),
    "youtube": ("ютуб", "youtube", "ютьюб"),
    "vk": ("вконтакте", "вк ", " вк", "vk "),
    "telegram": ("телеграм", "telegram", "тг "),
}

# Режимы качества — те же, что у роутера (§16), чтобы не заводить второй список.
QUALITY_WORDS = {
    "quality": ("максимально качествен", "максимальное качество", "самое лучшее",
                "лучшее качество", "покачественнее", "premium", "как можно лучше"),
    "economy": ("подешевле", "дешевле", "дёшево", "дешево", "экономно",
                "минимум кредитов", "бюджетно", "не трать"),
    "fast": ("побыстрее", "быстрее", "как можно быстрее", "срочно", "быстро"),
}

# Канал выполнения, если человек назвал его сам (§14: MODEL ≠ PROVIDER ≠ CHANNEL).
CHANNEL_WORDS = {
    "mcp": ("через mcp", "по mcp"),
    "api": ("через api", "по api", "по ключу"),
    "browser": ("через браузер", "в браузере", "браузером"),
}

# Явно названная модель. Список — только для распознавания слова в фразе;
# годится ли модель на самом деле, решает реестр моделей, а не этот разбор.
MODEL_WORDS = ("kling", "seedance", "soul", "nano banana", "nano_banana",
               "seedream", "veo", "hailuo", "sora", "gpt image", "imagen",
               "cinematic", "marketing studio")

RATIO_WORDS = {
    "9:16": ("вертикал", "9:16", "вертикально", "портрет"),
    "16:9": ("горизонтал", "16:9", "широкоформат", "landscape"),
    "1:1": ("квадрат", "1:1", "square"),
    "4:5": ("4:5",),
}

# Слова, которые в теме не нужны: это указания системе, а не предмет съёмки.
# Предлоги и связки: сами по себе темой не бывают.
_PREP = "про|о|об|для|на|в|с|и|а|но|по|из|от"

_STRIP = ("сделай", "создай", "сгенерируй", "нарисуй", "нужно", "нужен",
          "нужна", "хочу", "пожалуйста", "мне")


def _kind(low: str) -> str | None:
    if any(w in low for w in CAROUSEL_WORDS):
        return "carousel"
    if any(w in low for w in STORY_WORDS):
        return "stories"
    if any(w in low for w in IMAGE_WORDS):
        return "image"
    if any(w in low for w in VIDEO_WORDS):
        return "video"
    if any(w in low for w in POST_WORDS):
        return "post"
    return None


def _platform(low: str) -> str | None:
    for key, words in PLATFORM_WORDS.items():
        if any(w in low for w in words):
            return key
    return None


def _quality(low: str) -> str | None:
    # Порядок проверки — от самого дорогого требования к самому дешёвому:
    # «максимально качественно, но побыстрее» — это всё-таки про качество.
    for mode in ("quality", "economy", "fast"):
        if any(w in low for w in QUALITY_WORDS[mode]):
            return mode
    return None


def _channel(low: str) -> str | None:
    for key, words in CHANNEL_WORDS.items():
        if any(w in low for w in words):
            return key
    return None


def _model(low: str) -> str | None:
    for w in MODEL_WORDS:
        if w in low:
            return w
    return None


def _ratio(low: str) -> str | None:
    for ratio, words in RATIO_WORDS.items():
        if any(w in low for w in words):
            return ratio
    return None


def _seconds(low: str) -> int | None:
    m = re.search(r"(\d{1,3})\s*(?:сек|секунд|s\b|сек\.)", low)
    if m:
        return max(3, min(int(m.group(1)), 180))
    m = re.search(r"(\d{1,2})\s*(?:мин|минут)", low)
    if m:
        return max(3, min(int(m.group(1)) * 60, 180))
    return None


def _count(low: str) -> int:
    m = re.search(r"(\d{1,2})\s*(?:вариант|штук|шт\b|ролик|рилс|reels|кадр|фото|видео)",
                  low)
    if not m:
        return 1
    return max(1, min(int(m.group(1)), 10))


def subject_of(text: str) -> str:
    """Тема — то, ЧТО снимаем. Служебные слова из неё вычищаются.

    Тема остаётся в исходном регистре: «шашлык по-карски» в промпте должен
    выглядеть так, как его написал человек.

    Вычеркнутое место помечается меткой, и предлог рядом с меткой («на» от
    «на 20 секунд», «для» от «для Instagram») уходит вместе с ней. Без этого
    в теме оставались огрызки вроде «шашлык на для», и они уезжали в промпт.
    """
    t = (text or "").strip()
    MARK = "\x00"

    def cut(pattern: str) -> None:
        nonlocal t
        t = re.sub(pattern, MARK, t, flags=re.IGNORECASE)

    # Сначала числа с единицами: «на 20 секунд», «5 вариантов».
    cut(r"\d{1,3}\s*(?:сек\w*|мин\w*|вариант\w*|штук\w*|шт\b|кадр\w*)")
    # Явно названная модель вместе с «используй».
    for w in MODEL_WORDS:
        cut(rf"(?:использ\w*\s+)?{re.escape(w)}\w*")
    for group in (QUALITY_WORDS, CHANNEL_WORDS, RATIO_WORDS):
        for words in group.values():
            for w in words:
                cut(rf"{re.escape(w)}\w*")
    for words in PLATFORM_WORDS.values():
        for w in words:
            cut(rf"{re.escape(w.strip())}\w*")
    for group in (IMAGE_WORDS, VIDEO_WORDS, POST_WORDS, CAROUSEL_WORDS,
                  STORY_WORDS, _STRIP):
        for w in group:
            cut(rf"(?<!\w){re.escape(w)}\w*")

    # Предлог, оставшийся без своего слова, — тоже мусор.
    for _ in range(3):
        t = re.sub(rf"(?<!\w)(?:{_PREP})\s*{MARK}", MARK, t, flags=re.IGNORECASE)
        t = re.sub(rf"{MARK}\s*(?:{_PREP})(?!\w)", MARK, t, flags=re.IGNORECASE)
    t = t.replace(MARK, " ")
    t = re.sub(r"^\s*(?:про|о|об|на тему|для)\s+", " ", t.strip(" .,!?—-"),
               flags=re.IGNORECASE)
    t = re.sub(rf"(?<!\w)(?:{_PREP})\s*$", " ", t.strip(), flags=re.IGNORECASE)
    t = re.sub(r"\s{2,}", " ", t).strip(" .,!?—-:")
    return t


def parse(text: str, kind: str = None, platform: str = None) -> dict:
    """Разбор фразы в спецификацию задачи.

    `kind` и `platform` — то, что человек уже выбрал кнопками: явный выбор
    главнее разбора текста, иначе нажатие «🖼 Изображение» ничего не значило бы.
    """
    raw = (text or "").strip()
    low = raw.lower()

    resolved_kind = kind or _kind(low) or "video"
    resolved_platform = platform or _platform(low)
    # Формат: сказанное словами → требование площадки → вертикаль по умолчанию.
    ratio = _ratio(low)
    if not ratio and resolved_platform:
        ratio = formats.ratio_for(resolved_platform, resolved_kind)

    seconds = _seconds(low)
    if seconds is None and resolved_kind == "video" and resolved_platform:
        seconds = formats.seconds_for(resolved_platform, "video")

    return {
        "request": raw,
        "subject": subject_of(raw),
        "kind": resolved_kind,
        "platform": resolved_platform,
        "ratio": ratio,
        "seconds": seconds,
        "count": _count(low),
        "quality": _quality(low),
        "channel": _channel(low),
        "model": _model(low),
    }


KIND_NAMES = {"image": "Изображение", "video": "Видео", "post": "Пост",
              "carousel": "Карусель", "stories": "Stories"}
QUALITY_NAMES = {"quality": "качество", "economy": "экономно", "fast": "быстро"}


def as_text(spec: dict) -> str:
    """Что система поняла — человеку, до запуска.

    §72: «понял задачу» нельзя показывать словом «ок». Видно должно быть
    ровно то, что уйдёт в генерацию, чтобы ошибку разбора было заметно
    до траты кредитов, а не после.
    """
    kind = spec.get("kind", "video")
    lines = [f"📋 <b>{KIND_NAMES.get(kind, kind)}</b>: "
             f"{spec.get('subject') or 'тема по трендам'}"]
    where = spec.get("platform")
    parts = []
    if where:
        parts.append(dict(formats.PLATFORMS).get(where, where))
    if spec.get("ratio"):
        parts.append(spec["ratio"])
    if spec.get("seconds"):
        parts.append(f"{spec['seconds']} сек")
    if spec.get("count", 1) > 1:
        parts.append(f"{spec['count']} шт")
    if parts:
        lines.append("Формат: " + " · ".join(parts))
    choice = []
    if spec.get("quality"):
        choice.append(QUALITY_NAMES[spec["quality"]])
    if spec.get("model"):
        choice.append(f"модель {spec['model']}")
    if spec.get("channel"):
        choice.append(f"канал {spec['channel']}")
    if choice:
        lines.append("Выбор: " + ", ".join(choice))
    return "\n".join(lines)
