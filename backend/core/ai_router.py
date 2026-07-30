import os
import time
import asyncio
import anthropic
import openai
import google.generativeai as genai

AI_ROUTING = {
    # Anthropic
    "claude-sonnet-4-6": "anthropic",
    "claude-sonnet-4-20250514": "anthropic",
    "claude-haiku-4-5-20251001": "anthropic",
    # OpenAI
    "gpt-4o": "openai",
    "gpt-4o-mini": "openai",
    # Google (модели 1.5 отключены Google — не используем)
    "gemini-2.0-flash": "google",
    "gemini-2.5-flash": "google",
    "gemini-flash-latest": "google",
    "gemini-2.0-flash-lite": "google",
    # Perplexity
    "sonar-pro": "perplexity",
    "sonar-reasoning-pro": "perplexity",
    "sonar": "perplexity",
    # DeepSeek
    "deepseek-chat": "deepseek",
    "deepseek-reasoner": "deepseek",
    # Бесплатные провайдеры (NVIDIA, Groq, Cerebras, OpenRouter, Mistral, GitHub)
    # добавляются ниже из FREE_PROVIDERS — по псевдониму на каждого.
}

# Резерв на случай сбоя основной модели. Порядок «дёшево → дорого»:
# сначала самые дешёвые/бесплатные, Claude — в самом конце как надёжный мозг.
# У каждой Gemini-модели свой лимит бесплатной квоты, поэтому в цепочке их
# несколько: упёрлись в 429 на одной — пробуем следующую.
# Бесплатные идут первыми (их порядок задаёт FREE_PROVIDERS), затем платные
# «дёшево → дорого». Сама цепочка собирается ниже, когда известен реестр.
PAID_FALLBACK_CHAIN = ["gemini-2.0-flash-lite", "gemini-2.0-flash", "gemini-flash-latest",
                       "deepseek-chat", "gpt-4o-mini", "claude-sonnet-4-6"]

# Какая env-переменная с ключом нужна каждому провайдеру.
PROVIDER_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GEMINI_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    # ключи бесплатных провайдеров добавляются из FREE_PROVIDERS
}


_GEMINI_RESOLVED = None


def resolve_gemini_model() -> str | None:
    """Спрашивает у Google, какие модели реально доступны этому ключу,
    и возвращает лучшую flash-модель. Результат кэшируется.

    Избавляет от ошибок «модель не найдена», когда Google меняет линейку.
    """
    global _GEMINI_RESOLVED
    if _GEMINI_RESOLVED:
        return _GEMINI_RESOLVED
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        return None
    try:
        import httpx
        r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models",
                      params={"key": key}, timeout=15)
        names = [m.get("name", "").replace("models/", "")
                 for m in r.json().get("models", [])
                 if "generateContent" in (m.get("supportedGenerationMethods") or [])]
    except Exception:
        return None
    if not names:
        return None
    # Приоритет: свежие flash (дёшево и быстро) → любые flash → что есть.
    # Приоритет по РАЗМЕРУ бесплатной квоты: lite-модели щедрее «старших».
    for pref in ("flash-lite", "gemini-2.0-flash", "gemini-2.5-flash", "flash"):
        hits = [n for n in names if pref in n and "vision" not in n
                and "thinking" not in n and "exp" not in n]
        if hits:
            _GEMINI_RESOLVED = sorted(hits, key=len)[0]
            return _GEMINI_RESOLVED
    _GEMINI_RESOLVED = names[0]
    return _GEMINI_RESOLVED


