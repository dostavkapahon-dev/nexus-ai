"""
Монтаж: склейка нескольких клипов в один готовый ролик 9:16.

Берёт список ссылок на клипы (напр. сцены из Higgsfield), приводит каждый к
1080x1920 30fps с тихой аудиодорожкой, склеивает, накладывает роялти-фри музыку
и отдаёт один mp4. Работает на сервере (Render) — там CDN клипов доступен.

Опционально выжигает титры по сценам (.ass) и шлёт готовый ролик в Telegram.
"""
import os
import asyncio
import tempfile
from datetime import date

from core.video_assembly import _ffmpeg, _run
from core.video_editor import ensure_local_video
from core import music_library


async def _normalize(ff: str, src: str, dst: str) -> bool:
    """Приводит клип к 1080x1920/30fps + тихая стерео-дорожка (для ровной склейки)."""
    return await asyncio.to_thread(_run, [
        ff, "-y", "-i", src,
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,format=yuv420p",
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", "-shortest", dst,
    ])


async def assemble(clip_urls: list, music_mood: str = None, out_dir: str = None) -> dict:
    """Склеивает клипы по порядку в один ролик + фоновая музыка. Возвращает {ok, path}."""
    ff = _ffmpeg()
    if not ff:
        return {"ok": False, "error": "ffmpeg недоступен"}
    if not clip_urls:
        return {"ok": False, "error": "нет клипов"}

    work = tempfile.mkdtemp(prefix="nx_montage_")
    base = os.path.dirname(os.path.dirname(__file__))
    out_dir = out_dir or os.path.join(base, "output", date.today().isoformat())
    os.makedirs(out_dir, exist_ok=True)

    # 1. Скачать и нормализовать каждый клип.
    norm_clips = []
    for i, url in enumerate(clip_urls):
        local = await ensure_local_video({"url": url})
        if not local:
            continue
        dst = os.path.join(work, f"n{i}.mp4")
        if await _normalize(ff, local, dst) and os.path.exists(dst):
            norm_clips.append(dst)
    if not norm_clips:
        return {"ok": False, "error": "не удалось скачать/подготовить клипы (CDN?)"}

    # 2. Склейка (concat demuxer — одинаковые параметры уже гарантированы).
    listfile = os.path.join(work, "list.txt")
    with open(listfile, "w") as f:
        for c in norm_clips:
            f.write(f"file '{c}'\n")
    joined = os.path.join(work, "joined.mp4")
    if not await asyncio.to_thread(_run, [
        ff, "-y", "-f", "concat", "-safe", "0", "-i", listfile, "-c", "copy", joined,
    ]) or not os.path.exists(joined):
        return {"ok": False, "error": "склейка не удалась"}

    out = os.path.join(out_dir, f"reel_{date.today().isoformat()}_{os.getpid()}.mp4")

    # 3. Музыка поверх (если есть трек в библиотеке).
    track = music_library.pick_track(music_mood)
    if track:
        ok = await asyncio.to_thread(_run, [
            ff, "-y", "-i", joined, "-i", track,
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-shortest", out,
        ])
        if not ok or not os.path.exists(out):
            os.replace(joined, out)  # музыка не легла — отдаём без неё
    else:
        os.replace(joined, out)

    return {"ok": True, "path": out, "clips": len(norm_clips), "music": bool(track)}


async def send_video_to_telegram(path: str, chat_id: str, caption: str = "") -> bool:
    """Загружает готовый ролик файлом в Telegram (multipart)."""
    import httpx
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token or not chat_id or not os.path.exists(path):
        return False
    try:
        async with httpx.AsyncClient(timeout=180) as c:
            with open(path, "rb") as f:
                r = await c.post(
                    f"https://api.telegram.org/bot{token}/sendVideo",
                    data={"chat_id": chat_id, "caption": caption[:1024]},
                    files={"video": ("reel.mp4", f, "video/mp4")},
                )
            return r.json().get("ok", False)
    except Exception:
        return False


async def assemble_and_send(clip_urls: list, chat_id: str, music_mood: str = None,
                            caption: str = "🎬 Готовый ролик") -> dict:
    res = await assemble(clip_urls, music_mood=music_mood)
    if not res.get("ok"):
        return res
    sent = await send_video_to_telegram(res["path"], chat_id, caption)
    res["sent"] = sent
    return res
