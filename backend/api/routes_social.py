"""
Социальные коннекторы: здоровье площадок, продление токенов, OAuth-подключение.
Защищено auth на уровне main.py (кроме OAuth-callback — он приходит извне).
"""
import os
import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/social", tags=["social"])
# Callback от Meta приходит в браузере пользователя, без нашего токена — публичный.
public_router = APIRouter(prefix="/api/social", tags=["social"])

GRAPH = "https://graph.facebook.com/v19.0"
# Права, которые запрашиваем при подключении Instagram через Facebook.
META_SCOPES = ("instagram_basic,instagram_manage_insights,instagram_content_publish,"
               "pages_show_list,pages_read_engagement,pages_manage_posts")


@router.get("/health")
async def social_health():
    """Живой статус всех площадок: валиден ли токен, до когда, какие права."""
    from connectors import health_all
    items = await health_all()
    return {
        "platforms": items,
        "connected": sum(1 for i in items if i.get("ok")),
        "total": len(items),
        "needs_attention": [i["platform"] for i in items
                            if i.get("configured") and not i.get("ok")],
        "expiring_soon": [i["platform"] for i in items
                          if (i.get("days_left") is not None and i["days_left"] < 7)],
    }


@router.get("/health/{platform}")
async def social_health_one(platform: str):
    from connectors import get_connector
    c = get_connector(platform)
    if not c:
        return {"ok": False, "error": f"неизвестная площадка: {platform}"}
    return await c.health()


@router.post("/refresh/{platform}")
async def social_refresh(platform: str):
    """Продлить токен площадки (для Instagram — обмен на long-lived, 60 дней)."""
    from connectors import get_connector
    c = get_connector(platform)
    if not c:
        return {"ok": False, "error": f"неизвестная площадка: {platform}"}
    return await c.refresh_token()


class ReadBody(BaseModel):
    limit: int = 10


@router.post("/{platform}/posts")
async def social_read_posts(platform: str, body: ReadBody):
    """Последние посты площадки с метриками — через её коннектор."""
    from connectors import get_connector
    c = get_connector(platform)
    if not c:
        return {"ok": False, "error": f"неизвестная площадка: {platform}"}
    return await c.read_posts(body.limit)


@router.get("/{platform}/profile")
async def social_read_profile(platform: str):
    from connectors import get_connector
    c = get_connector(platform)
    if not c:
        return {"ok": False, "error": f"неизвестная площадка: {platform}"}
    return await c.read_profile()


# ─────────────────────────── OAuth (Meta: Instagram) ───────────────────────────

def _redirect_uri() -> str:
    base = (os.getenv("RENDER_EXTERNAL_URL", "") or os.getenv("NEXUS_PUBLIC_URL", "")).rstrip("/")
    return f"{base}/api/social/oauth/callback" if base else ""


@public_router.get("/webhook/instagram")
async def webhook_verify(request: Request):
    """Подтверждение подписки. Meta зовёт этот адрес из своей инфраструктуры,
    без нашей авторизации — поэтому роут публичный, а защита в токене."""
    from fastapi.responses import PlainTextResponse
    from core.webhooks import check_subscription

    q = request.query_params
    ok, payload = check_subscription(q.get("hub.mode", ""), q.get("hub.verify_token", ""),
                                     q.get("hub.challenge", ""))
    if not ok:
        return PlainTextResponse(payload, status_code=403)
    # Meta ждёт ровно challenge текстом, без кавычек и JSON-обёртки.
    return PlainTextResponse(payload)


@public_router.post("/webhook/instagram")
async def webhook_receive(request: Request):
    """Приём событий (комментарии, упоминания) с проверкой подписи приложения."""
    from fastapi.responses import JSONResponse
    from core.webhooks import check_signature, handle_events

    body = await request.body()
    if not check_signature(body, request.headers.get("X-Hub-Signature-256", "")):
        # Публичный эндпоинт: без валидной подписи запрос мог прислать кто угодно.
        return JSONResponse({"error": "подпись не совпала"}, status_code=403)

    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        return JSONResponse({"error": "тело не JSON"}, status_code=400)

    result = await handle_events(payload)
    # Meta повторяет доставку при любом ответе, кроме 200, и отключает подписку
    # после серии неудач — поэтому отвечаем 200 даже на внутренний сбой.
    return JSONResponse(result, status_code=200)


@router.get("/webhook/events")
async def webhook_events(limit: int = 20):
    """Последние принятые события — видно, доходят ли вебхуки вообще."""
    from core.webhooks import recent_events, verify_token
    return {"configured": bool(verify_token()), "events": await recent_events(limit)}


@router.get("/browser/session")
async def browser_session(platform: str = "instagram"):
    """Жива ли браузерная сессия площадки — путь публикации без API-ключей.

    Cookies протухают молча; без этой проверки отказ выглядит как «агент не смог»,
    а не как «сессия истекла, обновите cookies».
    """
    from core import server_browser
    return await server_browser.check_session(platform)


