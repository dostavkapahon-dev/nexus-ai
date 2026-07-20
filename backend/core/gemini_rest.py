"""Лёгкий REST-клиент Google Gemini на httpx.

Заменяет тяжёлый пакет `google-generativeai`, который в некоторых средах
тянет сломанные rust-биндинги `cryptography` и роняет весь импорт приложения.
Здесь — только чистые HTTP-вызовы к Generative Language API: текст и vision.
"""
import os
import base64
import httpx

BASE = "https://generativelanguage.googleapis.com/v1beta"


def _key() -> str:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY не задан")
    return key


async def generate(model: str, system: str, prompt: str,
                   image_bytes: bytes | None = None,
                   image_mime: str = "image/jpeg",
                   json_mode: bool = False,
                   timeout: float = 120.0) -> str:
    """Один вызов generateContent. Возвращает текст ответа.

    Если передан `image_bytes` — добавляется как inline-картинка (vision).
    """
    parts: list[dict] = [{"text": prompt}]
    if image_bytes is not None:
        parts.append({"inline_data": {
            "mime_type": image_mime,
            "data": base64.b64encode(image_bytes).decode(),
        }})
    body: dict = {"contents": [{"parts": parts}]}
    if system:
        body["system_instruction"] = {"parts": [{"text": system}]}
    if json_mode:
        body["generationConfig"] = {"response_mime_type": "application/json"}

    url = f"{BASE}/models/{model}:generateContent?key={_key()}"
    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.post(url, json=body)
        r.raise_for_status()
        data = r.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        return ""
