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
    # Google
    "gemini-1.5-pro": "google",
    "gemini-1.5-flash": "google",
    # Perplexity
    "sonar-pro": "perplexity",
    "sonar-reasoning-pro": "perplexity",
    "sonar": "perplexity",
    # DeepSeek
    "deepseek-chat": "deepseek",
    "deepseek-reasoner": "deepseek",
}

FALLBACK_CHAIN = ["claude-sonnet-4-6", "gpt-4o", "deepseek-chat", "gemini-1.5-flash", "gpt-4o-mini"]

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
    "viral_hunter": "gemini-1.5-flash",
    "strategist": "deepseek-chat",
    "copywriter": "deepseek-chat",
    "reviewer": "gemini-1.5-flash",
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
    "gemini-1.5-flash": 0.000075,
    "gemini-1.5-pro": 0.00125,
    "sonar": 0.001,
    "sonar-pro": 0.003,
    "sonar-reasoning-pro": 0.005,
    "deepseek-chat": 0.00014,
    "deepseek-reasoner": 0.00055,
}

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
        m = genai.GenerativeModel(model, system_instruction=system)
        resp = await asyncio.to_thread(m.generate_content, prompt)
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

    async def _call_deepseek(self, model, system, prompt):
        client = openai.AsyncOpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
        resp = await client.chat.completions.create(model=model, max_tokens=4096,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}])
        text = resp.choices[0].message.content
        tokens = resp.usage.total_tokens if resp.usage else len(text.split()) * 2
        return {"text": text, "tokens": tokens, "cost": tokens / 1000 * COST_PER_1K.get(model, 0.00014), "model_used": model}

    async def call(self, model: str, system: str, prompt: str) -> dict:
        models_to_try = [model] + [m for m in FALLBACK_CHAIN if m != model]
        last_error = None
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
                    elif provider == "openai":
                        result = await self._call_openai(m, system, prompt)
                    else:
                        result = await self._call_gemini(m, system, prompt)
                    result["duration_sec"] = round(time.time() - t0, 2)
                    return result
                except Exception as e:
                    last_error = e
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
        raise RuntimeError(f"All AI providers failed. Last error: {last_error}")

ai_router = AIRouter()