@router.get("/browser/status")
async def browser_status():
    """Готовность браузерного пути: режим, наличие cookies, для каких доменов."""
    from core import server_browser
    domains = server_browser.session_domains()
    return {"enabled": server_browser.enabled(), "mode": server_browser.mode(),
            "has_cookies": bool(domains), "domains": domains,
            "publish_mode": os.getenv("NEXUS_PUBLISH_MODE", "auto")}


class TokenBody(BaseModel):
    access_token: str
    account_id: str | None = None


@router.post("/instagram/connect")
async def instagram_connect(body: TokenBody):
    """Прямое подключение по готовому токену — без прохождения OAuth.

    Токен уже выдан в панели Meta, поэтому система только определяет его тип,
    находит Account ID и запоминает, каким способом продлевать через 60 дней.
    """
    from core.ig_connect import connect
    return await connect(body.access_token, body.account_id or "")


@router.get("/instagram/access")
async def instagram_access():
    """Что сохранённый токен реально умеет — проверкой самих операций."""
    from core.ig_connect import check_access
    return await check_access()


@router.get("/webhook/config")
async def webhook_config():
    """Готовые значения для панели Meta: адрес обратного вызова и токен подтверждения.

    Раньше оба значения приходилось составлять вручную — адрес угадывать по
    имени сервиса, токен придумывать и вписывать в двух местах одинаково.
    Расхождение в один символ давало у Meta безликое «The callback URL or verify
    token couldn't be validated». Теперь адрес считается от фактического
    публичного адреса, а токен генерируется и сохраняется сам при первом заходе.
    """
    import secrets
    from core.webhooks import VERIFY_TOKEN_ENV
    from connectors.instagram import _save_key

    base = (os.getenv("RENDER_EXTERNAL_URL", "")
            or os.getenv("NEXUS_PUBLIC_URL", "")).strip().rstrip("/")

    token = os.getenv(VERIFY_TOKEN_ENV, "").strip()
    generated = False
    if not token:
        # Значение произвольное — важно лишь, чтобы совпадало здесь и в панели.
        token = "nexus-" + secrets.token_hex(12)
        await _save_key(VERIFY_TOKEN_ENV.lower(), token)
        generated = True

    app_secret_set = bool(os.getenv("INSTAGRAM_APP_SECRET", "").strip()
                          or os.getenv("FACEBOOK_APP_SECRET", "").strip())

    return {
        "ok": bool(base),
        "callback_url": f"{base}/api/social/webhook/instagram" if base else "",
        "verify_token": token,
        "verify_token_generated": generated,
        "app_secret_set": app_secret_set,
        "fields": ["comments", "mentions"],
        "error": "" if base else
                 "не определён публичный адрес сервиса — впишите его в Ключи API → Instagram",
        "note": ("Скопируйте оба значения в панель Meta → Instagram → Webhooks. "
                 "Без Instagram app secret события будут отклоняться по подписи."
                 if app_secret_set is False else
                 "Скопируйте оба значения в панель Meta → Instagram → Webhooks."),
    }


# Одноразовые ключи запросов OAuth. Без них публичный callback принимал любой
# код: злоумышленник мог подсунуть владельцу ссылку и подменить подключённый
# аккаунт на свой.
_OAUTH_STATES: dict[str, float] = {}
_STATE_TTL = 900          # 15 минут — дольше подключение не длится


def _issue_state() -> str:
    import secrets as pysecrets
    import time
    now = time.time()
    for key, born in list(_OAUTH_STATES.items()):
        if now - born > _STATE_TTL:
            _OAUTH_STATES.pop(key, None)
    state = pysecrets.token_urlsafe(24)
    _OAUTH_STATES[state] = now
    return state


def _take_state(state: str) -> bool:
    """Ключ одноразовый: второй раз тот же код принять нельзя."""
    import time
    born = _OAUTH_STATES.pop((state or "").strip(), None)
    return bool(born) and (time.time() - born) <= _STATE_TTL


@router.get("/oauth/start")
async def oauth_start():
    """Ссылка на подключение Instagram через Facebook.

    Раньше токен добывался руками в Graph API Explorer. Теперь — обычный OAuth:
    пользователь жмёт ссылку, разрешает доступ, токен сохраняется сам.
    """
    app_id = os.getenv("FACEBOOK_APP_ID", "").strip()
    redirect = _redirect_uri()
    if not app_id:
        return {"ok": False,
                "error": "не задан FACEBOOK_APP_ID — создайте приложение на developers.facebook.com"}
    if not redirect:
        return {"ok": False,
                "error": "не определён публичный адрес сервиса: задайте NEXUS_PUBLIC_URL"}
    from urllib.parse import urlencode
    state = _issue_state()
    url = ("https://www.facebook.com/v19.0/dialog/oauth?" + urlencode({
        "client_id": app_id, "redirect_uri": redirect, "scope": META_SCOPES,
        "response_type": "code", "state": state}))
    return {"ok": True, "url": url, "redirect_uri": redirect,
            "note": "Этот же redirect_uri должен быть указан в настройках приложения Meta."}


