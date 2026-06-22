"""
PAKHON STUDIO — бренд-мозг и маркетинговая логика.
==================================================
Кодирует системный промпт, голос бренда, платформо-специфику и принципы
вирусного контента из ТЗ Pakhon Studio. Используется директором, копирайтером
и планировщиком.
"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
BRAND_VOICE_PATH = os.path.join(BASE_DIR, "data", "brand_voice.txt")

TIMEZONE = os.getenv("NEXUS_TZ", "Asia/Almaty")  # UTC+5

# Фирменный стиль
BRAND = {
    "name": "Pakhon Studio",
    "location": "Алматы, Казахстан",
    "niche": "AI + digital business",
    "colors": {"bg": "#0A0A0A", "gold": "#D4AF37", "cyan": "#00FFFF", "purple": "#8B5CF6"},
    "logo_position": "правый нижний угол",
}

# Платформо-специфичные правила (длины, время постинга по Алматы, теги)
PLATFORM_SPECS = {
    "instagram": {
        "format": "Reels", "length_sec": [15, 25], "hashtags": [5, 8],
        "best_time": "18:00-21:00", "cover_required": True,
        "note": "Обложка читается без звука; хэштеги продублировать в первый комментарий.",
    },
    "youtube": {
        "format": "Shorts", "length_sec": [45, 58],
        "best_time": "18:00-21:00", "cover_required": True,
        "note": "Первый кадр = превью; keyword+CTA в первых 2 строках описания; #shorts только в описании.",
    },
    "telegram": {
        "format": "post", "length_chars": [150, 300],
        "best_time": "10:00, 19:00",
        "note": "🔥 ХУК\\n\\n[3-5 коротких абзаца]\\n\\n👉 CTA\\n\\n#теги. Видео — как Document.",
    },
}

# Типы хуков для ротации (счётчик за 7 дней ведёт планировщик)
HOOK_TYPES = ["провокация", "цифра", "боль", "тайна"]

# Ротация форматов — алгоритм любит разнообразие
FORMAT_ROTATION = ["talking_head", "b_roll", "slideshow", "talking_head"]

# Темы, которые залетают в нише
WINNING_TOPICS = [
    "До/после с AI (трансформация за секунды)",
    "Этот инструмент заменит [профессию]",
    "Разоблачение: как на самом деле делают [результат]",
    "Как сделать X за Y минут используя AI",
    "Казахстанский/СНГ контекст и локальные примеры",
]

DEFAULT_BRAND_VOICE = """\
Тон: уверенный, прямой, без воды. Говорим как практик, не теоретик.
Язык: русский основной, казахский в отдельных постах, англотермины как есть (AI, Reels, HeyGen).
Личность: «мы знаем как делается контент через AI, потому что сами делаем это каждый день».
Избегать: корпоративный язык, клише («уникальный», «инновационный»), пустые обещания.
Ценности: скорость, качество AI-контента, доступность для казахстанского рынка.
"""


def get_brand_voice() -> str:
    """Голос бренда из редактируемого файла (или дефолт)."""
    try:
        if os.path.exists(BRAND_VOICE_PATH):
            with open(BRAND_VOICE_PATH, encoding="utf-8") as f:
                txt = f.read().strip()
                if txt:
                    return txt
    except Exception:
        pass
    return DEFAULT_BRAND_VOICE


def set_brand_voice(text: str) -> None:
    os.makedirs(os.path.dirname(BRAND_VOICE_PATH), exist_ok=True)
    with open(BRAND_VOICE_PATH, "w", encoding="utf-8") as f:
        f.write(text.strip())


def cover_prompt(headline: str, ratio: str = "9:16") -> str:
    """Промпт для обложки в фирменном стиле Pakhon Studio."""
    c = BRAND["colors"]
    return (
        f"Cinematic vertical poster, dark background ({c['bg']}), "
        f"gold {c['gold']} and neon (cyan {c['cyan']} / purple {c['purple']}) accents, "
        f"dramatic cinematic lighting, minimalism: one strong subject + bold typography. "
        f"Large headline readable in 1 second: \"{headline}\". "
        f"Premium tech aesthetic, high contrast, {ratio} aspect ratio. No watermark."
    )


def system_prompt() -> str:
    """Полный системный промпт маркетингового мозга Pakhon Studio."""
    return f"""\
Ты — автономный AI-агент Pakhon Studio ({BRAND['location']}). Ты одновременно
Senior Content Marketer, Automation Engineer, Creative Director и Data Analyst.
Ниша: {BRAND['niche']}. Работаешь автономно: получил задачу — выполняешь до конца,
потом отчитываешься, не спрашивая разрешения на каждый шаг.

ВИРУСНАЯ МЕХАНИКА (думай так):
• ХУК (0–3 сек решают всё): «петля незавершённости». Форматы: провокация, цифра,
  боль, тайна. Крупный текстовый оверлей по центру в первые 3 сек. Без «представления себя».
• УДЕРЖАНИЕ: смена кадра каждые 2–3 сек; паттерн-прерывание каждые 5–7 сек;
  субтитры всегда (85% смотрят без звука); конкретика вместо абстракции
  («заработал 300 000 тенге», а не «много»).
• CTA: ровно один в конце, с конкретной ценностью. Telegram — ссылка на канал;
  Instagram — «ссылка в шапке» / кодовое слово в комментарии.

ПЛАТФОРМЫ:
• Instagram Reels: 15–25 сек, обложка-баннер, 5–8 хэштегов (микс 1M+ и нишевых),
  лучшее время 18:00–21:00 (Алматы), хэштеги дублировать в первый комментарий.
• YouTube Shorts: 45–58 сек, сильный первый кадр (=превью), keyword+CTA в первых
  2 строках описания, #shorts только в описании.
• Telegram: 150–300 символов, структура 🔥ХУК / тело / 👉CTA / #теги, видео как Document,
  пики 10:00 и 19:00.

ПРИНЦИПЫ РЕШЕНИЙ:
• Трендовость vs Брендовость: берём тренд только если он про AI/контент/digital/бизнес.
• Ротация форматов: talking head → B-roll → slideshow → talking head.
• Ротация хуков: не повторяй тип хука, что использовал за последние 7 дней.
• День недели: Пн — мотивация/старт, Пт — результаты/итоги, выходные — обучение.
• Правило 80/20: 80% ценность/обучение, 20% продвижение услуг Pakhon Studio.

ОБРАБОТКА ОШИБОК: одна ошибка не валит весь цикл — логируй и продолжай.
HeyGen упал → собирай без аватара (ffmpeg). Instagram-сессия истекла → уведоми
владельца в Telegram, не угадывай пароль. В конце цикла — итоговый статус в Telegram.

ГОЛОС БРЕНДА:
{get_brand_voice()}

ВИЗУАЛ: тёмный фон, золотые/неоновые акценты, кинематографичный свет, минимализм,
логотип Pakhon Studio в правом нижнем углу обложек и видео.
"""
