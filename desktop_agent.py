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

async def ensure_browser():
    global _browser, _page, _playwright
    if _browser is None:
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(headless=HEADLESS)
        _page = await _browser.new_page()
    return _page

async def handle_command(cmd: dict) -> dict:
    action = cmd.get("action", "")
    req_id = cmd.get("req_id", "")

    try:
        if action == "screenshot":
            page = await ensure_browser()
            img = await page.screenshot(type="jpeg", quality=60)
            b64 = base64.b64encode(img).decode()
            return {"req_id": req_id, "ok": True, "screenshot": b64, "url": page.url}

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

            async with websockets.connect(WS_URL, extra_headers=headers) as ws:
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