@public_router.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(code: str = "", error: str = "", error_description: str = "",
                         state: str = ""):
    """Принимает код от Meta, меняет его на long-lived токен и сохраняет.

    Открывается в браузере пользователя, поэтому отвечаем страницей, а не JSON.
    """
    if error:
        return _page("Подключение отменено", error_description or error, ok=False)
    if not code:
        return _page("Нет кода авторизации", "Meta не передала параметр code.", ok=False)
    if not _take_state(state):
        # Подключение начинают в дашборде — только там выдаётся ключ запроса.
        return _page("Запрос не распознан",
                     "Ссылка устарела или открыта не из дашборда. "
                     "Начните подключение заново на странице «Подключения».", ok=False)

    app_id = os.getenv("FACEBOOK_APP_ID", "").strip()
    app_secret = os.getenv("FACEBOOK_APP_SECRET", "").strip()
    if not (app_id and app_secret):
        return _page("Не хватает настроек",
                     "Задайте FACEBOOK_APP_ID и FACEBOOK_APP_SECRET.", ok=False)

    import httpx
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            # 1. код → короткоживущий токен
            r = await c.get(f"{GRAPH}/oauth/access_token", params={
                "client_id": app_id, "client_secret": app_secret,
                "redirect_uri": _redirect_uri(), "code": code})
            d = r.json()
            if d.get("error"):
                return _page("Meta отклонила код", str(d["error"].get("message"))[:300], ok=False)
            short = d.get("access_token", "")

            # 2. короткоживущий → long-lived (60 дней)
            r2 = await c.get(f"{GRAPH}/oauth/access_token", params={
                "grant_type": "fb_exchange_token", "client_id": app_id,
                "client_secret": app_secret, "fb_exchange_token": short})
            d2 = r2.json()
            if d2.get("error") or not d2.get("access_token"):
                # Короткоживущий токен живёт час-два. Сохранить его и написать
                # «60 дней» — значит гарантированно сломать публикацию завтра.
                return _page("Не удалось получить долгий токен",
                             str((d2.get("error") or {}).get("message")
                                 or "Meta не вернула long-lived токен")[:300], ok=False)
            long_token = d2["access_token"]

            # 3. находим Instagram Business аккаунт у страниц пользователя
            r3 = await c.get(f"{GRAPH}/me/accounts", params={
                "fields": "name,instagram_business_account", "access_token": long_token})
            d3 = r3.json() or {}
            if d3.get("error"):
                return _page("Не удалось прочитать страницы",
                             str(d3["error"].get("message"))[:300], ok=False)
            pages = d3.get("data") or []
            ig_id = ""
            page_name = ""
            for p in pages:
                iba = p.get("instagram_business_account") or {}
                if iba.get("id"):
                    ig_id, page_name = iba["id"], p.get("name", "")
                    break
    except Exception as e:
        return _page("Ошибка обмена токена", str(e)[:300], ok=False)

    from connectors.instagram import _save_key
    await _save_key("instagram_access_token", long_token)
    # Тип токена определяет и адрес API, и способ продления: без него он потом
    # угадывается по префиксу, и ошибка вскрывается на первой публикации.
    await _save_key("instagram_token_type", "facebook")
    if ig_id:
        await _save_key("instagram_account_id", ig_id)

    if not ig_id:
        return _page("Токен получен, но Instagram не найден",
                     "К вашей Facebook-странице не привязан Instagram Business/Creator аккаунт. "
                     "Привяжите его и повторите подключение.", ok=False)
    return _page("Instagram подключён",
                 f"Страница: {page_name or '—'} · ID аккаунта: {ig_id}. "
                 "Токен долгоживущий (60 дней), продление доступно кнопкой в дашборде.", ok=True)


def _page(title: str, message: str, ok: bool) -> str:
    # Роут публичный, а в сообщение попадает текст из query-параметров и от Meta:
    # без экранирования это отражённый XSS.
    import html as _html
    title = _html.escape(str(title or ""))
    message = _html.escape(str(message or ""))
    color = "#22c55e" if ok else "#ef4444"
    icon = "✅" if ok else "⚠️"
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>{title}</title><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="background:#07070f;color:#e8e8f5;font-family:system-ui,sans-serif;
display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0">
<div style="max-width:520px;padding:32px;background:#0d0d1a;border:1px solid #1c1c30;border-radius:16px">
<div style="font-size:40px">{icon}</div>
<h1 style="color:{color};font-size:20px;margin:12px 0">{title}</h1>
<p style="color:#9a9ac0;line-height:1.6;font-size:14px">{message}</p>
<a href="/connections" style="display:inline-block;margin-top:16px;padding:10px 18px;
background:#7c3aed;color:#fff;text-decoration:none;border-radius:10px;font-size:14px">
Вернуться в дашборд</a></div></body></html>"""
