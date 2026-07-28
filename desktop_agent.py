#!/usr/bin/env python3
"""
NEXUS AI Desktop Agent
======================
Запусти этот скрипт на своём ПК, чтобы подключить
браузерное управление к дашборду NEXUS AI.

Установка:
  pip install websockets playwright
  playwright install chromium

Запуск:
  python desktop_agent.py --server https://nexus-ai-emog.onrender.com --token YOUR_TOKEN
"""
import asyncio
import json
import os
import sys
import base64
import argparse
from datetime import datetime

try:
    import websockets
    from playwright.async_api import async_playwright
except ImportError:
    print("Установите зависимости: pip install websockets playwright && playwright install chromium")
    sys.exit(1)

parser = argparse.ArgumentParser()
parser.add_argument("--server", default="https://nexus-ai-emog.onrender.com", help="URL сервера NEXUS AI")
parser.add_argument("--token", default=os.getenv("NEXUS_TOKEN", ""), help="Токен авторизации")
parser.add_argument("--headless", action="store_true", help="Запустить браузер без GUI")
args = parser.parse_args()

WS_URL = args.server.replace("https://", "wss://").replace("http://", "ws://") + "/ws/desktop"
HEADLESS = args.headless

_browser = None
_page = None
_playwright = None

# Постоянный профиль браузера: вход в Instagram/VK/др. сохраняется между запусками.
PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser_session")

def _find_chromium() -> str | None:
    """Ищет уже скачанный Chromium (любой версии) в кэше Playwright."""
    import glob
    roots = [os.getenv("PLAYWRIGHT_BROWSERS_PATH", ""),
             os.path.expanduser("~/.cache/ms-playwright"),
             os.path.expandvars(r"%USERPROFILE%\AppData\Local\ms-playwright")]
    patterns = ["chromium-*/chrome-linux/chrome", "chromium-*/chrome-win/chrome.exe",
                "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium"]
    for root in [r for r in roots if r and os.path.isdir(r)]:
        for pat in patterns:
            hits = sorted(glob.glob(os.path.join(root, pat)), reverse=True)
            if hits:
                return hits[0]
    return None


async def ensure_browser():
    """Поднимает браузер с сохранением сессий. Устойчиво к рассинхрону версий
    Playwright/Chromium: пробует бандл, системный Chrome/Edge, затем явный файл."""
    global _browser, _page, _playwright
    if _browser is None:
        _playwright = await async_playwright().start()
        os.makedirs(PROFILE_DIR, exist_ok=True)
        opts = {"headless": HEADLESS, "viewport": {"width": 1280, "height": 800}}

        attempts = [
            ("бандл Playwright", {}),
            ("системный Chrome", {"channel": "chrome"}),
            ("системный Edge", {"channel": "msedge"}),
        ]
        # Явный путь к браузеру — спасает при рассинхроне версий Playwright/Chromium.
        exe = os.getenv("BROWSER_PATH") or _find_chromium()
        if exe:
            attempts.append((f"файл {os.path.basename(exe)}", {"executable_path": exe}))
        errors = []
        for label, extra in attempts:
            try:
                _browser = await _playwright.chromium.launch_persistent_context(
                    PROFILE_DIR, **opts, **extra
                )
                print(f"🌐 Браузер запущен ({label})")
                break
            except Exception as e:
                errors.append(f"{label}: {str(e)[:120]}")
                _browser = None

        if _browser is None:
            hint = ("Не удалось запустить браузер.\n"
                    "Выполни:  py -m playwright install chromium\n"
                    "или установи Google Chrome.\nПодробности:\n  " + "\n  ".join(errors))
            raise RuntimeError(hint)

        _page = _browser.pages[0] if _browser.pages else await _browser.new_page()
    return _page

