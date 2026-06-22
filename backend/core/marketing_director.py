"""
Marketing Director — главный AI-дирижёр (запуск «через Claude отсюда»).
=====================================================================
Принимает бизнес-цель на естественном языке и сам координирует исполнителей:
  - браузерного агента (desktop_agent.py) для действий на сайтах,
  - генерацию видео (HeyGen / HiggsField / Runway),
  - публикацию текста/медиа на площадках (Telegram/Instagram/VK/...).

Работает на Claude через tool use: модель решает, какой инструмент вызвать,
сервер исполняет и возвращает результат, пока цель не достигнута.
"""
import os
import json
import asyncio

import anthropic

DIRECTOR_MODEL = "claude-sonnet-4-6"

SYSTEM = """\
Ты — директор по маркетингу NEXUS AI. Тебе ставят бизнес-цель, ты декомпозируешь
её и выполняешь через доступные инструменты. Доступные исполнители:
- run_browser: автономный браузерный агент на ПК пользователя (живые сессии
  Instagram/OLX/VK/YouTube). Используй для действий, у которых нет API.
- make_video: генерация короткого видео (аватар-озвучка или кинематографичный клип).
- publish: публикация готового текста (+картинки) на площадку через API или браузер.
- done: заверши работу с кратким отчётом для пользователя.

Принципы:
- Действуй конкретными шагами, по одному инструменту за раз.
- Учитывай правила площадок: без спама и обхода защит.
- Если не хватает данных (доступ, файл, бюджет) — заверши через done и чётко
  перечисли, что нужно от пользователя.
- Отвечай и пиши отчёты на русском.
"""

TOOLS = [
    {
        "name": "run_browser",
        "description": "Запустить браузерного агента на ПК для задачи на сайте.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Что сделать в браузере, словами."},
                "start_url": {"type": "string"},
            },
            "required": ["task"],
        },
    },
    {
        "name": "make_video",
        "description": "Сгенерировать короткое видео (Reels/Shorts/TikTok).",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Визуальное описание сцены."},
                "script": {"type": "string", "description": "Текст озвучки (для аватара)."},
                "provider": {"type": "string", "enum": ["auto", "heygen", "higgsfield", "runway"]},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "publish",
        "description": "Опубликовать текст (+картинку) на площадке.",
        "input_schema": {
            "type": "object",
            "properties": {
                "platform": {"type": "string", "enum": ["telegram", "instagram", "vk", "youtube", "tiktok"]},
                "text": {"type": "string"},
                "image_url": {"type": "string"},
            },
            "required": ["platform", "text"],
        },
    },
    {
        "name": "done",
        "description": "Завершить и вернуть отчёт пользователю.",
        "input_schema": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
    },
]


async def _exec_tool(name: str, inp: dict) -> dict:
    if name == "run_browser":
        from core.browser_agent import run_agent
        return await run_agent(task=inp["task"], start_url=inp.get("start_url"), max_steps=20)
    if name == "make_video":
        from core.media_generator import generate_clip
        return await generate_clip(prompt=inp["prompt"], script=inp.get("script", ""),
                                   provider=inp.get("provider", "auto"))
    if name == "publish":
        from core.orchestrator import nexus_core
        return await nexus_core._publish_one(inp["platform"], inp["text"], inp.get("image_url", ""))
    return {"ok": False, "error": f"unknown tool {name}"}


