"""
Роль 3 — монтажёр. Диспетчер бесплатного стека: FFmpeg собирает финальный ролик.

edit_reel(base_video, script_text, voice_audio, mood):
  1. определяет длительность (по голосу, иначе по видео);
  2. строит караоке-субтитры (.ass) из сценария (core.subtitles);
  3. подбирает роялти-фри трек по настроению (core.music_library);
  4. FFmpeg: запекает субтитры + микширует голос и музыку (музыка приглушена
     под голос) → финальный mp4 9:16.

Все шаги — детерминированный код, без LLM. Недоступен ffmpeg / нет входа —
возвращаем {ok: False, error} и не роняем конвейер.
"""
import os
import re
import asyncio
import subprocess
import tempfile
from datetime import date

import httpx

from core.video_assembly import _ffmpeg, _run
from core import subtitles as subs
from core import music_library


async def ensure_local_video(vid: dict) -> str | None:
    """Из результата генерации ({path|url}) делает локальный файл (скачивает url)."""
    if not vid:
        return None
    path = vid.get("path")
    if path and os.path.exists(path):
        return path
    url = vid.get("url") or ""
    if not url or not url.startswith("http"):
        return None
    try:
        async with httpx.AsyncClient(timeout=90, follow_redirects=True) as c:
            r = await c.get(url)
            r.raise_for_status()
        p = os.path.join(tempfile.mkdtemp(prefix="nx_dl_"), "in.mp4")
        with open(p, "wb") as f:
            f.write(r.content)
        return p
    except Exception:
        return None


def _duration(path: str) -> float:
    """Длительность медиа в секундах через ffmpeg (парсим stderr). 0 при ошибке."""
    ff = _ffmpeg()
    if not ff or not path or not os.path.exists(path):
        return 0.0
    try:
        p = subprocess.run([ff, "-i", path], capture_output=True, timeout=30)
        err = p.stderr.decode(errors="ignore")
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", err)
        if m:
            h, mn, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            return h * 3600 + mn * 60 + s
    except Exception:
        pass
    return 0.0


async def edit_reel(base_video: str, script_text: str = "", voice_audio: str = None,
                    mood: str = None, use_whisperx: bool = False,
                    out_dir: str = None) -> dict:
    """Собирает финальный ролик из готового видео Higgsfield + сценарий + музыка."""
    ff = _ffmpeg()
    if not ff:
        return {"ok": False, "error": "ffmpeg недоступен"}
    if not base_video or not os.path.exists(base_video):
        return {"ok": False, "error": "нет исходного видео"}

    # 1. Длительность: приоритет — голос, иначе видео.
    dur = _duration(voice_audio) if voice_audio else 0.0
    if dur <= 0:
        dur = _duration(base_video)
    if dur <= 0:
        dur = max(3.0, len(subs._words(script_text)) / 2.5)

    work = tempfile.mkdtemp(prefix="nx_edit_")
    base = os.path.dirname(os.path.dirname(__file__))
    out_dir = out_dir or os.path.join(base, "output", date.today().isoformat())
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"final_{date.today().isoformat()}_{os.getpid()}.mp4")

    # 2. Субтитры-караоке из сценария.
    ass_path = None
    if script_text.strip():
        ass_path = subs.build_ass(script_text, dur, audio_path=voice_audio,
                                  use_whisperx=use_whisperx,
                                  out_path=os.path.join(work, "subs.ass"))

    # 3. Музыка по настроению.
    track = music_library.pick_track(mood)

    # 4. Сборка команды FFmpeg.
    args = [ff, "-y", "-i", base_video]
    filter_v = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    if ass_path:
        esc = ass_path.replace("\\", "/").replace(":", "\\:")
        filter_v += f",subtitles='{esc}'"

    # Аудио: голос (если есть) + музыка приглушённая. Иначе — музыка, иначе — тишина видео.
    audio_inputs = []
    if voice_audio and os.path.exists(voice_audio):
        args += ["-i", voice_audio]
        audio_inputs.append(("voice", len(audio_inputs) + 1))
    if track:
        args += ["-i", track]
        audio_inputs.append(("music", len(audio_inputs) + 1))

    filter_complex = f"[0:v]{filter_v}[v]"
    map_args = ["-map", "[v]"]

    if len(audio_inputs) == 2:  # голос + музыка
        v_idx = audio_inputs[0][1]
        m_idx = audio_inputs[1][1]
        filter_complex += (
            f";[{v_idx}:a]volume=1.0[a1]"
            f";[{m_idx}:a]volume=0.18[a2]"
            f";[a1][a2]amix=inputs=2:duration=first:dropout_transition=2[a]"
        )
        map_args += ["-map", "[a]"]
    elif len(audio_inputs) == 1:  # только голос или только музыка
        idx = audio_inputs[0][1]
        vol = "1.0" if audio_inputs[0][0] == "voice" else "0.4"
        filter_complex += f";[{idx}:a]volume={vol}[a]"
        map_args += ["-map", "[a]"]
    else:
        map_args += ["-map", "0:a?"]  # звук из исходного видео, если есть

    args += ["-filter_complex", filter_complex] + map_args
    args += ["-t", f"{dur:.2f}", "-r", "30", "-pix_fmt", "yuv420p",
             "-c:v", "libx264", "-c:a", "aac", "-shortest", out]

    ok = await asyncio.to_thread(_run, args)
    if not ok or not os.path.exists(out):
        return {"ok": False, "error": "FFmpeg-сборка не удалась"}
    return {
        "ok": True, "path": out, "provider": "ffmpeg_editor",
        "duration": round(dur, 1),
        "subtitles": bool(ass_path), "music": bool(track),
        "mode": "whisperx" if use_whisperx else "estimated",
    }