# ── Бесплатные OpenAI-совместимые провайдеры ──────────────────────────────────
# Все они говорят на диалекте OpenAI (/v1/chat/completions + /v1/models),
# поэтому вместо метода на каждого — один реестр и один вызов.
#
# `prefs` — подсказки для поиска по каталогу в порядке убывания предпочтения.
# Конкретные id моделей везде живут недолго, поэтому не зашиваем их: на первом
# вызове спрашиваем /models и выбираем лучшую из реально доступных ключу.
FREE_PROVIDERS: dict[str, dict] = {
    "nvidia": {
        "alias": "nvidia-free",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "key_env": "NVIDIA_API_KEY",
        "title": "NVIDIA NIM",
        "signup": "https://build.nvidia.com/settings/api-keys",
        "limits": "1000 кредитов при регистрации, 40 запросов/мин",
        "prefs": ("llama-3.3-70b-instruct", "nemotron", "llama-3.1-70b-instruct",
                  "qwen2.5-72b-instruct", "deepseek-r1", "gemma", "llama"),
    },
    "groq": {
        "alias": "groq-free",
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "title": "Groq",
        "signup": "https://console.groq.com/keys",
        "limits": "30 запросов/мин, 1000/сутки — самая быстрая бесплатная выдача",
        "prefs": ("llama-3.3-70b-versatile", "llama-3.1-70b", "llama-3.1-8b-instant",
                  "qwen", "gemma2", "llama"),
    },
    "cerebras": {
        "alias": "cerebras-free",
        "base_url": "https://api.cerebras.ai/v1",
        "key_env": "CEREBRAS_API_KEY",
        "title": "Cerebras",
        "signup": "https://cloud.cerebras.ai",
        "limits": "около 1 млн токенов в сутки — годится для пакетной работы",
        "prefs": ("llama-3.3-70b", "qwen-3", "llama3.1-70b", "llama"),
    },
    "openrouter": {
        "alias": "openrouter-free",
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "title": "OpenRouter",
        "signup": "https://openrouter.ai/keys",
        "limits": "~30 бесплатных моделей, 20 запросов/мин, 50 в сутки",
        # У OpenRouter бесплатные модели помечены суффиксом «:free» — берём только их,
        # иначе легко уйти на платную и списать деньги.
        "prefs": (":free",),
        "require_pref": True,
    },
    "mistral": {
        "alias": "mistral-free",
        "base_url": "https://api.mistral.ai/v1",
        "key_env": "MISTRAL_API_KEY",
        "title": "Mistral",
        "signup": "https://console.mistral.ai/api-keys",
        "limits": "бесплатный тариф на все модели, ~2 запроса/мин",
        "prefs": ("mistral-large", "mistral-small", "open-mixtral", "mistral"),
    },
    "github": {
        "alias": "github-free",
        "base_url": "https://models.github.ai/inference",
        "key_env": "GITHUB_MODELS_TOKEN",
        "title": "GitHub Models",
        "signup": "https://github.com/settings/tokens (classic token, права models:read)",
        "limits": "100+ моделей по обычному токену GitHub, суточные лимиты",
        "models_path": "/catalog/models",   # у GitHub каталог лежит не на /models
        "prefs": ("gpt-4o-mini", "llama-3.3-70b", "gpt-4o", "phi-4", "mistral"),
    },
}

# Псевдоним модели → имя провайдера. Псевдоним и есть то, что просят у роутера.
FREE_ALIASES = {spec["alias"]: name for name, spec in FREE_PROVIDERS.items()}

_FREE_RESOLVED: dict[str, str] = {}


def free_provider_of(model: str) -> str | None:
    """Имя бесплатного провайдера по псевдониму модели."""
    return FREE_ALIASES.get(model)


def resolve_free_model(provider: str) -> str | None:
    """Спрашивает у провайдера список моделей и выбирает лучшую доступную.

    Каталоги у всех обновляются постоянно, поэтому зашитый id рано или поздно
    отвалится с «model not found». Результат кэшируется на процесс.
    """
    if provider in _FREE_RESOLVED:
        return _FREE_RESOLVED[provider]
    spec = FREE_PROVIDERS.get(provider)
    if not spec:
        return None
    key = os.getenv(spec["key_env"], "")
    if not key:
        return None
    try:
        import httpx
        url = spec["base_url"] + spec.get("models_path", "/models")
        r = httpx.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=20)
        payload = r.json()
        raw = payload.get("data") if isinstance(payload, dict) else payload
        ids = [(m.get("id") or m.get("name") or "") for m in (raw or [])]
    except Exception:
        return None
    ids = [i for i in ids if i and "embed" not in i.lower() and "rerank" not in i.lower()]
    if not ids:
        return None
    for pref in spec["prefs"]:
        hits = [i for i in ids if pref in i.lower()]
        if hits:
            _FREE_RESOLVED[provider] = sorted(hits, key=len)[0]
            return _FREE_RESOLVED[provider]
    # У OpenRouter «любая модель» означает платную — лучше честно не найти ничего.
    if spec.get("require_pref"):
        return None
    _FREE_RESOLVED[provider] = ids[0]
    return _FREE_RESOLVED[provider]


# Совместимость: NVIDIA появилась раньше остальных и зовётся отдельно.
NVIDIA_BASE_URL = FREE_PROVIDERS["nvidia"]["base_url"]


