import os
import httpx

async def publish_telegram(chat_id: str, text: str, image_url: str = None, video_url: str = None) -> dict:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not set")

    async with httpx.AsyncClient(timeout=60) as client:
        if video_url:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendVideo",
                json={"chat_id": chat_id, "video": video_url, "caption": text[:1024], "parse_mode": "HTML"}
            )
        elif image_url:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                json={"chat_id": chat_id, "photo": image_url, "caption": text[:1024], "parse_mode": "HTML"}
            )
        else:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
            )
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram error: {data}")
        return {"message_id": data["result"]["message_id"]}
