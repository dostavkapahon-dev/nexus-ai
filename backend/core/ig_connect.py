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


async def connect(token: str, account_id: str = "") -> dict:
    """Подключает Instagram по готовому токену: определяет тип, находит id, сохраняет."""
    token = (token or "").strip()
    if not token:
        return {"ok": False, "error": "пустой токен"}

    detected = await _try_instagram(token) or await _try_facebook(token)
    if not detected:
        return {"ok": False,
                "error": "Meta не приняла токен: он неверный, истёк или выдан "
                         "для другого приложения. Сгенерируйте новый в панели Meta."}

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