def resolve_nvidia_model() -> str | None:
    return resolve_free_model("nvidia")


def _has_key(model: str) -> bool:
    """Есть ли ключ у провайдера этой модели (иначе нет смысла её пробовать)."""
    provider = AI_ROUTING.get(model, "openai")
    return bool(os.getenv(PROVIDER_KEY_ENV.get(provider, ""), ""))

PREMIUM_MODELS = {
    "niche_analyst": "sonar-pro",
    "viral_hunter": "sonar-reasoning-pro",
    "strategist": "claude-sonnet-4-6",
    "copywriter": "gpt-4o",
    "reviewer": "claude-sonnet-4-6",
    "voice_adapter": "claude-sonnet-4-6",
    "visual_creator": "gpt-4o",
    "adapter": "gpt-4o",
}

ECONOMY_MODELS = {
    "niche_analyst": "deepseek-chat",
    "viral_hunter": "gemini-2.0-flash-lite",
    "strategist": "deepseek-chat",
    "copywriter": "deepseek-chat",
    "reviewer": "gemini-2.0-flash-lite",
    "voice_adapter": "deepseek-chat",
    "visual_creator": "gpt-4o-mini",
    "adapter": "gpt-4o-mini",
}

COST_PER_1K = {
    "claude-sonnet-4-6": 0.003,
    "claude-sonnet-4-20250514": 0.003,
    "claude-haiku-4-5-20251001": 0.00025,
    "gpt-4o": 0.005,
    "gpt-4o-mini": 0.00015,
    "gemini-2.0-flash": 0.0001,
    "gemini-flash-latest": 0.0001,
    "gemini-2.0-flash-lite": 0.00005,
    "gemini-2.5-flash": 0.0003,
    "sonar": 0.001,
    "sonar-pro": 0.003,
    "sonar-reasoning-pro": 0.005,
    "deepseek-chat": 0.00014,
    "deepseek-reasoner": 0.00055,
    # бесплатные псевдонимы получают цену 0.0 ниже
}

# Регистрируем бесплатных в общих таблицах роутера: маршрутизация по провайдеру,
# ключ окружения и нулевая цена (тратятся их квоты/кредиты, а не деньги).
for _name, _spec in FREE_PROVIDERS.items():
    AI_ROUTING[_spec["alias"]] = _name
    PROVIDER_KEY_ENV[_name] = _spec["key_env"]
    COST_PER_1K[_spec["alias"]] = 0.0

# Бесплатное пробуем раньше платного.
FALLBACK_CHAIN = [s["alias"] for s in FREE_PROVIDERS.values()] + PAID_FALLBACK_CHAIN

def estimate_cost(ai_mode: str, posts_per_day: int, days: int) -> float:
    models = PREMIUM_MODELS if ai_mode == "premium" else ECONOMY_MODELS
    avg_tokens = 2000
    total_tokens = (3 * avg_tokens) + (posts_per_day * days * 8 * avg_tokens)
    avg_cost = sum(COST_PER_1K.get(m, 0.002) for m in models.values()) / len(models)
    return round(total_tokens / 1000 * avg_cost, 2)


