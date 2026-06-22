"""
CREATIVE DIRECTOR — мозг продакшена Pakhon Studio.
==================================================
Пишет тех-задание и промты под вирусный контент, делает раскадровку по кадрам,
выбирает САМЫЙ ДЕШЁВЫЙ рабочий путь сборки видео из доступных провайдеров,
и проверяет результат на «вау» (само-ревью).

Все AI-вызовы идут через ai_router → работают на бесплатном Gemini.
"""
import os
import json

from core.brand import system_prompt

# Относительная стоимость (чем меньше — тем дешевле). Для выбора стратегии.
COST_HINT = {
    "pollinations_image": 0.0,   # безлимит, бесплатно
    "imagen_image": 0.02,
    "higgsfield_video": 0.20,    # много моделей, image2video
    "heygen_avatar": 0.30,       # говорящий аватар
    "runway_video": 0.50,
}

_BRIEF_PROMPT = """\
Ты — креативный директор. На основе анализа сделай ПРОДАКШЕН-ТЗ под вирусный
Reel/Short (вертикаль 9:16). Думай кадрами и удержанием (смена кадра 2-3 сек,
паттерн-прерывание каждые 5-7 сек, субтитры всегда, хук-оверлей первые 3 сек).

АНАЛИЗ:
{analysis}

Верни СТРОГО JSON:
{{
  "title": "рабочее название ролика",
  "duration_sec": 20,
  "storyboard": [
    {{"t": "0-3", "visual": "что в кадре", "overlay": "крупный текст хука", "image_prompt": "англ. промпт кадра (без текста)"}},
    {{"t": "3-8", "visual": "...", "overlay": "...", "image_prompt": "..."}},
    {{"t": "8-15", "visual": "...", "overlay": "...", "image_prompt": "..."}},
    {{"t": "15-20", "visual": "CTA экран", "overlay": "призыв", "image_prompt": "..."}}
  ],
  "cover_prompt": "англ. промпт обложки в тёмном кинематографичном стиле, золото/неон",
  "video_motion_prompt": "англ. промпт движения для image2video (камера, динамика)",
  "avatar_script": "скрипт озвучки аватара 15-25 сек, разговорно, [пауза 0.5s]",
  "voice_mood": "energetic|calm|bold",
  "music_mood": "жанр/настроение трека",
  "subtitles_style": "белый Bold с чёрной обводкой, нижняя треть"
}}
"""

_WOW_PROMPT = """\
Ты — строгий редактор вирусного контента. Оцени ролик по тех-заданию ниже.
Критерии: сила хука (0-3 сек), удержание, конкретика, чёткость одного CTA,
соответствие нише AI/digital. Будь критичен.

ТЗ:
{brief}

Верни СТРОГО JSON:
{{"score": 0-10, "verdict": "коротко почему", "fix": "одно конкретное улучшение",
  "new_hook": "усиленный хук-оверлей если score<8, иначе пусто"}}
"""


async def build_brief(analysis: dict) -> dict:
    """Полное продакшен-ТЗ с раскадровкой и промтами."""
    from core.ai_router import ai_router
    try:
        res = await ai_router.call("claude-sonnet-4-6", system_prompt(),
                                   _BRIEF_PROMPT.format(analysis=json.dumps(analysis, ensure_ascii=False)))
        raw = res.get("text", "")
        s, e = raw.find("{"), raw.rfind("}") + 1
        return json.loads(raw[s:e])
    except Exception as e:
        return {"title": analysis.get("theme", "Reel"), "duration_sec": 20, "storyboard": [],
                "cover_prompt": analysis.get("image_prompt", "dark cinematic AI poster"),
                "video_motion_prompt": "slow cinematic zoom, dynamic camera",
                "avatar_script": analysis.get("avatar_script", ""), "voice_mood": "energetic",
                "_error": f"Нет AI для ТЗ: {str(e)[:100]}"}


def choose_strategy(content_type: str = "auto") -> dict:
    """Выбор пути видео. ОСНОВНОЙ продакшен — HiggsField или HeyGen.

    Приоритет:
      1) HeyGen аватар — если нужен говорящий ведущий (talking_head/explainer)
      2) HiggsField — раскадровка из фото (безлимит) → анимация (image2video), дёшево и динамично
      3) HeyGen / Runway — если только они доступны
      4) (аварийно) ffmpeg-слайдшоу — ТОЛЬКО если нет ключей HiggsField/HeyGen/Runway
    """
    has_hf = bool(os.getenv("HIGGSFIELD_API_KEY"))
    has_hg = bool(os.getenv("HEYGEN_API_KEY"))
    has_rw = bool(os.getenv("RUNWAY_API_KEY"))

    if content_type in ("talking_head", "explainer") and has_hg:
        return {"strategy": "heygen_avatar", "reason": "Говорящий ведущий — аватар HeyGen",
                "est_cost": COST_HINT["heygen_avatar"], "needs": "HEYGEN_API_KEY", "fallback": False}

    if has_hf:
        return {"strategy": "storyboard_to_higgsfield",
                "reason": "HiggsField: раскадровка (безлимит фото) → анимация image2video",
                "est_cost": COST_HINT["imagen_image"] * 4 + COST_HINT["higgsfield_video"],
                "needs": "HIGGSFIELD_API_KEY", "fallback": False}

    if has_hg:
        return {"strategy": "heygen_avatar", "reason": "HeyGen аватар",
                "est_cost": COST_HINT["heygen_avatar"], "needs": "HEYGEN_API_KEY", "fallback": False}
    if has_rw:
        return {"strategy": "runway", "reason": "Runway image2video",
                "est_cost": COST_HINT["runway_video"], "needs": "RUNWAY_API_KEY", "fallback": False}

    # Аварийный режим — нормальное видео требует HiggsField или HeyGen.
    return {"strategy": "free_slideshow", "fallback": True,
            "reason": "Нет ключей HiggsField/HeyGen — аварийный ffmpeg-слайдшоу. "
                      "Для нормального видео добавь HIGGSFIELD_API_KEY или HEYGEN_API_KEY.",
            "est_cost": 0.0, "needs": "HIGGSFIELD_API_KEY или HEYGEN_API_KEY"}


async def wow_review(brief: dict) -> dict:
    """Само-ревью на «вау». Может вернуть усиленный хук."""
    from core.ai_router import ai_router
    try:
        res = await ai_router.call("claude-sonnet-4-6", system_prompt(),
                                   _WOW_PROMPT.format(brief=json.dumps(brief, ensure_ascii=False)[:3000]))
        raw = res.get("text", "")
        s, e = raw.find("{"), raw.rfind("}") + 1
        return json.loads(raw[s:e])
    except Exception as e:
        return {"score": 7, "verdict": "авто-ревью недоступно", "fix": "", "new_hook": "",
                "_error": str(e)[:100]}
