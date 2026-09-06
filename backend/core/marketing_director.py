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
- analyze: получить реальные данные аккаунта (Instagram/TikTok/YouTube) или разбор чужого
  ролика по ссылке. ВСЕГДА вызывай analyze ПЕРЕД созданием контента — решения по теме, хуку
  и формату должны идти от реальных цифр аккаунта и того, что уже заходило, а не вслепую.
- delegate: отдать текстовую подзадачу другой нейросети (см. список ниже).
- web_search / open_url / research: искать в интернете. Ты не ограничен списком
  сайтов — сам решай, где искать: тренды, темы, конкуренты, референсы, ниша,
  новости, популярные форматы, проверка фактов, идеи. Если данных не хватает,
  сперва ищи, а не выдумывай.
- run_browser: автономный браузерный агент на ПК пользователя (живые сессии
  Instagram/OLX/VK/YouTube). Используй для действий, у которых нет API.
- make_video: короткое видео. HIXIIT сам подбирает модель; аватар-озвучка — HeyGen.
- make_image: изображение/кадр/обложка через HIXIIT.
- publish: публикация готового текста (+картинки) на площадку через API или браузер.
- done: заверши работу с кратким отчётом для пользователя.

Принципы:
- Действуй конкретными шагами, по одному инструменту за раз.
- Ты — управляющий, а не копирайтер. Любой текст (посты, сценарии, заголовки,
  разбор данных) отдавай через delegate дешёвому исполнителю и проверяй результат.
  Сам пиши только план, критику и итоговый отчёт.
- Бери самого дешёвого исполнителя, который справится; дороже — только если
  дешёвый уже вернул слабый результат.
- Учитывай правила площадок: без спама и обхода защит.
- Если не хватает данных (доступ, файл, бюджет) — заверши через done и чётко
  перечисли, что нужно от пользователя.