async def _run_director_anthropic(goal: str, context: str = "", max_steps: int = 12) -> dict:
    """Главный цикл дирижёра. Возвращает {'status', 'summary', 'steps'}."""
    client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    messages = [{
        "role": "user",
        "content": f"ЦЕЛЬ: {goal}\n\nКОНТЕКСТ: {context or '—'}\n\n"
                   f"Составь план и начни выполнять через инструменты.",
    }]
    steps = []
    for _ in range(max_steps):
        resp = await client.messages.create(
            model=DIRECTOR_MODEL, max_tokens=1500, system=SYSTEM, tools=TOOLS, messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})
        tool_use = next((b for b in resp.content if b.type == "tool_use"), None)
        thought = next((b.text for b in resp.content if b.type == "text"), "")

        if tool_use is None:
            return {"status": "stopped", "summary": thought, "steps": steps}

        name, inp = tool_use.name, tool_use.input
        if name == "done":
            steps.append({"action": "done", "thought": thought})
            return {"status": "done", "summary": inp.get("summary", ""), "steps": steps}

        result = await _exec_tool(name, inp)
        steps.append({"action": name, "input": inp, "thought": thought,
                      "result_ok": result.get("ok", result.get("status") == "done")})
        messages.append({
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": json.dumps(result, ensure_ascii=False)[:3000],
            }],
        })
    return {"status": "max_steps", "summary": "Достигнут лимит шагов дирижёра.", "steps": steps}


# ── Gemini-путь (бесплатный Google-ключ), JSON-протокол инструментов ───────────
GEMINI_DIRECTOR_MODEL = os.getenv("NEXUS_DIRECTOR_GEMINI_MODEL", "gemini-2.0-flash")

_GEMINI_DIRECTOR_DOC = """\
Верни СТРОГО ОДИН JSON-объект (без markdown) одного из видов:
{"tool":"run_browser","args":{"task":"...","start_url":"..."}}
{"tool":"make_video","args":{"prompt":"...","script":"...","provider":"auto"}}
{"tool":"publish","args":{"platform":"instagram","text":"...","image_url":"..."}}
{"tool":"done","args":{"summary":"..."}}
Можно добавить поле "thought" с кратким планом/обоснованием.
"""


async def _run_director_gemini(goal: str, context: str = "", max_steps: int = 12) -> dict:
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel(
        GEMINI_DIRECTOR_MODEL,
        system_instruction=SYSTEM + "\n\n" + _GEMINI_DIRECTOR_DOC,
        generation_config={"response_mime_type": "application/json"},
    )
    history = ""
    steps = []
    for _ in range(max_steps):
        prompt = (f"ЦЕЛЬ: {goal}\n\nКОНТЕКСТ: {context or '—'}\n\n"
                  f"Журнал выполнения:\n{history or '—'}\n\nРеши следующий шаг.")
        resp = await asyncio.to_thread(model.generate_content, prompt)
        raw = (getattr(resp, "text", "") or "").strip()
        try:
            s, e = raw.find("{"), raw.rfind("}") + 1
            data = json.loads(raw[s:e])
        except Exception:
            return {"status": "stopped", "summary": raw[:300], "steps": steps}

        tool = data.get("tool", "")
        args = data.get("args", {}) or {}
        thought = data.get("thought", "")
        if tool == "done":
            steps.append({"action": "done", "thought": thought})
            return {"status": "done", "summary": args.get("summary", thought), "steps": steps}

        result = await _exec_tool(tool, args)
        ok = result.get("ok", result.get("status") == "done")
        steps.append({"action": tool, "input": args, "thought": thought, "result_ok": ok})
        history += f"\n- {tool}: {'ok' if ok else 'ошибка'} :: {json.dumps(result, ensure_ascii=False)[:400]}"
    return {"status": "max_steps", "summary": "Достигнут лимит шагов дирижёра.", "steps": steps}


async def run_director(goal: str, context: str = "", max_steps: int = 12) -> dict:
    """Запуск дирижёра на доступном AI: Anthropic если есть ключ, иначе Gemini."""
    if os.getenv("ANTHROPIC_API_KEY"):
        return await _run_director_anthropic(goal, context, max_steps)
    if os.getenv("GEMINI_API_KEY"):
        return await _run_director_gemini(goal, context, max_steps)
    return {"status": "error",
            "summary": "Нет ключа Anthropic или Google. Добавь GEMINI_API_KEY (бесплатно) "
                       "или ANTHROPIC_API_KEY в Подключениях."}
