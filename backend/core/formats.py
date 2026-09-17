"""Формат кадра и ролика определяет площадка, а не случайное слово в задаче.

Раньше это решалось в трёх местах по-разному и все три были неверны:
`media_generator` считал вертикальным всё, кроме телеграма (и потому рисовал
горизонтальный YouTube вертикально, а пост в Instagram — квадратом),
`content_factory` вообще не смотрел на выбранную площадку и всегда просил
кадр «для instagram», а длительность ролика не была привязана к площадке
никак — Shorts и Reels резались уже после генерации.

Здесь один источник правды: площадка + вид контента → соотношение сторон,
размер, длительность и предел подписи. Значения — требования самих площадок.
"""

# Ключ — «площадка/вид». Вид: image (кадр, пост, карусель) или video.
#
# seconds — рабочая длительность, max_seconds — потолок площадки. Мы генерируем
# по рабочей: ролик, который площадка обрежет, — это выброшенные кредиты.
SPECS: dict[str, dict] = {
    "instagram/video":   {"ratio": "9:16", "seconds": 15, "max_seconds": 90,
                          "caption": 2200, "name": "Reels"},
    "instagram/image":   {"ratio": "4:5", "seconds": 0, "max_seconds": 0,
                          "caption": 2200, "name": "пост в ленте"},
    "instagram/stories": {"ratio": "9:16", "seconds": 15, "max_seconds": 60,
                          "caption": 0, "name": "Stories"},
    "tiktok/video":      {"ratio": "9:16", "seconds": 15, "max_seconds": 180,
                          "caption": 2200, "name": "TikTok"},
    "tiktok/image":      {"ratio": "9:16", "seconds": 0, "max_seconds": 0,
                          "caption": 2200, "name": "фотопост TikTok"},
    "youtube/video":     {"ratio": "16:9", "seconds": 60, "max_seconds": 0,
                          "caption": 5000, "name": "YouTube"},
    "youtube/image":     {"ratio": "16:9", "seconds": 0, "max_seconds": 0,
                          "caption": 5000, "name": "обложка YouTube"},
    "shorts/video":      {"ratio": "9:16", "seconds": 30, "max_seconds": 180,
                          "caption": 5000, "name": "YouTube Shorts"},
    "shorts/image":      {"ratio": "9:16", "seconds": 0, "max_seconds": 0,
                          "caption": 5000, "name": "обложка Shorts"},
    "vk/video":          {"ratio": "9:16", "seconds": 15, "max_seconds": 180,
                          "caption": 4000, "name": "VK Клипы"},
    "vk/image":          {"ratio": "1:1", "seconds": 0, "max_seconds": 0,
                          "caption": 4000, "name": "пост VK"},
    "telegram/video":    {"ratio": "9:16", "seconds": 15, "max_seconds": 0,
                          "caption": 1024, "name": "видео в Telegram"},
    "telegram/image":    {"ratio": "1:1", "seconds": 0, "max_seconds": 0,
                          "caption": 1024, "name": "пост в Telegram"},
}

# Что показывать кнопками. Порядок — по тому, как часто это нужно.
PLATFORMS = [
    ("instagram", "Instagram"),
    ("tiktok", "TikTok"),
    ("shorts", "YouTube Shorts"),
    ("youtube", "YouTube"),
    ("vk", "VK"),
    ("telegram", "Telegram"),
]

DEFAULT = {"ratio": "9:16", "seconds": 15, "max_seconds": 0,
           "caption": 2200, "name": "вертикальный формат"}

# Соотношение → пиксели. Те же значения принимает Higgsfield (core.higgsfield.SIZES),
# но здесь они нужны и тем путям, которые ходят мимо него.
PIXELS = {
    "9:16": "1080x1920",
    "16:9": "1920x1080",
    "1:1": "1080x1080",
    "4:5": "1080x1350",
}


def _kind(kind: str) -> str:
    """Виды контента сводим к тем, для которых у площадок есть требования."""
    if kind in ("video", "reel", "reels", "clip"):
        return "video"
    if kind == "stories":
        return "stories"
    return "image"          # post, carousel, image, cover


def spec(platform: str, kind: str = "video") -> dict:
    """Требования площадки. Неизвестная площадка — вертикальный формат."""
    key = f"{(platform or '').strip().lower()}/{_kind(kind)}"
    return dict(SPECS.get(key) or DEFAULT)


def ratio_for(platform: str, kind: str = "video") -> str:
    return spec(platform, kind)["ratio"]


def size_for(platform: str, kind: str = "video") -> str:
    return PIXELS.get(ratio_for(platform, kind), PIXELS["9:16"])


def seconds_for(platform: str, kind: str = "video") -> int:
    return spec(platform, kind)["seconds"]


def describe(platform: str, kind: str = "video") -> str:
    """Строка для человека: что именно будет сделано и в каком формате.

    Показывается до генерации — чтобы «не тот формат» было видно до того,
    как потрачены кредиты, а не после.
    """
    s = spec(platform, kind)
    parts = [s["name"], s["ratio"]]
    if s["seconds"]:
        parts.append(f"{s['seconds']} сек")
    return " · ".join(parts)
