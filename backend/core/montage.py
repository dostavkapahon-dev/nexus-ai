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


# Плавные переходы между сценами (ffmpeg xfade). Чередуются для живости.
TRANSITIONS = ["fade", "wipeleft", "slideup", "circleopen", "dissolve"]
XFADE_DUR = 0.4  # длительность перехода, сек


async def _concat_with_transitions(ff: str, clips: list, out: str) -> bool:
    """Склейка с плавными переходами xfade. True — получилось."""
    from core.video_editor import _duration
    durs = [_duration(c) for c in clips]
    if any(d <= XFADE_DUR for d in durs):
        return False  # слишком короткие клипы — переход не влезет

    # Строим цепочку: [0][1]xfade → [v01]; [v01][2]xfade → [v012] ...
    parts, offset, prev = [], 0.0, "[0:v]"
    for i in range(1, len(clips)):
        offset += durs[i - 1] - XFADE_DUR
        label = f"[v{i}]"
        tr = TRANSITIONS[(i - 1) % len(TRANSITIONS)]
        parts.append(f"{prev}[{i}:v]xfade=transition={tr}:duration={XFADE_DUR}"
                     f":offset={offset:.2f}{label}")
        prev = label

    args = [ff, "-y"]
    for c in clips:
        args += ["-i", c]
    args += ["-filter_complex", ";".join(parts), "-map", prev,
             "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", out]
    ok = await asyncio.to_thread(_run, args)
    return bool(ok and os.path.exists(out))


async def assemble(clip_urls: list, music_mood: str = None, out_dir: str = None,
                   script: str = None, voice_url: str = None,
                   transitions: bool = True) -> dict:
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

    # 1. Скачать и нормализовать каждый клип (с диагностикой каждого шага).
    norm_clips = []
    diag = []
    for i, url in enumerate(clip_urls):
        local = await ensure_local_video({"url": url})
        if not local:
            diag.append(f"клип {i+1}: не скачался (недоступен URL?)")
            continue
        dst = os.path.join(work, f"n{i}.mp4")
        if await _normalize(ff, local, dst) and os.path.exists(dst):
            norm_clips.append(dst)
        else:
            diag.append(f"клип {i+1}: ffmpeg-нормализация не удалась")
    if not norm_clips:
        return {"ok": False, "error": "ни один клип не подготовлен. " + "; ".join(diag)}

    # 2. Склейка. С переходами (xfade) — выглядит профессионально; при сбое —
    #    обычный concat встык как надёжный запасной путь.
    joined = os.path.join(work, "joined.mp4")
    used_transitions = False
    if transitions and len(norm_clips) > 1:
        used_transitions = await _concat_with_transitions(ff, norm_clips, joined)
    if not used_transitions:
        listfile = os.path.join(work, "list.txt")
        with open(listfile, "w") as f:
            for c in norm_clips:
                f.write(f"file '{c}'\n")
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
            "transitions": used_transitions,
            "music": bool(track), "voice": bool(voice_local), "captions": bool(ass_path)}


async def send_video_to_telegram(path: str, chat_id: str, caption: str = "") -> dict:
    """Загружает готовый ролик файлом в Telegram (multipart). Возвращает {ok, error}."""
    import httpx
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return {"ok": False, "error": "нет TELEGRAM_BOT_TOKEN"}
    if not os.path.exists(path):
        return {"ok": False, "error": "файл ролика не найден"}
    size_mb = os.path.getsize(path) / 1024 / 1024
    if size_mb > 49:
        return {"ok": False, "error": f"ролик {size_mb:.0f} МБ — Telegram-бот лимит 50 МБ"}
    try:
        async with httpx.AsyncClient(timeout=300) as c:
            with open(path, "rb") as f:
                r = await c.post(
                    f"https://api.telegram.org/bot{token}/sendVideo",
                    data={"chat_id": chat_id, "caption": caption[:1024]},
                    files={"video": ("reel.mp4", f, "video/mp4")},
                )
            d = r.json()
            if d.get("ok"):
                return {"ok": True}
            return {"ok": False, "error": d.get("description", "Telegram отклонил")[:150]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:150]}


async def assemble_and_send(clip_urls: list, chat_id: str, music_mood: str = None,
                            caption: str = "🎬 Готовый ролик",
                            script: str = None, voice_url: str = None) -> dict:
    res = await assemble(clip_urls, music_mood=music_mood, script=script, voice_url=voice_url)
    if not res.get("ok"):
        return res
    snd = await send_video_to_telegram(res["path"], chat_id, caption)
    res["sent"] = snd.get("ok")
    if not snd.get("ok"):
        res["send_error"] = snd.get("error")
    return res
