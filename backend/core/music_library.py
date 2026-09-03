"""
Роль 3 — музыкальная библиотека (роялти-фри), выбор трека КОДОМ, без LLM.

Треки кладутся в backend/data/music/*.mp3 (или .m4a/.wav). Теги — в
data/music/tags.json: {"track.mp3": {"mood": "energetic", "bpm": 120}}.
Если тегов нет — трек считается universal. Источники бесплатных треков:
YouTube Audio Library, Pixabay Music, Free Music Archive (свободные лицензии).

Выбор трека — простой поиск по тегу настроения, без вызова модели.
"""
import os
import json
import random

MUSIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "music")
AUDIO_EXT = (".mp3", ".m4a", ".wav", ".aac", ".ogg")

# Сопоставление «тон/цель ниши» → настроение трека.
MOOD_ALIASES = {
    "экспертный": "calm", "expert": "calm", "спокойный": "calm",
    "дерзкий": "energetic", "bold": "energetic", "энергичный": "energetic",
    "развлекательный": "fun", "fun": "fun", "весёлый": "fun",
    "драматичный": "dramatic", "dramatic": "dramatic",
}


def _tags() -> dict:
    path = os.path.join(MUSIC_DIR, "tags.json")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def list_tracks() -> list[dict]:
    """Все треки библиотеки с тегами."""
    if not os.path.isdir(MUSIC_DIR):
        return []
    tags = _tags()
    out = []
    for fn in os.listdir(MUSIC_DIR):
        if fn.lower().endswith(AUDIO_EXT):
            meta = tags.get(fn, {})
            out.append({
                "file": fn,
                "path": os.path.join(MUSIC_DIR, fn),
                "mood": (meta.get("mood") or "universal"),
                "bpm": meta.get("bpm"),
            })
    return out


def normalize_mood(tone: str | None) -> str:
    if not tone:
        return "universal"
    t = tone.lower().strip()
    return MOOD_ALIASES.get(t, t)


async def add_track_from_url(url: str, mood: str = "universal", name: str = None) -> dict:
    """Скачивает трек по прямой ссылке в библиотеку и проставляет тег настроения."""
    import httpx
    os.makedirs(MUSIC_DIR, exist_ok=True)
    fname = name or os.path.basename(url.split("?")[0]) or "track.mp3"
    if not fname.lower().endswith(AUDIO_EXT):
        fname += ".mp3"
    dst = os.path.join(MUSIC_DIR, fname)
    try:
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as c:
            r = await c.get(url)
            r.raise_for_status()
        with open(dst, "wb") as f:
            f.write(r.content)
    except Exception as e:
        return {"ok": False, "error": str(e)[:150]}

    tags = _tags()
    tags[fname] = {"mood": normalize_mood(mood)}
    with open(os.path.join(MUSIC_DIR, "tags.json"), "w", encoding="utf-8") as f:
        json.dump(tags, f, ensure_ascii=False, indent=2)
    return {"ok": True, "file": fname, "mood": normalize_mood(mood),
            "total": len(list_tracks())}


def pick_track(mood: str | None = None) -> str | None:
    """Возвращает путь к треку по настроению. Нет совпадения — любой. Пусто — None."""
    tracks = list_tracks()
    if not tracks:
        return None
    mood = normalize_mood(mood)
    matches = [t for t in tracks if t["mood"] == mood] or \
              [t for t in tracks if t["mood"] == "universal"] or tracks
    return random.choice(matches)["path"]
