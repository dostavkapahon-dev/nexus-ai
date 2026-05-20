import os
import time
import asyncio
import anthropic
import openai
import google.generativeai as genai

AI_ROUTING = {
    "claude-sonnet-4-20250514": "anthropic",
    "claude-haiku-4-5-20251001": "anthropic",
    "gpt-4o": "openai",
    "gpt-4o-mini": "openai",
    "gemini-1.5-flash": "google",
}

FALLBACK_CHAIN = ["claude-sonnet-4-20250514", "gpt-4o", "gemini-1.5-flash", "gpt-4o-mini"]

class AIRouter:
    async def _call_claude(self, model: str, system: str, prompt: str) -> dict:
        client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        msg = await client.messages.create(
            model=model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": prompt}]
        )
        text = msg.content[0].text
        tokens = msg.usage.input_tokens + msg.usage.output_tokens
        cost = tokens * 0.000003
        return {"text": text, "tokens": tokens, "cost": cost, "model_used": model}

    async def _call_openai(self, model: str, system: str, prompt: str) -> dict:
        client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=4096
        )
        text = resp.choices[0].message.content
        tokens = resp.usage.total_tokens
        cost = tokens * 0.000005
        return {"text": text, "tokens": tokens, "cost": cost, "model_used": model}

    async def _call_gemini(self, model: str, system: str, prompt: str) -> dict:
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        m = genai.GenerativeModel(model, system_instruction=system)
        resp = await asyncio.to_thread(m.generate_content, prompt)
        text = resp.text
        tokens = len(text.split()) * 2
        return {"text": text, "tokens": tokens, "cost": 0, "model_used": model}

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
