"""
Серверный браузер — «руки» онлайн, без ПК пользователя.

Зачем: публикация без официальных API площадок раньше требовала запущенного
desktop_agent.py на компьютере пользователя. Этот модуль даёт браузер на стороне
сервера и выполняет тот же протокол команд, что и desktop-агент (navigate /
screenshot / click_xy / type_text / key / scroll / wait / back / page_text).
Vision-агент управляет им так же — публикация идёт через обычный веб-интерфейс
площадок, без API-токенов.

Два режима (выбираются автоматически):
  • УДАЛЁННЫЙ (рекомендуется для слабого хостинга типа Render 512 МБ): если задан
    NEXUS_BROWSER_CDP (или BRIGHTDATA_BROWSER_URL) — Playwright подключается к
    облачному браузеру по CDP (напр. Bright Data Scraping Browser). Chromium на
    самом сервере НЕ запускается — инстанс остаётся лёгким, всё работает онлайн.
  • ЛОКАЛЬНЫЙ (для VPS с запасом памяти): поднимает headless Chromium прямо на
    сервере в постоянном профиле NEXUS_BROWSER_PROFILE.

Сессии/логины: в локальном режиме хранятся в профиле; в любом режиме можно
подложить cookies через NEXUS_BROWSER_STORAGE_STATE (storage_state JSON Playwright).

Работает как фолбэк в send_to_desktop: если ПК-агент не подключён, команды
исполняет этот серверный браузер.
"""
import os
import json
import base64
import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

# Хосты, которые нельзя открывать серверным браузером (защита от SSRF: облачные
# метаданные, локалхост). Доступ к внутренней сети через браузер закрыт.
_BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal",
                      "metadata.goog", "instance-data"}


def _host_is_private(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
        return (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified)
    except ValueError:
        pass
    # Не IP-литерал: пробуем резолвить и проверить все адреса.
    try:
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
                return True
    except Exception:
        return False  # не резолвится — не блокируем (best-effort)
    return False


def url_allowed(url: str) -> bool:
    """Разрешён ли URL для навигации: только http(s) и не внутренняя сеть."""
    try:
        u = urlparse((url or "").strip())
    except Exception:
        return False
    if u.scheme not in ("http", "https"):
        return False
    host = (u.hostname or "").lower()
    if not host or host in _BLOCKED_HOSTNAMES:
        return False
    return not _host_is_private(host)


_playwright = None
_browser = None          # выставлен только в удалённом (CDP) режиме
_context = None
_page = None
_lock = asyncio.Lock()


def _cdp_endpoint() -> str:
    return (os.getenv("NEXUS_BROWSER_CDP") or os.getenv("BRIGHTDATA_BROWSER_URL") or "").strip()


def mode() -> str:
    return "remote" if _cdp_endpoint() else "local"


# Playwright принимает только эти значения sameSite; расширения браузера пишут
# свои («no_restriction», «unspecified»), и на них context.add_cookies падает.
_SAMESITE = {"strict": "Strict", "lax": "Lax", "none": "None",
             "no_restriction": "None", "unspecified": "Lax"}


def normalize_cookies(raw) -> list[dict]:
    """Приводит cookies к формату Playwright.

    Пользователь достаёт cookies расширением (Cookie-Editor, EditThisCookie), а те
    экспортируют свой формат: `expirationDate` вместо `expires`, `sameSite:
    "no_restriction"`, плюс поля `hostOnly`/`session`/`storeId`, которых Playwright
    не знает и из-за которых `add_cookies` падает целиком. Разбирать эти ошибки
    руками пользователь не должен — нормализуем здесь.
    """
    out = []
    for c in (raw or []):
        if not isinstance(c, dict):
            continue
        name, value = c.get("name"), c.get("value")
        if not name or value is None:
            continue
        cookie = {"name": str(name), "value": str(value),
                  "path": c.get("path") or "/",
                  "httpOnly": bool(c.get("httpOnly", False)),
                  "secure": bool(c.get("secure", False))}

        domain = (c.get("domain") or "").strip()
        if domain:
            cookie["domain"] = domain
        elif c.get("url"):
            cookie["url"] = c["url"]
        else:
            continue   # без домена cookie бесполезен

        expires = c.get("expires", c.get("expirationDate"))
        if expires not in (None, "", -1):
            try:
                cookie["expires"] = int(float(expires))
            except (TypeError, ValueError):
                pass

        cookie["sameSite"] = _SAMESITE.get(str(c.get("sameSite", "")).lower(), "Lax")
        out.append(cookie)
    return out


def _storage_state():
    """Возвращает storage_state для Playwright из NEXUS_BROWSER_STORAGE_STATE.

    Принимает три вида значения: путь к файлу, JSON storage_state (`{"cookies": …}`)
    и просто массив cookies из расширения — последний вариант и есть то, что
    реально получается у пользователя за две минуты.
    """
    state = os.getenv("NEXUS_BROWSER_STORAGE_STATE", "").strip()
    if not state:
        return None
    try:
        data = json.loads(open(state).read()) if os.path.isfile(state) else json.loads(state)
    except Exception:
        return None

    if isinstance(data, list):
        data = {"cookies": data}
    if not isinstance(data, dict):
        return None

    cookies = normalize_cookies(data.get("cookies"))
    if not cookies:
        return None
    return {"cookies": cookies, "origins": data.get("origins") or []}


def session_domains() -> list[str]:
    """Домены, для которых есть cookies — по ним видно, куда мы залогинены."""
    state = _storage_state() or {}
    return sorted({(c.get("domain") or "").lstrip(".")
                   for c in state.get("cookies", []) if c.get("domain")})


def enabled() -> bool:
    """Серверный браузер разрешён? По умолчанию — да; можно выключить env-флагом."""
    return os.getenv("NEXUS_SERVER_BROWSER", "1").strip() not in ("0", "false", "no", "")


def _profile_dir() -> str:
    return os.getenv("NEXUS_BROWSER_PROFILE",
                     os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                  "browser_session"))


