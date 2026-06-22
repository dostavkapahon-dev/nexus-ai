"""
Autonomous vision browser agent ("brain").
========================================
Drives the local desktop_agent.py (the "hands") to complete marketing and
business tasks described in natural language.

Loop:
  screenshot  ->  Claude (vision + tools)  ->  decide next action
              ->  send action to desktop agent  ->  repeat until done.

The desktop agent runs a real Chromium browser on the user's PC, so the agent
acts inside the user's own logged-in sessions (Instagram, OLX, Ads Manager,
etc.). Keys live on the server; only browser commands cross the WebSocket.
"""
import os
import json

import anthropic

from api.routes_desktop import send_to_desktop

# Vision-capable model. Sonnet 4.6 understands screenshots and tool use.
VISION_MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """\
Ты — автономный браузерный агент, выполняющий маркетинговые и бизнес-задачи.
Ты управляешь реальным браузером Chromium на ПК пользователя через инструменты.
Пользователь уже залогинен в свои аккаунты (Instagram, OLX, Facebook Ads и т.д.).

Принципы работы:
- На каждом шаге тебе дают свежий СКРИНШОТ и текущий URL. Смотри на экран и
  решай ОДНО следующее действие.
- Кликай по координатам (x, y) центра нужного элемента, опираясь на скриншот.
  Координаты — в пикселях от левого верхнего угла видимой области.
- Чтобы ввести текст: сначала click по полю, потом type_text.
- Если страница ещё грузится — используй wait, затем сделай новый скриншот.
- Прокручивай (scroll) когда нужный элемент не виден.
- Действуй маленькими проверяемыми шагами. После каждого действия ты увидишь
  результат на следующем скриншоте.
- Когда задача выполнена — вызови done с кратким отчётом.
- Если требуется ввод, которого у тебя нет (пароль, код 2FA, оплата, неоднозначный
  выбор), вызови ask с конкретным вопросом и остановись. НЕ выдумывай данные.
- Соблюдай правила площадок: не делай массовый спам и обходы защит.
"""

TOOLS = [
    {
        "name": "navigate",
        "description": "Открыть URL в браузере.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "click",
        "description": "Кликнуть по координатам (x, y) центра элемента на скриншоте.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "number"},
                "y": {"type": "number"},
            },
            "required": ["x", "y"],
        },
    },
    {
        "name": "type_text",
        "description": "Напечатать текст в сфокусированное поле (обычно после click).",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "clear": {"type": "boolean", "description": "Очистить поле перед вводом."},
            },
            "required": ["text"],
        },
    },
    {
        "name": "key",
        "description": "Нажать клавишу, напр. Enter, Tab, Escape.",
        "input_schema": {
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
        },
    },
    {
        "name": "scroll",
        "description": "Прокрутить страницу по вертикали. dy>0 вниз, dy<0 вверх.",
        "input_schema": {
            "type": "object",
            "properties": {"dy": {"type": "integer"}},
            "required": ["dy"],
        },
    },
    {
        "name": "wait",
        "description": "Подождать N секунд (загрузка страницы/анимации).",
        "input_schema": {
            "type": "object",
            "properties": {"seconds": {"type": "number"}},
            "required": ["seconds"],
        },
    },
    {
        "name": "back",
        "description": "Вернуться на предыдущую страницу.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "done",
        "description": "Задача выполнена. Передай краткий отчёт о результате.",
        "input_schema": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
    },
    {
        "name": "ask",
        "description": "Нужен ввод/решение пользователя. Останавливает агента.",
        "input_schema": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
    },
]

# Map agent tool -> desktop_agent.py action payload.
_ACTION_MAP = {
    "navigate": lambda i: {"action": "navigate", "url": i["url"]},
    "click": lambda i: {"action": "click_xy", "x": i["x"], "y": i["y"]},
    "type_text": lambda i: {"action": "type_text", "text": i["text"], "clear": i.get("clear", False)},
    "key": lambda i: {"action": "key", "key": i["key"]},
    "scroll": lambda i: {"action": "scroll", "dy": i["dy"]},
    "wait": lambda i: {"action": "wait", "seconds": i.get("seconds", 2)},
    "back": lambda i: {"action": "back"},
}


async def _screenshot() -> dict:
    return await send_to_desktop({"action": "screenshot"}, timeout=30.0)


def _image_block(b64: str) -> dict:
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
    }


def _strip_old_images(messages: list) -> None:
    """Keep only the most recent screenshot to bound token usage."""
    seen = False
    for msg in reversed(messages):
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "image":
                if seen:
                    block.clear()
                    block.update({"type": "text", "text": "[предыдущий скриншот опущен]"})
                else:
                    seen = True


