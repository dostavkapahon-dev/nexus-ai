"""
Социальные коннекторы: здоровье площадок, продление токенов, OAuth-подключение.
Защищено auth на уровне main.py (кроме OAuth-callback — он приходит извне).
"""
import os

from fastapi import APIRouter
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
    url = (f"https://www.facebook.com/v19.0/dialog/oauth?client_id={app_id}"
           f"&redirect_uri={redirect}&scope={META_SCOPES}&response_type=code")
    return {"ok": True, "url": url, "redirect_uri": redirect,
            "note": "Этот же redirect_uri должен быть указан в настройках приложения Meta."}


@public_router.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(code: str = "", error: str = "", error_description: str = ""):
    """Принимает код от Meta, меняет его на long-lived токен и сохраняет.

    Открывается в браузере пользователя, поэтому отвечаем страницей, а не JSON.
    """
    if error:
        return _page("Подключение отменено", error_description or error, ok=False)
    if not code:
        return _page("Нет кода авторизации", "Meta не передала параметр code.", ok=False)

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
            long_token = d2.get("access_token", short)

            # 3. находим Instagram Business аккаунт у страниц пользователя
            r3 = await c.get(f"{GRAPH}/me/accounts", params={
                "fields": "name,instagram_business_account", "access_token": long_token})
            pages = (r3.json() or {}).get("data") or []
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