# Аргументы под маломощный хостинг (Render free): без sandbox и /dev/shm.
_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-setuid-sandbox",
    "--no-first-run",
    "--no-zygote",
]


async def ensure_browser():
    """Лениво даёт страницу браузера. Удалённый (CDP) режим — если задан эндпоинт,
    иначе локальный persistent-context Chromium. Повторно использует соединение."""
    global _playwright, _browser, _context, _page
    if _context is not None and _page is not None:
        return _page

    from playwright.async_api import async_playwright
    _playwright = await async_playwright().start()

    cdp = _cdp_endpoint()
    if cdp:
        # УДАЛЁННЫЙ облачный браузер (напр. Bright Data Scraping Browser).
        # Ничего тяжёлого на сервере не запускается — только сетевое подключение.
        _browser = await _playwright.chromium.connect_over_cdp(cdp)
        state = _storage_state()
        if _browser.contexts:
            _context = _browser.contexts[0]
        else:
            _context = await _browser.new_context(**({"storage_state": state} if state else {}))
        if state and state.get("cookies"):
            try:
                await _context.add_cookies(state["cookies"])
            except Exception:
                pass
        _page = _context.pages[0] if _context.pages else await _context.new_page()
        return _page

    # ЛОКАЛЬНЫЙ Chromium (для VPS с запасом памяти).
    os.makedirs(_profile_dir(), exist_ok=True)
    headless = os.getenv("NEXUS_BROWSER_HEADLESS", "1").strip() not in ("0", "false", "no")
    opts = {"headless": headless, "viewport": {"width": 1280, "height": 800}, "args": _LAUNCH_ARGS}
    exe = os.getenv("BROWSER_PATH")
    if exe:
        opts["executable_path"] = exe
    _context = await _playwright.chromium.launch_persistent_context(_profile_dir(), **opts)

    state = _storage_state()
    if state and state.get("cookies"):
        try:
            await _context.add_cookies(state["cookies"])
        except Exception:
            pass
    _page = _context.pages[0] if _context.pages else await _context.new_page()
    return _page