async def _run_anthropic(task: str, start_url: str | None = None, max_steps: int = 25) -> dict:
    """Run the vision loop until the task is done, blocked, or steps run out."""
    client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    if start_url:
        await send_to_desktop({"action": "navigate", "url": start_url}, timeout=40.0)

    steps: list[dict] = []
    messages: list[dict] = []

    shot = await _screenshot()
    messages.append({
        "role": "user",
        "content": [
            {"type": "text", "text": f"ЗАДАЧА: {task}\n\nТекущий URL: {shot.get('url', '?')}\n"
                                     f"Размер экрана: {shot.get('width')}x{shot.get('height')}\nСкриншот:"},
            _image_block(shot["screenshot"]),
        ],
    })

    for step in range(max_steps):
        _strip_old_images(messages)
        resp = await client.messages.create(
            model=VISION_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        tool_use = next((b for b in resp.content if b.type == "tool_use"), None)
        thought = next((b.text for b in resp.content if b.type == "text"), "")

        if tool_use is None:
            return {"status": "stopped", "reason": "no_action",
                    "message": thought, "steps": steps}

        name, inp = tool_use.name, tool_use.input
        steps.append({"step": step + 1, "thought": thought, "action": name, "input": inp})

        if name == "done":
            return {"status": "done", "summary": inp.get("summary", ""), "steps": steps}
        if name == "ask":
            return {"status": "needs_input", "question": inp.get("question", ""), "steps": steps}

        # Execute the browser action on the user's PC.
        try:
            payload = _ACTION_MAP[name](inp)
            result = await send_to_desktop(payload, timeout=45.0)
            ok = result.get("ok", False)
            err = result.get("error", "")
        except Exception as e:
            ok, err = False, str(e)

        # Fresh screenshot as the tool result so the model sees the outcome.
        try:
            shot = await _screenshot()
            tool_result_content = [
                {"type": "text",
                 "text": f"Действие {'выполнено' if ok else 'ОШИБКА: ' + err}. "
                         f"URL: {shot.get('url', '?')}. Новый скриншот:"},
                _image_block(shot["screenshot"]),
            ]
        except Exception as e:
            tool_result_content = [{"type": "text", "text": f"Действие статус ok={ok}. "
                                                            f"Не удалось снять скриншот: {e}"}]

        messages.append({
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": tool_result_content,
            }],
        })

    return {"status": "max_steps", "message": f"Достигнут лимит {max_steps} шагов.", "steps": steps}


# ── Провайдер зрения: Anthropic (если есть ключ) → иначе Google Gemini ─────────
def vision_provider() -> str | None:
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("GEMINI_API_KEY"):
        return "google"
    return None


GEMINI_VISION_MODEL = os.getenv("NEXUS_VISION_GEMINI_MODEL", "gemini-2.0-flash")

_GEMINI_ACTIONS_DOC = """\
Верни СТРОГО ОДИН JSON-объект (без markdown, без пояснений вокруг) одного из видов:
{"action":"navigate","url":"https://..."}        — открыть URL
{"action":"click","x":123,"y":456}               — клик по координатам центра элемента
{"action":"type_text","text":"...","clear":false}— ввести текст в сфокусированное поле
{"action":"key","key":"Enter"}                   — нажать клавишу
{"action":"scroll","dy":600}                     — прокрутить (dy>0 вниз)
{"action":"wait","seconds":2}                    — подождать загрузку
{"action":"back"}                                — назад
{"action":"done","summary":"..."}                — задача выполнена
{"action":"ask","question":"..."}                — нужен ввод пользователя (пароль/2FA/файл)
Можно добавить поле "thought" с кратким обоснованием.
"""


async def _run_gemini(task: str, start_url: str | None = None, max_steps: int = 25) -> dict:
    """Тот же vision-loop, но на бесплатном Google Gemini (JSON-протокол действий)."""
    import json as _json
    import base64 as _b64
    import google.generativeai as genai

    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel(
        GEMINI_VISION_MODEL,
        system_instruction=SYSTEM_PROMPT + "\n\n" + _GEMINI_ACTIONS_DOC,
        generation_config={"response_mime_type": "application/json"},
    )

    if start_url:
        await send_to_desktop({"action": "navigate", "url": start_url}, timeout=40.0)

    steps: list[dict] = []
    history = ""
    shot = await _screenshot()

    for step in range(max_steps):
        img_bytes = _b64.b64decode(shot["screenshot"])
        prompt = (f"ЗАДАЧА: {task}\n\nИстория действий:\n{history or '—'}\n\n"
                  f"Текущий URL: {shot.get('url', '?')}\n"
                  f"Размер экрана: {shot.get('width')}x{shot.get('height')}\n"
                  f"Реши следующее действие. Текущий скриншот:")
        resp = await asyncio.to_thread(
            model.generate_content, [prompt, {"mime_type": "image/jpeg", "data": img_bytes}]
        )
        raw = (getattr(resp, "text", "") or "").strip()
        try:
            s, e = raw.find("{"), raw.rfind("}") + 1
            data = _json.loads(raw[s:e])
        except Exception:
            return {"status": "stopped", "reason": "bad_json", "message": raw[:300], "steps": steps}

        action = data.get("action", "")
        thought = data.get("thought", "")
        steps.append({"step": step + 1, "thought": thought, "action": action, "input": data})

        if action == "done":
            return {"status": "done", "summary": data.get("summary", ""), "steps": steps}
        if action == "ask":
            return {"status": "needs_input", "question": data.get("question", ""), "steps": steps}

        try:
            payload = _ACTION_MAP[action](data)
            result = await send_to_desktop(payload, timeout=45.0)
            ok, err = result.get("ok", False), result.get("error", "")
        except Exception as ex:
            ok, err = False, str(ex)

        history += f"\n{step + 1}. {action} -> {'ok' if ok else 'ОШИБКА: ' + err}"
        try:
            shot = await _screenshot()
        except Exception as ex:
            return {"status": "stopped", "reason": "screenshot_failed", "message": str(ex), "steps": steps}

    return {"status": "max_steps", "message": f"Достигнут лимит {max_steps} шагов.", "steps": steps}


async def run_agent(task: str, start_url: str | None = None, max_steps: int = 25) -> dict:
    """Запуск браузерного агента на доступном провайдере зрения."""
    provider = vision_provider()
    if provider == "anthropic":
        return await _run_anthropic(task, start_url, max_steps)
    if provider == "google":
        return await _run_gemini(task, start_url, max_steps)
    return {"status": "error",
            "error": "Нет ключа Anthropic или Google. Добавь GEMINI_API_KEY (бесплатно) "
                     "или ANTHROPIC_API_KEY в Подключениях."}