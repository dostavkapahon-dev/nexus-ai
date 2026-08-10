"""
Серверный браузер — «руки» прямо на сервере, без ПК пользователя.

Зачем: публикация без официальных API площадок раньше требовала запущенного
desktop_agent.py на компьютере пользователя. Этот модуль поднимает headless
Chromium ПРЯМО на сервере и выполняет тот же протокол команд, что и desktop-агент
(navigate / screenshot / click_xy / type_text / key / scroll / wait / back /
page_text). Браузерный vision-агент управляет им точно так же — публикация идёт
через обычный веб-интерфейс площадок, без API-токенов.

Сессии (вход в Instagram/TikTok/YouTube) сохраняются в постоянном профиле
NEXUS_BROWSER_PROFILE, поэтому логиниться нужно один раз. Дополнительно можно
подложить готовые cookies через NEXUS_BROWSER_STORAGE_STATE (путь к storage_state
JSON от Playwright) — удобно, чтобы перенести вход с локального браузера.

Работает как фолбэк в send_to_desktop: если ПК-агент не подключён, команды
исполняет этот серверный браузер.
"""
import os
import base64
import asyncio

_playwright = None
_context = None
_page = None
_lock = asyncio.Lock()


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
    """Лениво поднимает persistent-context Chromium. Повторно использует его."""
    global _playwright, _context, _page
    if _context is not None and _page is not None:
        return _page

    from playwright.async_api import async_playwright
    _playwright = await async_playwright().start()
    os.makedirs(_profile_dir(), exist_ok=True)

    headless = os.getenv("NEXUS_BROWSER_HEADLESS", "1").strip() not in ("0", "false", "no")
    opts = {"headless": headless, "viewport": {"width": 1280, "height": 800}, "args": _LAUNCH_ARGS}

    exe = os.getenv("BROWSER_PATH")
    if exe:
        opts["executable_path"] = exe

    _context = await _playwright.chromium.launch_persistent_context(_profile_dir(), **opts)

    # Необязательный импорт cookies/сессий, перенесённых с локального браузера.
    state = os.getenv("NEXUS_BROWSER_STORAGE_STATE", "").strip()
    if state:
        try:
            import json
            data = json.loads(open(state).read()) if os.path.isfile(state) else json.loads(state)
            if data.get("cookies"):
                await _context.add_cookies(data["cookies"])
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
                await page.goto(cmd.get("url", ""), timeout=45000)
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
    global _playwright, _context, _page
    try:
        if _context:
            await _context.close()
        if _playwright:
            await _playwright.stop()
    except Exception:
        pass
    _playwright = _context = _page = None
