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
    """Токен Facebook. Их тоже два вида, и проверять надо оба.

    `/me/accounts` перечисляет Страницы — это работает только для токена
    **пользователя**. Токен **Страницы** (а именно его выдаёт Graph API Explorer,
    и именно его просил старый интерфейс) на этот запрос отвечает ошибкой: у него
    нет «списка страниц», он сам и есть страница. Раньше такой токен получал
    «Meta не приняла токен», хотя был совершенно рабочим.
    """
    async def ask(path: str, fields: str):
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.get(f"{GRAPH_FB}/{path}",
                                params={"fields": fields, "access_token": token})
                return r.json()
        except Exception:
            return None

    alive, page_name = False, ""

    # 1. Токен пользователя: у него есть список Страниц.
    data = await ask("me/accounts", "name,instagram_business_account")
    if data and not data.get("error"):
        alive = True
        for page in data.get("data") or []:
            iba = page.get("instagram_business_account") or {}
            if iba.get("id"):
                return {"type": "facebook", "account_id": iba["id"],
                        "page": page.get("name", "")}
            page_name = page_name or page.get("name", "")

    # 2. Токен Страницы: списка страниц у него нет, спрашиваем саму страницу.
    me = await ask("me", "name,instagram_business_account")
    if me and not me.get("error"):
        alive = True
        iba = me.get("instagram_business_account") or {}
        if iba.get("id"):
            return {"type": "facebook", "account_id": iba["id"],
                    "page": me.get("name", "")}
        page_name = page_name or me.get("name", "")

    # Meta ответила хотя бы на один запрос — токен живой, но Instagram не привязан.
    # Это другая беда, и говорить о ней надо иначе, чем «токен не подошёл».
    if alive:
        return {"type": "facebook", "account_id": "", "page": page_name,
                "warning": "токен принят, но к Странице не привязан "
                           "Instagram Business/Creator аккаунт"}

    # Оба запроса отклонены — токен действительно не работает.
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


def fingerprint(token: str) -> str:
    """Безопасные приметы строки: длина и начало, без самого секрета.

    Настоящий токен Instagram Login — обычно 150–250 символов. Если пришло
    заметно меньше, строка почти наверняка обрезана при копировании, и это
    видно сразу — не нужно просить прислать токен (чего делать нельзя).
    """
    if not token:
        return "пусто"
    hint = ""
    if len(token) < 100:
        hint = " — подозрительно коротко, обычно 150–250"
    return f"начинается с «{token[:8]}», длина {len(token)}{hint}"


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
        # Приметы строки — без самого токена: по ним видно, дошла ли она целиком.
        # Иначе «Meta не приняла токен» одинаково для обрезанной строки, чужого
        # приложения и просроченного токена, и разбираться приходится перепиской.
        return {"ok": False,
                "error": "Meta не приняла токен: он неверный, истёк, отозван или "
                         "выдан для другого приложения. Сгенерируйте новый в панели "
                         "Meta и скопируйте кнопкой «Copy» целиком.",
                "token_looks_like": fingerprint(token)}

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


async def check_access() -> dict:
    """Что токен реально умеет — по операциям, а не по списку прав.

    «Токен принят» и «работает публикация» — разные вещи: Meta может принять
    токен, но отказать в чтении медиа или в публикации, если у аккаунта не тот
    тип или не выдано право. Права из `debug_token` тоже не ответ: они
    показывают запрошенное, а не то, что пройдёт на деле. Поэтому дёргаем сами
    операции и показываем ответ Meta по каждой.
    """
    from connectors import ig_api

    if not ig_api.configured():
        return {"ok": False, "error": "не задан токен Instagram — вставьте его на этой странице",
                "checks": []}

    tok = ig_api.token()

    async def probe(path: str, params: dict) -> tuple[bool, str, dict]:
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.get(ig_api.url(path), params={**params, "access_token": tok})
                d = r.json()
        except Exception as e:
            return False, f"сеть недоступна: {type(e).__name__}", {}
        if isinstance(d, dict) and d.get("error"):
            return False, str(d["error"].get("message", ""))[:160], {}
        return True, "", d if isinstance(d, dict) else {}

    checks, account = [], {}

    ok, err, data = await probe(ig_api.me_path(), {"fields": ig_api.profile_fields()})
    if ok:
        account = {"username": data.get("username", ""), "id": data.get("id", ""),
                   "account_type": data.get("account_type", ""),
                   "followers": data.get("followers_count"),
                   "media_count": data.get("media_count")}
    checks.append({"what": "Чтение своего профиля", "ok": ok, "error": err,
                   "detail": f"@{account.get('username','')}" if ok else ""})

    ok_media, err_media, media = await probe(ig_api.me_path("media"), {"fields": "id", "limit": 1})
    checks.append({"what": "Чтение своих публикаций", "ok": ok_media, "error": err_media,
                   "detail": "" if not ok_media else
                             ("постов нет" if not (media.get("data") or []) else "доступно")})

    # Комментарии проверяем на самом свежем посте: без поста проверять нечего,
    # и это не отказ в доступе, а отсутствие материала.
    items = (media.get("data") or []) if ok_media else []
    if items:
        ok_c, err_c, _ = await probe(f"{items[0]['id']}/comments", {"fields": "id", "limit": 1})
        checks.append({"what": "Чтение комментариев", "ok": ok_c, "error": err_c, "detail": ""})
    else:
        checks.append({"what": "Чтение комментариев", "ok": None, "error": "",
                       "detail": "нечего проверять — нет ни одной публикации"})

    # Публикацию не выполняем: проверка не должна оставлять постов в аккаунте.
    # Тип аккаунта — единственное, что можно узнать не публикуя.
    a_type = (account.get("account_type") or "").upper()
    if not account:
        checks.append({"what": "Публикация", "ok": None, "error": "",
                       "detail": "неизвестно — профиль не прочитался"})
    elif a_type in ("BUSINESS", "CREATOR", "MEDIA_CREATOR"):
        checks.append({"what": "Публикация", "ok": True, "error": "",
                       "detail": f"тип аккаунта {a_type} — публикация разрешена"})
    elif a_type:
        checks.append({"what": "Публикация", "ok": False,
                       "error": f"тип аккаунта {a_type}: Meta не пускает к публикации "
                                "личные аккаунты — переключите на Business или Creator",
                       "detail": ""})
    else:
        checks.append({"what": "Публикация", "ok": None, "error": "",
                       "detail": "тип аккаунта не сообщён"})

    failed = [c for c in checks if c["ok"] is False]
    return {"ok": not failed, "token_type": ig_api.token_type(),
            "api": ig_api.base(), "account": account, "checks": checks,
            "summary": ("всё доступно" if not failed
                        else "не работает: " + ", ".join(c["what"].lower() for c in failed))}
