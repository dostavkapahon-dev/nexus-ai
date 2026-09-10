"""
Аудит имён переменных окружения: заданное ≠ прочитанное.

Больная точка, которая повторялась. Человек добавляет ключ в переменные
хостинга, видит его в списке и считает, что интеграция подключена. Система же
читает переменную с ДРУГИМ именем и ключа не видит вовсе — снаружи это выглядит
как «ключ есть, а ничего не работает», и чинить начинают код, а не имя.

Здесь проверка ровно на это: какие заданные переменные явно метили в известную
интеграцию, но названы не так, как их читает код.

Чего эта проверка НЕ делает:
  * не угадывает по похожести. Совпадение либо по явному псевдониму из списка
    ниже, либо по имени бренда в начале канонического имени. Догадка вроде
    «DB → DATABASE_URL» ошибётся ровно тогда, когда цена ошибки высока;
  * не читает и не показывает ЗНАЧЕНИЯ — только имена;
  * не трогает системные переменные хостинга (PATH, PORT, RENDER_*).
"""
import os

# Переменные, которые действительно читает код. Ключи провайдеров подтягиваются
# из роутера, чтобы список не разошёлся с реальностью при добавлении провайдера.
BASE_CANONICAL = {
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY",
    "PERPLEXITY_API_KEY", "MISTRAL_API_KEY",
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_POST_CHAT_ID",
    "INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_ACCOUNT_ID", "INSTAGRAM_APP_SECRET",
    "TIKTOK_ACCESS_TOKEN", "VK_ACCESS_TOKEN", "VK_GROUP_ID",
    "THREADS_ACCESS_TOKEN", "YOUTUBE_API_KEY",
    "HIGGSFIELD_API_KEY", "HIGGSFIELD_SECRET", "HIGGSFIELD_MCP_URL",
    "HIGGSFIELD_MCP_TOKEN", "HIGGSFIELD_MODEL",
    "HEYGEN_API_KEY", "RUNWAY_API_KEY", "ELEVENLABS_API_KEY", "STABILITY_API_KEY",
    "BRIGHTDATA_API_KEY", "DATABASE_URL", "ADMIN_PASSWORD",
    "IG_HANDLE", "TIKTOK_HANDLE", "YOUTUBE_HANDLE",
}

# Псевдонимы, которые люди пишут по привычке. Только явные, без угадывания.
# Пустое значение — переменная известна, но код её больше не использует.
ALIASES = {
    "qroc": "GROQ_API_KEY",          # опечатка в «groq», встречается часто
    "groq": "GROQ_API_KEY",
    "gpt": "OPENAI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "google": "GEMINI_API_KEY",
    "telegram": "TELEGRAM_BOT_TOKEN",
    "higgsfield": "HIGGSFIELD_API_KEY",
    "hixiit": "HIGGSFIELD_API_KEY",
    "ayrshare": "",                  # заменён бесплатной разведкой social_intel
}

# У бренда бывает несколько переменных. Здесь — та, которую человек почти всегда
# и имеет в виду, когда пишет просто «instagram»: без неё интеграция не работает
# вовсе, тогда как ID и секрет вторичны.
PREFERRED_BY_BRAND = {
    "instagram": "INSTAGRAM_ACCESS_TOKEN",
    "telegram": "TELEGRAM_BOT_TOKEN",
    "higgsfield": "HIGGSFIELD_API_KEY",
    "tiktok": "TIKTOK_ACCESS_TOKEN",
    "vk": "VK_ACCESS_TOKEN",
    "threads": "THREADS_ACCESS_TOKEN",
    "youtube": "YOUTUBE_API_KEY",
    "brightdata": "BRIGHTDATA_API_KEY",
}

# Переменные хостинга и системы: они не наши и в отчёт не попадают.
IGNORE_PREFIXES = ("RENDER_", "PYTHON", "LC_", "LD_", "XDG_", "NEXUS_",
                   "PLAYWRIGHT_", "GOOGLE_", "FACEBOOK_", "AWS_", "npm_")