async def execute(cmd: dict) -> dict:
    """Исполняет одну команду того же протокола, что и desktop_agent.handle_command."""
    if not enabled():
        return {"ok": False, "error": "Серверный браузер выключен (NEXUS_SERVER_BROWSER=0)."}

    action = cmd.get("action", "")
    req_id = cmd.get("req_id", "")
    async with _lock:
        try:
            if action == "wait":
                await asyncio.sleep(min(float(cmd.get("seconds", 2)), 15))
                return {"req_id": req_id, "ok": True}

            page = await ensure_browser()

            if action == "screenshot":
                img = await page.screenshot(type="jpeg", quality=60)
                size = page.viewport_size or {"width": 1280, "height": 800}
                return {"req_id": req_id, "ok": True,
                        "screenshot": base64.b64encode(img).decode(), "url": page.url,
                        "title": await page.title(), "width": size["width"], "height": size["height"]}

            if action == "navigate":
                target = cmd.get("url", "")
                if not url_allowed(target):
                    return {"req_id": req_id, "ok": False,
                            "error": "URL заблокирован: разрешены только http(s) на внешние адреса"}
                await page.goto(target, timeout=45000)
                await asyncio.sleep(2)
                return {"req_id": req_id, "ok": True, "url": page.url, "title": await page.title()}

            if action == "click_xy":
                await page.mouse.click(float(cmd.get("x", 0)), float(cmd.get("y", 0)))
                await asyncio.sleep(1)
                return {"req_id": req_id, "ok": True}

            if action == "type_text":
                if cmd.get("clear"):
                    await page.keyboard.press("Control+A")
                    await page.keyboard.press("Delete")
                await page.keyboard.type(cmd.get("text", ""), delay=30)
                return {"req_id": req_id, "ok": True}

            if action == "key":
                await page.keyboard.press(cmd.get("key", "Enter"))
                await asyncio.sleep(0.5)
                return {"req_id": req_id, "ok": True}

            if action == "scroll":
                await page.mouse.wheel(0, int(cmd.get("dy", 600)))
                await asyncio.sleep(0.8)
                return {"req_id": req_id, "ok": True}

            if action == "back":
                await page.go_back(timeout=15000)
                await asyncio.sleep(1)
                return {"req_id": req_id, "ok": True, "url": page.url}

            if action == "page_text":
                text = await page.inner_text("body")
                return {"req_id": req_id, "ok": True, "text": text[:6000]}

            if action == "ping":
                return {"req_id": req_id, "ok": True, "message": "server browser alive"}

            return {"req_id": req_id, "ok": False, "error": f"Unknown action: {action}"}

        except Exception as e:
            return {"req_id": req_id, "ok": False, "error": str(e)}


def explain_error(err) -> str:
    """Переводит технический сбой браузера в понятное действие.

    «Executable doesn't exist at /opt/pw-browsers/...» ничего не говорит человеку
    о том, что делать. А делать надо одно: доустановить Chromium при сборке.
    """
    text = str(err or "")
    low = text.lower()
    if "executable doesn't exist" in low or "playwright install" in low:
        return ("Chromium не установлен на сервере. В Render → Settings → Build Command "
                "добавьте строкой: python -m playwright install chromium — и пересоберите. "
                "Либо задайте NEXUS_BROWSER_CDP (облачный браузер).")
    if "out of memory" in low or "killed" in low:
        return ("Браузеру не хватило памяти (Render free — 512 МБ). Используйте облачный "
                "браузер через NEXUS_BROWSER_CDP или тариф с большей памятью.")
    if "timeout" in low:
        return "Страница не открылась вовремя — площадка медленно отвечает, попробуйте ещё раз."
    return text[:200]


# По этим признакам на странице видно, что нас разлогинило.
_LOGIN_MARKERS = ("log in", "войти", "sign up", "зарегистрироваться",
                  "phone number, username", "телефон, имя пользователя")


async def check_session(platform: str = "instagram") -> dict:
    """Проверяет, жива ли браузерная сессия площадки.

    Cookies протухают молча, и без этой проверки публикация выглядит как
    «агент что-то делал и не смог» — вместо понятного «сессия истекла,
    обновите cookies». Проверяем по факту: открываем страницу и смотрим,
    не показывают ли нам форму входа.
    """
    urls = {"instagram": "https://www.instagram.com/",
            "tiktok": "https://www.tiktok.com/",
            "youtube": "https://studio.youtube.com/",
            "vk": "https://vk.com/feed"}
    url = urls.get(platform)
    if not url:
        return {"ok": False, "platform": platform, "error": "нет проверки для этой площадки"}

    if not enabled():
        return {"ok": False, "platform": platform,
                "error": "серверный браузер выключен (NEXUS_SERVER_BROWSER=0)"}
    if not _storage_state():
        return {"ok": False, "platform": platform, "logged_in": False,
                "error": "cookies не заданы — вставьте их в Ключи API → Браузерная сессия"}

    nav = await execute({"action": "navigate", "url": url})
    if not nav.get("ok"):
        return {"ok": False, "platform": platform, "error": explain_error(nav.get("error"))}

    text = (await execute({"action": "page_text"})).get("text", "").lower()
    logged_in = not any(m in text for m in _LOGIN_MARKERS)
    return {"ok": True, "platform": platform, "logged_in": logged_in,
            "mode": mode(), "url": nav.get("url"),
            "hint": None if logged_in else "сессия истекла — обновите cookies"}


async def is_available() -> bool:
    """Можно ли реально поднять браузер на сервере (Playwright + Chromium стоят)."""
    if not enabled():
        return False
    try:
        await ensure_browser()
        return True
    except Exception:
        return False


async def shutdown():
    global _playwright, _browser, _context, _page
    try:
        if _browser:            # удалённый режим: закрываем соединение, не сам браузер
            await _browser.close()
        elif _context:          # локальный persistent-context
            await _context.close()
        if _playwright:
            await _playwright.stop()
    except Exception:
        pass
    _playwright = _browser = _context = _page = None
