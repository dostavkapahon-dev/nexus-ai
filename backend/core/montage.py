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


async def assemble(clip_urls: list, music_mood: str = None, out_dir: str = None,
                   script: str = None, voice_url: str = None) -> dict:
    """Профессиональная склейка: клипы → один ролик 9:16 с караоке-титрами,
    озвучкой и музыкой (приглушённой под голос).

    script    — текст для караоке-титров (тайминг по длине ролика/аудио);
    voice_url — ссылка на озвучку (голос); музыка тогда идёт фоном тише.
    """
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

    # 3. Длительность склейки (для таймингов субтитров).
    from core.video_editor import _duration
    dur = _duration(joined) or 0.0

    # 4. Караоке-титры из сценария (тайминг по длине ролика/озвучки).
    voice_local = await ensure_local_video({"url": voice_url}) if voice_url else None
    ass_path = None
    if script and script.strip():
        from core import subtitles as subs
        sub_dur = (_duration(voice_local) if voice_local else 0) or dur or 15.0
        ass_path = subs.build_ass(script, sub_dur, audio_path=voice_local,
                                  out_path=os.path.join(work, "subs.ass"))

    track = music_library.pick_track(music_mood)

    # 5. Собираем финал: видео (+титры) + аудио (голос + музыка приглушённая).
    args = [ff, "-y", "-i", joined]
    inputs = 1
    voice_idx = music_idx = None
    if voice_local:
        args += ["-i", voice_local]; voice_idx = inputs; inputs += 1
    if track:
        args += ["-i", track]; music_idx = inputs; inputs += 1

    fc = []
    vlabel = "0:v:0"
    if ass_path:
        esc = ass_path.replace("\\", "/").replace(":", "\\:")
        fc.append(f"[0:v]subtitles='{esc}'[v]"); vlabel = "[v]"

    amap = None
    if voice_idx is not None and music_idx is not None:
        # Голос громкий + музыка тихо фоном → микс.
        fc.append(f"[{voice_idx}:a]volume=1.0[vo];[{music_idx}:a]volume=0.15[mu];"
                  f"[vo][mu]amix=inputs=2:duration=first:dropout_transition=2[a]")
        amap = "[a]"
    elif voice_idx is not None:
        fc.append(f"[{voice_idx}:a]volume=1.0[a]"); amap = "[a]"
    elif music_idx is not None:
        fc.append(f"[{music_idx}:a]volume=0.5[a]"); amap = "[a]"

    if fc:
        args += ["-filter_complex", ";".join(fc)]
    args += ["-map", vlabel]
    if amap:
        args += ["-map", amap]
    else:
        args += ["-map", "0:a:0?"]
    args += ["-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", "-shortest", out]

    ok = await asyncio.to_thread(_run, args)
    if not ok or not os.path.exists(out):
        os.replace(joined, out)  # что-то не легло — отдаём хотя бы склейку

    return {"ok": True, "path": out, "clips": len(norm_clips),
            "music": bool(track), "voice": bool(voice_local), "captions": bool(ass_path)}


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
                            caption: str = "🎬 Готовый ролик",
                            script: str = None, voice_url: str = None) -> dict:
    res = await assemble(clip_urls, music_mood=music_mood, script=script, voice_url=voice_url)
    if not res.get("ok"):
        return res
    sent = await send_video_to_telegram(res["path"], chat_id, caption)
    res["sent"] = sent
    return res