IGNORE_EXACT = {"PATH", "HOME", "PORT", "PWD", "SHELL", "USER", "LANG", "TERM",
                "HOSTNAME", "TZ", "TMPDIR", "SHLVL", "_"}


# Метка «имя недописано, вариантов несколько» — угадывать за человека нельзя.
AMBIGUOUS = "\x00ambiguous:"


def canonical() -> set:
    """Имена, которые код действительно читает."""
    names = set(BASE_CANONICAL)
    try:
        from core.ai_router import PROVIDER_KEY_ENV
        names.update(v for v in PROVIDER_KEY_ENV.values() if v)
    except Exception:
        pass
    return names


def _brand(name: str) -> str:
    """Бренд из канонического имени: INSTAGRAM_ACCESS_TOKEN → instagram."""
    return name.split("_")[0].lower()


def _match(given: str, known: set) -> str | None:
    """Каноническое имя, в которое метила эта переменная. None — не метила.

    Возвращает пустую строку, если переменная известна, но больше не нужна.
    """
    low = given.strip().lower()
    if low in ALIASES:
        return ALIASES[low]

    # GEMINI_API_KEY1 → GEMINI_API_KEY: лишний символ в конце.
    flat = "".join(ch for ch in low if ch.isalnum())
    for name in known:
        if flat.startswith("".join(ch for ch in name.lower() if ch.isalnum())):
            return name

    # «instagram» → INSTAGRAM_ACCESS_TOKEN: имя переменной = бренд целиком.
    # Проверяется РАНЬШЕ поиска по префиксу: у бренда переменных несколько, и
    # без этого правила «instagram» выдавалось бы за неоднозначное имя, хотя
    # человек почти наверняка имел в виду токен.
    if low in PREFERRED_BY_BRAND:
        return PREFERRED_BY_BRAND[low]

    # HIGGSFIELD_MCP → HIGGSFIELD_MCP_URL: имя, наоборот, недописано. Раньше
    # такие проходили мимо проверки: ловились только имена длиннее правильного.
    # Требуем, чтобы обрыв пришёлся на границу слова — иначе «TELEG» ловило бы
    # половину таблицы по случайному совпадению букв.
    upper = given.strip().upper()
    prefixed = sorted(n for n in known
                      if n.startswith(upper) and n[len(upper):].startswith("_"))
    if len(prefixed) == 1:
        return prefixed[0]
    if len(prefixed) > 1:
        # Несколько подходящих — угадывать нельзя, но и молчать нельзя:
        # называем все варианты, выбор за человеком.
        return AMBIGUOUS + ", ".join(prefixed)
    # На бренд может приходиться несколько переменных (ID, секрет, токен).
    # Берём первую по алфавиту, иначе подсказка меняется от запуска к запуску.
    same_brand = sorted(n for n in known if _brand(n) == low)
    return same_brand[0] if same_brand else None


def misnamed(environ: dict = None) -> list:
    """Заданные переменные, которые код не прочитает под этим именем."""
    env = environ if environ is not None else os.environ
    known = canonical()
    out = []
    for given in env:
        if given in known or given in IGNORE_EXACT:
            continue
        if any(given.startswith(p) for p in IGNORE_PREFIXES):
            continue
        target = _match(given, known)
        if target is None:
            continue                      # чужая переменная — не наше дело
        if target.startswith(AMBIGUOUS):
            out.append({"given": given, "expected": "",
                        "note": "имя недописано, подходит: "
                                + target[len(AMBIGUOUS):]})
        elif target == "":
            out.append({"given": given, "expected": "",
                        "note": "система больше не использует — можно удалить"})
        else:
            out.append({"given": given, "expected": target,
                        "note": f"переименуйте в {target}"})
    return sorted(out, key=lambda x: x["given"].lower())


def as_lines(items: list) -> list:
    """Строки для Telegram. Значения не показываем — только имена."""
    if not items:
        return []
    lines = ["", "⚠️ <b>Заданы, но не читаются</b> (имя не то, что ждёт код):"]
    for it in items:
        lines.append(f"   <code>{it['given']}</code> → {it['note']}")
    return lines
