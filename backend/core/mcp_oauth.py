"""OAuth для MCP Higgsfield: человек входит один раз, дальше работает сервер.

Почему это вообще нужно. Официальный MCP Higgsfield авторизует не приложение, а
пользователя: ключ и секрет из кабинета там не принимаются. На сервере нажать
«войти» некому, поэтому MCP всё время оставался «настроен, но не отвечает», и
генерация упиралась в REST, где у ключа нет права на модель.

Здесь реализован ровно тот поток, который описан в спецификации MCP: сервер сам
находит адреса авторизации, регистрируется как клиент, отдаёт человеку ссылку, а
после его согласия меняет код на токен и хранит токен у себя. Дальше сервер
работает без человека, а когда токен истечёт — обновляет его сам по refresh.

Секреты не уходят ни во фронтенд, ни в Telegram, ни в логи: токен хранится там
же, где остальные доступы (`core.credentials`, с шифрованием), а наружу отдаётся
только адрес страницы входа.
"""
import base64
import hashlib
import json
import os
import secrets
import time

import httpx

OFFICIAL_MCP_URL = "https://mcp.higgsfield.ai/mcp"

# Где лежат выданные платформой данные. Имена совпадают с переменными окружения,
# которые читает клиент MCP: тогда после входа ничего перенастраивать не нужно.
TOKEN_KEY = "higgsfield_mcp_token"
REFRESH_KEY = "higgsfield_mcp_refresh"
CLIENT_KEY = "higgsfield_mcp_client"       # регистрация клиента (id + secret)
FLOW_KEY = "higgsfield_mcp_flow"           # незавершённый вход: state + verifier

CALLBACK_PATH = "/api/mcp/higgsfield/callback"

TIMEOUT = 20.0


def server_url() -> str:
    return (os.getenv("HIGGSFIELD_MCP_URL", "").strip() or OFFICIAL_MCP_URL).rstrip("/")


def public_base() -> str:
    """Адрес, на который платформа вернёт человека после входа.

    На Render он известен самому хостингу, поэтому обычно ничего задавать не
    нужно — и это важно: неверный адрес возврата ломает вход уже после того,
    как человек ввёл пароль.
    """
    base = (os.getenv("NEXUS_PUBLIC_URL", "")
            or os.getenv("RENDER_EXTERNAL_URL", "")).strip()
    return base.rstrip("/")


def redirect_uri() -> str:
    base = public_base()
    return f"{base}{CALLBACK_PATH}" if base else ""


def _origin(url: str) -> str:
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


async def _kv_get(key: str) -> str:
    try:
        from core.credentials import get as _get
        return (await _get(key)) or ""
    except Exception:
        return ""


async def _kv_set(key: str, value: str) -> None:
    from core.credentials import set as _set
    await _set(key, value)


async def discover() -> dict:
    """Адреса авторизации — у самой платформы, а не зашитые в коде.

    Спецификация MCP говорит спрашивать их у сервера ресурса, и это не
    формальность: зашитый адрес живёт до первой смены на их стороне.
    """
    url = server_url()
    out = {"ok": False, "resource": url}
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as c:
        issuer = ""
        try:
            r = await c.get(f"{_origin(url)}/.well-known/oauth-protected-resource")
            if r.status_code == 200:
                data = r.json()
                servers = data.get("authorization_servers") or []
                issuer = str(servers[0]) if servers else ""
        except Exception as e:
            out["error"] = f"метаданные ресурса недоступны: {type(e).__name__}"
        # Часть серверов метаданных ресурса не отдаёт, но сама является и
        # сервером авторизации. Тогда спрашиваем их у того же адреса.
        issuer = issuer or _origin(url)
        for path in ("/.well-known/oauth-authorization-server",
                     "/.well-known/openid-configuration"):
            try:
                r = await c.get(f"{issuer.rstrip('/')}{path}")
            except Exception as e:
                out["error"] = f"{type(e).__name__}: {str(e)[:120]}"
                continue
            if r.status_code != 200:
                continue
            meta = r.json()
            out.update(ok=True, issuer=issuer,
                       authorize=meta.get("authorization_endpoint", ""),
                       token=meta.get("token_endpoint", ""),
                       register=meta.get("registration_endpoint", ""),
                       scopes=meta.get("scopes_supported") or [])
            return out
    out.setdefault("error", "сервер не отдал метаданные авторизации")
    return out


