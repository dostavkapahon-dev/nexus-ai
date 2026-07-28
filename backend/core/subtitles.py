"""
Роль 3 — субтитры в стиле «караоке» (по одному слову), формат .ass для FFmpeg.

Два режима:
  • estimated (по умолчанию, бесплатно, CPU): тайминг слов раскидываем равномерно
    по длительности аудио/видео. Так как сценарий пишем МЫ — транскрибация не нужна.
  • whisperx (опциональный апгрейд): если установлен пакет whisperx и передан
    внешний аудиофайл — берём точные word-level таймкоды.

Оба дают .ass с крупным словом по центру снизу — тренд Reels/TikTok.
"""
import os
import tempfile

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
Style: Kara, DejaVu Sans, 96, &H00FFFFFF, &H00000000, &H90000000, 1, 5, 2, 2, 60, 60, 260

[Events]
Format: Layer, Start, End, Style, Text
"""


def _ts(sec: float) -> str:
    """Секунды → формат ASS h:mm:ss.cs."""
    if sec < 0:
        sec = 0
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = int(round((sec - int(sec)) * 100))
    if cs == 100:
        cs = 0
        s += 1
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _words(text: str) -> list[str]:
    return [w for w in (text or "").split() if w.strip()]


def estimated_words(text: str, duration_sec: float) -> list[tuple]:
    """Раскидывает слова равномерно по длительности → [(word, start, end)]."""
    words = _words(text)
    if not words or duration_sec <= 0:
        return []
    step = duration_sec / len(words)
    out = []
    t = 0.0
    for w in words:
        out.append((w, t, t + step))
        t += step
    return out


def whisperx_words(audio_path: str, language: str = None) -> list[tuple]:
    """Точные word-level таймкоды через WhisperX. Требует пакет whisperx.

    Возвращает [] если whisperx не установлен или произошла ошибка — тогда
    вызывающий код использует estimated-режим.
    """
    try:
        import whisperx  # type: ignore
    except Exception:
        return []
    try:
        device = "cpu"
        model = whisperx.load_model("small", device, compute_type="int8")
        audio = whisperx.load_audio(audio_path)
        result = model.transcribe(audio, batch_size=8)
        lang = language or result.get("language", "en")
        model_a, meta = whisperx.load_align_model(language_code=lang, device=device)
        aligned = whisperx.align(result["segments"], model_a, meta, audio, device)
        out = []
        for seg in aligned.get("segments", []):
            for w in seg.get("words", []):
                if "start" in w and "end" in w:
                    out.append((w.get("word", "").strip(), float(w["start"]), float(w["end"])))
        return out
    except Exception:
        return []


def build_ass(text: str, duration_sec: float, audio_path: str = None,
              use_whisperx: bool = False, out_path: str = None) -> str | None:
    """Строит .ass файл караоке-субтитров. Возвращает путь к файлу или None."""
    timings = []
    if use_whisperx and audio_path and os.path.exists(audio_path):
        timings = whisperx_words(audio_path)
    if not timings:
        timings = estimated_words(text, duration_sec)
    if not timings:
        return None

    lines = [ASS_HEADER]
    for word, start, end in timings:
        safe = word.replace("{", "(").replace("}", ")").replace("\n", " ")
        lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Kara,{safe}")

    out_path = out_path or os.path.join(tempfile.mkdtemp(prefix="nx_subs_"), "subs.ass")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return out_path