class AIRouter:
    async def _call_claude(self, model, system, prompt):
        client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        msg = await client.messages.create(model=model, max_tokens=4096, system=system,
                                            messages=[{"role": "user", "content": prompt}])
        text = msg.content[0].text
        tokens = msg.usage.input_tokens + msg.usage.output_tokens
        return {"text": text, "tokens": tokens, "cost": tokens / 1000 * COST_PER_1K.get(model, 0.003), "model_used": model}

    async def _call_openai(self, model, system, prompt):
        client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = await client.chat.completions.create(model=model, max_tokens=4096,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}])
        text = resp.choices[0].message.content
        tokens = resp.usage.total_tokens
        return {"text": text, "tokens": tokens, "cost": tokens / 1000 * COST_PER_1K.get(model, 0.005), "model_used": model}

    async def _call_gemini(self, model, system, prompt):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        try:
            m = genai.GenerativeModel(model, system_instruction=system)
            resp = await asyncio.to_thread(m.generate_content, prompt)
        except Exception as e:
            # Модель недоступна для этого ключа → берём реально доступную.
            alt = await asyncio.to_thread(resolve_gemini_model)
            if not alt or alt == model:
                raise
            m = genai.GenerativeModel(alt, system_instruction=system)
            resp = await asyncio.to_thread(m.generate_content, prompt)
            model = alt
        text = resp.text
        tokens = len(text.split()) * 2
        return {"text": text, "tokens": tokens, "cost": tokens / 1000 * COST_PER_1K.get(model, 0.0001), "model_used": model}

    async def _call_perplexity(self, model, system, prompt):
        client = openai.AsyncOpenAI(api_key=os.getenv("PERPLEXITY_API_KEY"), base_url="https://api.perplexity.ai")
        resp = await client.chat.completions.create(model=model, max_tokens=4096,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}])
        text = resp.choices[0].message.content
        tokens = resp.usage.total_tokens if resp.usage else len(text.split()) * 2
        return {"text": text, "tokens": tokens, "cost": tokens / 1000 * COST_PER_1K.get(model, 0.003), "model_used": model}

    async def _call_free(self, model, system, prompt):
        """Любой бесплатный OpenAI-совместимый провайдер из FREE_PROVIDERS."""
        provider = free_provider_of(model) or model
        spec = FREE_PROVIDERS.get(provider)
        if not spec:
            raise RuntimeError(f"Неизвестный бесплатный провайдер: {model}")
        real = await asyncio.to_thread(resolve_free_model, provider)
        if not real:
            raise RuntimeError(f"{spec['title']}: не удалось получить список моделей "
                               f"(проверьте {spec['key_env']})")
        client = openai.AsyncOpenAI(api_key=os.getenv(spec["key_env"]), base_url=spec["base_url"])
        resp = await client.chat.completions.create(model=real, max_tokens=4096,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}])
        text = resp.choices[0].message.content
        tokens = resp.usage.total_tokens if resp.usage else len(text.split()) * 2
        # Тратятся квоты провайдера, а не деньги — в денежную стоимость не пишем.
        return {"text": text, "tokens": tokens, "cost": 0.0, "model_used": f"{provider}:{real}"}

    async def _call_nvidia(self, model, system, prompt):
        """Совместимость: NVIDIA — частный случай бесплатного провайдера."""
        return await self._call_free(model, system, prompt)

    async def _call_deepseek(self, model, system, prompt):
        client = openai.AsyncOpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
        resp = await client.chat.completions.create(model=model, max_tokens=4096,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}])
        text = resp.choices[0].message.content
        tokens = resp.usage.total_tokens if resp.usage else len(text.split()) * 2
        return {"text": text, "tokens": tokens, "cost": tokens / 1000 * COST_PER_1K.get(model, 0.00014), "model_used": model}

    async def call(self, model: str, system: str, prompt: str) -> dict:
        # Порядок: запрошенная модель → cheap-first фолбэк.
        ordered = [model] + [m for m in FALLBACK_CHAIN if m != model]
        # Пропускаем модели без ключа провайдера, чтобы не жечь время на заведомый сбой.
        with_keys = [m for m in ordered if _has_key(m)]
        # Если ключей нет вовсе (напр. локальный тест) — пробуем как есть.
        models_to_try = with_keys or ordered
        last_error = None
        errors = {}
        for m in models_to_try:
            provider = AI_ROUTING.get(m, "openai")
            for attempt in range(3):
                try:
                    t0 = time.time()
                    if provider == "anthropic":
                        result = await self._call_claude(m, system, prompt)
                    elif provider == "perplexity":
                        result = await self._call_perplexity(m, system, prompt)
                    elif provider == "deepseek":
                        result = await self._call_deepseek(m, system, prompt)
                    elif provider in FREE_PROVIDERS:
                        result = await self._call_free(m, system, prompt)
                    elif provider == "openai":
                        result = await self._call_openai(m, system, prompt)
                    else:
                        result = await self._call_gemini(m, system, prompt)
                    result["duration_sec"] = round(time.time() - t0, 2)
                    return result
                except Exception as e:
                    last_error = e
                    errors[m] = f"{type(e).__name__}: {str(e)[:180]}"
                    # Квота/недоступная модель — повторять бессмысленно, идём к следующей.
                    if any(s in str(e).lower() for s in
                           ("insufficient_quota", "resource_exhausted", "429", "not found", "unsupported", "deprecat")):
                        break
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
        detail = " | ".join(f"{m} → {err}" for m, err in errors.items()) or str(last_error)
        raise RuntimeError(f"All AI providers failed. {detail}")

ai_router = AIRouter()