async def handle_command(cmd: dict) -> dict:
    action = cmd.get("action", "")
    req_id = cmd.get("req_id", "")

    try:
        if action == "screenshot":
            page = await ensure_browser()
            img = await page.screenshot(type="jpeg", quality=60)
            b64 = base64.b64encode(img).decode()
            size = page.viewport_size or {"width": 1280, "height": 720}
            return {"req_id": req_id, "ok": True, "screenshot": b64, "url": page.url,
                    "title": await page.title(), "width": size["width"], "height": size["height"]}

        elif action == "click_xy":
            # Click at absolute viewport coordinates (used by the vision agent).
            page = await ensure_browser()
            x = float(cmd.get("x", 0))
            y = float(cmd.get("y", 0))
            await page.mouse.click(x, y)
            await asyncio.sleep(1)
            return {"req_id": req_id, "ok": True}

        elif action == "type_text":
            # Type into the currently focused element (after a click).
            page = await ensure_browser()
            text = cmd.get("text", "")
            clear = cmd.get("clear", False)
            if clear:
                await page.keyboard.press("Control+A")
                await page.keyboard.press("Delete")
            await page.keyboard.type(text, delay=30)
            return {"req_id": req_id, "ok": True}

        elif action == "key":
            page = await ensure_browser()
            await page.keyboard.press(cmd.get("key", "Enter"))
            await asyncio.sleep(0.5)
            return {"req_id": req_id, "ok": True}

        elif action == "scroll":
            page = await ensure_browser()
            dy = int(cmd.get("dy", 600))
            await page.mouse.wheel(0, dy)
            await asyncio.sleep(0.8)
            return {"req_id": req_id, "ok": True}

        elif action == "wait":
            await asyncio.sleep(min(float(cmd.get("seconds", 2)), 15))
            return {"req_id": req_id, "ok": True}

        elif action == "back":
            page = await ensure_browser()
            await page.go_back(timeout=15000)
            await asyncio.sleep(1)
            return {"req_id": req_id, "ok": True, "url": page.url}

        elif action == "page_text":
            page = await ensure_browser()
            text = await page.inner_text("body")
            return {"req_id": req_id, "ok": True, "text": text[:6000]}

        elif action == "navigate":
            url = cmd.get("url", "")
            page = await ensure_browser()
            await page.goto(url, timeout=30000)
            await asyncio.sleep(2)
            return {"req_id": req_id, "ok": True, "url": page.url, "title": await page.title()}

        elif action == "click":
            page = await ensure_browser()
            selector = cmd.get("selector", "")
            await page.click(selector, timeout=10000)
            return {"req_id": req_id, "ok": True}

        elif action == "type":
            page = await ensure_browser()
            selector = cmd.get("selector", "")
            text = cmd.get("text", "")
            await page.fill(selector, text)
            return {"req_id": req_id, "ok": True}

        elif action == "get_text":
            page = await ensure_browser()
            selector = cmd.get("selector", "")
            text = await page.inner_text(selector)
            return {"req_id": req_id, "ok": True, "text": text}

        elif action == "post_instagram":
            # Navigate to Instagram and post content
            page = await ensure_browser()
            text = cmd.get("text", "")
            image_url = cmd.get("image_url", "")
            await page.goto("https://www.instagram.com", timeout=30000)
            await asyncio.sleep(2)
            img = await page.screenshot(type="jpeg", quality=50)
            b64 = base64.b64encode(img).decode()
            return {"req_id": req_id, "ok": True, "screenshot": b64,
                    "message": "Instagram открыт. Продолжай управление через команды."}

        elif action == "post_tiktok":
            page = await ensure_browser()
            await page.goto("https://www.tiktok.com/upload", timeout=30000)
            await asyncio.sleep(2)
            img = await page.screenshot(type="jpeg", quality=50)
            b64 = base64.b64encode(img).decode()
            return {"req_id": req_id, "ok": True, "screenshot": b64,
                    "message": "TikTok Upload открыт."}

        elif action == "get_stats":
            page = await ensure_browser()
            platform = cmd.get("platform", "instagram")
            if platform == "instagram":
                await page.goto("https://www.instagram.com/", timeout=30000)
            elif platform == "tiktok":
                await page.goto("https://www.tiktok.com/", timeout=30000)
            await asyncio.sleep(3)
            img = await page.screenshot(type="jpeg", quality=50)
            b64 = base64.b64encode(img).decode()
            return {"req_id": req_id, "ok": True, "screenshot": b64}

        elif action == "ping":
            return {"req_id": req_id, "ok": True, "message": "Desktop agent alive",
                    "platform": sys.platform, "time": datetime.now().isoformat()}

        else:
            return {"req_id": req_id, "ok": False, "error": f"Unknown action: {action}"}

    except Exception as e:
        return {"req_id": req_id, "ok": False, "error": str(e)}

async def main():
    print(f"NEXUS AI Desktop Agent")
    print(f"Server: {WS_URL}")
    print(f"Headless: {HEADLESS}")
    print(f"Connecting...")

    while True:
        try:
            headers = {}
            if args.token:
                headers["Authorization"] = f"Bearer {args.token}"

            # Совместимость версий websockets: новые используют additional_headers,
            # старые — extra_headers.
            try:
                conn = websockets.connect(WS_URL, additional_headers=headers)
            except TypeError:
                conn = websockets.connect(WS_URL, extra_headers=headers)

            async with conn as ws:
                print(f"✅ Connected to NEXUS AI server!")
                async for message in ws:
                    cmd = json.loads(message)
                    print(f"← {cmd.get('action')} {cmd.get('req_id', '')[:8]}")
                    result = await handle_command(cmd)
                    await ws.send(json.dumps(result))
                    print(f"→ {result.get('ok')} {result.get('message', result.get('error', ''))[:60]}")

        except Exception as e:
            print(f"❌ Connection lost: {e}")
            print("Reconnecting in 5s...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())