"""
Прямое подключение Instagram по готовому токену.

Пользователь уже получил токен в панели Meta (роль тестировщика, Standard Access) —
гонять его через OAuth незачем. Здесь он просто вставляет токен, а система сама
находит id аккаунта и запоминает, каким способом этот токен продлевать.

Почему тип токена важен. У Meta два разных семейства, и они несовместимы:
  • `facebook` — токен Страницы/пользователя, работает на graph.facebook.com,
    продлевается обменом `fb_exchange_token` (нужны App ID и App Secret);
  • `instagram` — токен Instagram Login, работает на graph.instagram.com,
    продлевается запросом `refresh_access_token` (App Secret не нужен).
Если применить не тот способ, продление молча не сработает, и через 60 дней
публикация встанет без объяснимой причины. Поэтому тип определяем сразу,
по факту — спрашиваем у обоих API, кто узнаёт этот токен.
"""
import httpx

GRAPH_FB = "https://graph.facebook.com/v19.0"
GRAPH_IG = "https://graph.instagram.com"

TYPE_KEY = "instagram_token_type"


async def _try_facebook(token: str) -> dict | None:
    """Токен Facebook: ищем Страницы пользователя и привязанный к ним Instagram."""
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(f"{GRAPH_FB}/me/accounts", params={
                "fields": "name,instagram_business_account", "access_token": token})
            data = r.json()
        if data.get("error"):
            return None
        for page in data.get("data") or []:
            iba = page.get("instagram_business_account") or {}
            if iba.get("id"):
                return {"type": "facebook", "account_id": iba["id"],
                        "page": page.get("name", "")}
        # Токен рабочий, но Instagram к Странице не привязан — это другая беда,
        # и сообщить о ней надо иначе, чем «токен не подошёл».
        return {"type": "facebook", "account_id": "", "page": "",
                "warning": "токен принят, но ни к одной Странице не привязан "
                           "Instagram Business/Creator аккаунт"}
    except Exception:
        return None


async def _try_instagram(token: str) -> dict | None:
    """Токен Instagram Login: аккаунт отвечает сам за себя."""
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(f"{GRAPH_IG}/me", params={
                "fields": "id,username", "access_token": token})
            data = r.json()
        if data.get("error") or not data.get("id"):
            return None
        return {"type": "instagram", "account_id": data["id"],
                "username": data.get("username", "")}
    except Exception:
        return None


def clean_token(raw: str) -> str:
    """Убирает из вставленного токена то, что ломает его при копировании.

    Панель Meta переносит длинный токен по строкам, и вместе с ним копируются
    переводы строк и пробелы. Meta на такой строке отвечает «Cannot parse access
    token» — по этому тексту невозможно догадаться, что дело в переносе.
    """
    t = (raw or "").strip().strip('"').strip("'")
    # Внутренние пробелы и переводы строк — всегда следствие копирования,
    # в самом токене их не бывает.
    return "".join(t.split())


def diagnose(token: str) -> str | None:
    """Ищет заведомо не-токен и называет вещь своим именем.

    Иначе пользователь получает от Meta «Cannot parse access token» и не понимает,
    что вставил App ID, обрезанную строку или вовсе не то поле.
    """
    if not token:
        return "поле пустое — вставьте токен из панели Meta"
    if "…" in token or "..." in token:
        return ("токен скопирован не полностью — в строке есть многоточие. "
                "В панели Meta нажмите «Copy» рядом с токеном, а не выделяйте мышью")
    if token.isdigit():
        return ("это App ID, а не токен. Токен — длинная строка, начинается "
                "с IGAA… или EAA…")
    if len(token) == 32 and all(c in "0123456789abcdefABCDEF" for c in token):
        return ("это App Secret, а не токен доступа. Токен длиннее и начинается "
                "с IGAA… или EAA…")
    if len(token) < 50:
        return (f"строка слишком короткая для токена ({len(token)} символов). "
                "Настоящий токен — сотни символов, начинается с IGAA… или EAA…")
    if not (token.startswith("IGAA") or token.startswith("EAA")):
        head = token[:6]
        return (f"токен начинается с «{head}…» — обычно это IGAA… (Instagram Login) "
                "или EAA… (Страница Facebook). Проверьте, что скопировали именно "
                "Access Token, а не другое поле")
    return None


async def connect(token: str, account_id: str = "") -> dict:
    """Подключает Instagram по готовому токену: определяет тип, находит id, сохраняет."""
    token = clean_token(token)

    # Сначала то, что видно без обращения к Meta: так пользователь получает
    # понятную причину вместо «Cannot parse access token».
    problem = diagnose(token)
    if problem:
        return {"ok": False, "error": problem}

    detected = await _try_instagram(token) or await _try_facebook(token)
    if not detected:
        return {"ok": False,
                "error": "Meta не приняла токен: он неверный, истёк или выдан "
                         "для другого приложения. Сгенерируйте новый в панели Meta "
                         "и скопируйте кнопкой «Copy» целиком."}

    resolved = account_id.strip() or detected.get("account_id", "")
    if not resolved:
        return {"ok": False, "type": detected["type"],
                "error": detected.get("warning") or
                         "не удалось определить Instagram Account ID — укажите его вручную"}

    from connectors.instagram import _save_key
    await _save_key("instagram_access_token", token)
    await _save_key("instagram_account_id", resolved)
    # Запоминаем тип: от него зависит способ продления через 60 дней.
    await _save_key(TYPE_KEY, detected["type"])

    return {"ok": True, "type": detected["type"], "account_id": resolved,
            "username": detected.get("username", ""), "page": detected.get("page", ""),
            "note": ("Токен сохранён. Продление настроено автоматически: "
                     + ("запрос refresh_access_token" if detected["type"] == "instagram"
                        else "обмен fb_exchange_token") + ", джоб в 08:00.")}