async def _client(meta: dict) -> dict:
    """Регистрация приложения. Один раз — дальше берём сохранённую."""
    saved = await _kv_get(CLIENT_KEY)
    if saved:
        try:
            return json.loads(saved)
        except Exception:
            pass
    endpoint = meta.get("register") or ""
    if not endpoint:
        # Без динамической регистрации нужен заранее выданный client_id.
        cid = (os.getenv("HIGGSFIELD_MCP_CLIENT_ID", "") or "").strip()
        if not cid:
            raise RuntimeError(
                "сервер не поддерживает автоматическую регистрацию клиента; "
                "нужен HIGGSFIELD_MCP_CLIENT_ID из кабинета Higgsfield")
        return {"client_id": cid,
                "client_secret": (os.getenv("HIGGSFIELD_MCP_CLIENT_SECRET", "")
                                  or "").strip()}
    body = {"client_name": "NEXUS AI Content Director",
            "redirect_uris": [redirect_uri()],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none"}
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(endpoint, json=body)
    if r.status_code >= 400:
        raise RuntimeError(f"регистрация клиента отклонена ({r.status_code}): "
                           f"{r.text[:200]}")
    data = r.json()
    await _kv_set(CLIENT_KEY, json.dumps(data, ensure_ascii=False))
    return data


def _verifier() -> tuple[str, str]:
    """PKCE: секрет остаётся у нас, наружу уходит только его отпечаток."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


async def start() -> dict:
    """Готовит вход и возвращает ссылку для человека."""
    if not redirect_uri():
        return {"ok": False,
                "error": "не известен публичный адрес сервиса — задайте "
                         "NEXUS_PUBLIC_URL (адрес вашего сервиса на Render)"}
    meta = await discover()
    if not meta.get("ok") or not meta.get("authorize"):
        return {"ok": False,
                "error": meta.get("error", "не нашёл адрес авторизации")}
    try:
        client = await _client(meta)
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}

    # Прав не просим вовсе — и это не упрощение, а единственное, что здесь
    # верно. Higgsfield отвечал «The OAuth 2.0 Client is not allowed to
    # request scope 'private_metadata'», когда мы брали список из метаданных
    # сервера. Ответ регистрации тоже не годится источником: он может нести
    # тот же широкий список, и отказ повторится. Молчание надёжнее догадки —
    # сервер авторизации сам выдаёт права по умолчанию.
    #
    # Единственный способ задать их явно — переменная окружения: если
    # платформа однажды потребует конкретное право, его впишут руками.
    granted = (os.getenv("HIGGSFIELD_MCP_SCOPE", "") or "").strip()

    verifier, challenge = _verifier()
    state = secrets.token_urlsafe(24)
    await _kv_set(FLOW_KEY, json.dumps({
        "state": state, "verifier": verifier, "token": meta["token"],
        "client_id": client.get("client_id", ""),
        "client_secret": client.get("client_secret", ""),
        "scope": granted,
        "started": time.time()}, ensure_ascii=False))

    from urllib.parse import urlencode
    params = {"response_type": "code",
              "client_id": client.get("client_id", ""),
              "redirect_uri": redirect_uri(),
              "state": state,
              "code_challenge": challenge,
              "code_challenge_method": "S256",
              "resource": server_url()}
    if granted:
        params["scope"] = granted
    return {"ok": True, "url": f"{meta['authorize']}?{urlencode(params)}",
            "redirect": redirect_uri()}


async def finish(code: str, state: str) -> dict:
    """Меняет код на токен. Вызывается со страницы возврата."""
    raw = await _kv_get(FLOW_KEY)
    if not raw:
        return {"ok": False, "error": "вход не начинался или уже завершён"}
    try:
        flow = json.loads(raw)
    except Exception:
        return {"ok": False, "error": "состояние входа повреждено"}
    if not state or state != flow.get("state"):
        # Чужой запрос на наш адрес возврата. Принять его — значит пустить в
        # аккаунт кого угодно.
        return {"ok": False, "error": "не совпал state — запрос отклонён"}
    if not code:
        return {"ok": False, "error": "платформа не вернула код"}

    data = {"grant_type": "authorization_code", "code": code,
            "redirect_uri": redirect_uri(),
            "client_id": flow.get("client_id", ""),
            "code_verifier": flow.get("verifier", ""),
            "resource": server_url()}
    if flow.get("client_secret"):
        data["client_secret"] = flow["client_secret"]
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(flow["token"], data=data,
                         headers={"Content-Type":
                                  "application/x-www-form-urlencoded"})
    if r.status_code >= 400:
        return {"ok": False,
                "error": f"обмен кода отклонён ({r.status_code}): {r.text[:200]}"}
    body = r.json()
    access = body.get("access_token", "")
    if not access:
        return {"ok": False, "error": "платформа не вернула access_token"}
    await _kv_set(TOKEN_KEY, access)
    if body.get("refresh_token"):
        await _kv_set(REFRESH_KEY, body["refresh_token"])
    await _kv_set(FLOW_KEY, "-")        # вход завершён, черновик больше не нужен
    return {"ok": True, "refreshable": bool(body.get("refresh_token")),
            "expires_in": body.get("expires_in", 0)}


async def refresh() -> dict:
    """Продлевает доступ без человека. Ради этого всё и делалось."""
    token = await _kv_get(REFRESH_KEY)
    if not token:
        return {"ok": False, "error": "нет refresh-токена — нужен повторный вход"}
    saved = await _kv_get(CLIENT_KEY)
    client = json.loads(saved) if saved else {}
    meta = await discover()
    if not meta.get("ok") or not meta.get("token"):
        return {"ok": False, "error": meta.get("error", "нет адреса токена")}
    data = {"grant_type": "refresh_token", "refresh_token": token,
            "client_id": client.get("client_id", ""),
            "resource": server_url()}
    if client.get("client_secret"):
        data["client_secret"] = client["client_secret"]
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(meta["token"], data=data,
                         headers={"Content-Type":
                                  "application/x-www-form-urlencoded"})
    if r.status_code >= 400:
        return {"ok": False,
                "error": f"продление отклонено ({r.status_code}): {r.text[:200]}"}
    body = r.json()
    if not body.get("access_token"):
        return {"ok": False, "error": "платформа не вернула access_token"}
    await _kv_set(TOKEN_KEY, body["access_token"])
    if body.get("refresh_token"):
        await _kv_set(REFRESH_KEY, body["refresh_token"])
    return {"ok": True}


async def reset() -> dict:
    """Забывает регистрацию клиента и незавершённый вход.

    Нужна, когда на сервере осталась запись от неудачной попытки: следующий
    `/hfconnect` тогда регистрируется заново, а не тянет прежние данные.
    Токены не трогает — их убирает только повторный вход.
    """
    from core.credentials import delete as _delete
    gone = []
    for key in (CLIENT_KEY, FLOW_KEY):
        try:
            await _delete(key)
            gone.append(key)
        except Exception:
            pass
    return {"ok": True, "cleared": gone}


async def state() -> dict:
    """Что известно про вход. Значения токенов наружу не отдаём — только факт."""
    token = await _kv_get(TOKEN_KEY)
    return {"connected": bool(token),
            "refreshable": bool(await _kv_get(REFRESH_KEY)),
            "redirect": redirect_uri(),
            "server": server_url()}

async def refresh_on_start() -> dict:
    """Продлить доступ при запуске сервиса. Никогда не роняет старт.

    Токен доступа живёт часами, деплой случается чаще. Без этого первая задача
    после перезапуска упиралась в протухший доступ, канал уходил в остывание, и
    человек видел «Higgsfield не работает» — хотя вход был выполнен и продлить
    его можно молча.
    """
    try:
        if not await _kv_get(REFRESH_KEY):
            return {"ok": False, "error": "вход не выполнен"}
        res = await refresh()
        print(f"[NEXUS] доступ Higgsfield "
              + ("продлён при запуске" if res.get("ok")
                 else f"продлить не удалось: {str(res.get('error'))[:120]}"),
              flush=True)
        return res
    except BaseException as e:
        print(f"[NEXUS] продление доступа Higgsfield не выполнено: "
              f"{type(e).__name__}: {str(e)[:120]}", flush=True)
        return {"ok": False, "error": str(e)[:200]}