- Отвечай и пиши отчёты на русском.
"""


async def _full_system() -> str:
    """Профиль пользователя + бренд-мозг + инструкции директора по инструментам.

    Профиль идёт первым: заданные пользователем ниша, цели и ограничения важнее
    общих правил, зашитых в код. Без него дирижёр работал по чужому брифу.
    """
    from core.dispatch import executors_doc
    base = SYSTEM + "\n\n--- ИСПОЛНИТЕЛИ ДЛЯ delegate (только эти доступны) ---\n" + executors_doc()
    try:
        from agents.registry import agents_doc
        doc = agents_doc()
        if doc:
            base += "\n\n" + doc
    except Exception:
        pass
    try:
        from core.brand import system_prompt
        base = await system_prompt() + "\n\n--- ИНСТРУМЕНТЫ ДИРЕКТОРА ---\n" + base
    except Exception:
        pass
    try:
        from core.agent_profile import as_prompt
        profile = await as_prompt()
        if profile:
            return profile + "\n" + base
    except Exception:
        pass
    return base

TOOLS = [
    {
        "name": "delegate",
        "description": ("Отдать текстовую подзадачу другой нейросети и получить её ответ. "
                        "Основной рабочий инструмент: тексты, сценарии, анализ, идеи."),
        "input_schema": {
            "type": "object",
            "properties": {
                "executor": {"type": "string",
                             "description": ("Имя исполнителя-модели ИЛИ ключ агента "
                                             "из списка в системном промпте (research, "
                                             "copywriter, content_strategist и т.д.).")},
                "task": {"type": "string", "description": "Что именно сделать — конкретно и полно."},
                "system": {"type": "string", "description": "Роль исполнителя, если нужна особая."},
                "context": {"type": "string", "description": "Данные, на которые опираться."},
            },
            "required": ["executor", "task"],
        },
    },
    {
        "name": "web_search",
        "description": ("Найти информацию в интернете. Любые сайты и темы: тренды, "
                        "конкуренты, референсы, новости, форматы, проверка фактов. "
                        "Возвращает список ссылок с кратким описанием."),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Поисковый запрос словами."},
                "max_results": {"type": "integer", "description": "Сколько результатов (по умолчанию 8)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "open_url",
        "description": "Открыть страницу и прочитать её текст. Используй после web_search.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "research",
        "description": ("Исследовать тему целиком: поиск, чтение нескольких страниц и "
                        "выжимка. Результат сохраняется в историю исследований."),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Что исследуем."},
                "pages": {"type": "integer", "description": "Сколько страниц прочитать (1–5)."},
            },
            "required": ["topic"],
        },
    },
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
        "name": "analyze",
        "description": ("Получить реальные данные аккаунта или разбор чужого ролика. "
                        "Вызывай ПЕРЕД созданием контента, чтобы решения шли от фактов, "
                        "а не вслепую."),
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "enum": ["instagram", "tiktok", "youtube", "url"],
                           "description": "Площадка для досье аккаунта, либо 'url' для разбора ролика по ссылке."},
                "handle": {"type": "string",
                           "description": "Ник аккаунта (опц., иначе берётся свой из настроек) "
                                          "или ССЫЛКА на ролик, если target='url'."},
            },
            "required": ["target"],
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
        "name": "make_image",
        "description": "Сгенерировать изображение (кадр, обложка, визуал поста) через HIXIIT. "
                       "Модель HIXIIT подбирает сам под задачу.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Визуальное описание кадра."},
                "ratio": {"type": "string", "enum": ["9:16", "16:9", "1:1"]},
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
    if name == "delegate":
        executor = (inp.get("executor") or "").strip().lower()
        # Сначала роль агента, потом модель: имена не пересекаются, а роль несёт
        # свою специализацию и своего исполнителя.
        from agents.registry import get as get_agent, run as run_agent_role
        if get_agent(executor):
            return await run_agent_role(executor, inp.get("task", ""),
                                        inp.get("context", ""))
        from core.dispatch import delegate
        return await delegate(executor=executor, task=inp.get("task", ""),
                              system=inp.get("system", ""), context=inp.get("context", ""))
    if name == "web_search":
        from core.websearch import search
        return await search(inp.get("query", ""), int(inp.get("max_results") or 8))
    if name == "open_url":
        from core.websearch import fetch
        res = await fetch(inp.get("url", ""))
        # Полный текст страницы в контекст модели не отдаём: это тысячи токенов
        # на каждый шаг, а решения принимаются по сути, а не по вёрстке.
        if res.get("ok"):
            res = {**res, "text": res["text"][:6000]}
        return res
    if name == "research":
        from core.websearch import deep_research
        return await deep_research(inp.get("topic", ""), int(inp.get("pages") or 3))
    if name == "run_browser":
        from core.browser_agent import run_agent
        return await run_agent(task=inp["task"], start_url=inp.get("start_url"), max_steps=20)
    if name == "analyze":
        target = (inp.get("target") or "").strip().lower()
        handle = (inp.get("handle") or "").strip()
        if target == "url" or handle.startswith("http"):
            from core.viral_research import analyze_reference
            return await analyze_reference(handle or inp.get("target", ""))
        # Явный ник конкурента — разбираем именно его; иначе свой из настроек.
        if handle:
            try:
                from core.social_intel import _remember
                data = None
                if target == "instagram":
                    from core.instagram_reader import analyze as ig
                    data = await ig(handle)
                elif target == "youtube":
                    from core.youtube_reader import analyze as yt
                    data = await yt(handle)
                elif target == "tiktok":
                    from core.social_intel import _fetch_channel
                    data = await _fetch_channel("tiktok", handle.lstrip("@"))
                if data is not None:
                    # Разбор по явному нику тоже остаётся в памяти — к нему
                    # возвращаются вопросом «что там у конкурента».
                    await _remember(data)
                    return data
            except Exception as e:
                return {"ok": False, "error": str(e)[:200]}
        from core.social_intel import get_account_intelligence
        return await get_account_intelligence([target] if target else None)
    if name == "make_video":
        provider = inp.get("provider", "auto")
        # Говорящий аватар умеет только HeyGen — там generate_clip незаменим.
        # Всё остальное ведёт HIXIIT: он сам выбирает модель под задачу.
        voiceover = bool(inp.get("script")) and bool(os.getenv("HEYGEN_API_KEY"))
        if provider in ("heygen", "runway") or voiceover:
            from core.media_generator import generate_clip
            return await generate_clip(prompt=inp["prompt"], script=inp.get("script", ""),
                                       provider="heygen" if voiceover else provider)
        from core.hixiit import generate as hixiit_generate
        return await hixiit_generate(inp["prompt"], kind="video", ratio=inp.get("ratio"))
    if name == "make_image":
        from core.hixiit import generate as hixiit_generate
        return await hixiit_generate(inp["prompt"], kind="image", ratio=inp.get("ratio"))
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
            model=DIRECTOR_MODEL, max_tokens=1500, system=await _full_system(), tools=TOOLS, messages=messages,
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
        step = {"action": name, "input": inp, "thought": thought,
                "result_ok": result.get("ok", result.get("status") == "done")}
        if name == "delegate":
            step.update({"executor": result.get("executor"),
                         "model_used": result.get("model_used"),
                         "cost": result.get("cost")})
        # Ссылку на готовое медиа несём в шаге — иначе картинка и видео
        # остаются только внутри дирижёра и до человека не доходят.
        if name in ("make_image", "make_video") and result.get("url"):
            step["media_url"] = result["url"]
        steps.append(step)
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
{"tool":"analyze","args":{"target":"instagram|tiktok|youtube|url","handle":"ник или ссылка (опц.)"}}
{"tool":"delegate","args":{"executor":"deepseek","task":"...","system":"...","context":"..."}}
{"tool":"web_search","args":{"query":"что ищем","max_results":8}}
{"tool":"open_url","args":{"url":"https://..."}}
{"tool":"research","args":{"topic":"тема исследования","pages":3}}
{"tool":"run_browser","args":{"task":"...","start_url":"..."}}
{"tool":"make_video","args":{"prompt":"...","script":"...","provider":"auto"}}
{"tool":"make_image","args":{"prompt":"...","ratio":"9:16"}}
{"tool":"publish","args":{"platform":"instagram","text":"...","image_url":"..."}}
{"tool":"done","args":{"summary":"..."}}
Можно добавить поле "thought" с кратким планом/обоснованием.
"""


async def _run_director_gemini(goal: str, context: str = "", max_steps: int = 12) -> dict:
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel(
        GEMINI_DIRECTOR_MODEL,
        system_instruction=await _full_system() + "\n\n" + _GEMINI_DIRECTOR_DOC,
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
        step = {"action": tool, "input": args, "thought": thought, "result_ok": ok}
        if tool == "delegate":
            step.update({"executor": result.get("executor"),
                         "model_used": result.get("model_used"),
                         "cost": result.get("cost")})
        if tool in ("make_image", "make_video") and result.get("url"):
            step["media_url"] = result["url"]
        steps.append(step)
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
