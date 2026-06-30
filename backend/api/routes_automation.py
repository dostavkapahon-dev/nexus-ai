"""
Роуты автоматизации маркетинга: запуск Claude-дирижёра, генерация видео,
мульти-публикация плана. Защищены auth на уровне main.py.
"""
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/automation", tags=["automation"])


class DirectorRequest(BaseModel):
    goal: str
    context: Optional[str] = ""
    max_steps: Optional[int] = 12


@router.post("/director")
async def run_director_endpoint(body: DirectorRequest):
    """Запустить главного AI-дирижёра по бизнес-цели (запуск «через Claude отсюда»)."""
    from core.marketing_director import run_director
    if not body.goal.strip():
        return {"ok": False, "error": "Поле 'goal' обязательно."}
    try:
        result = await run_director(body.goal, body.context or "", int(body.max_steps or 12))
        return {"ok": True, **result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


class VideoRequest(BaseModel):
    prompt: str
    script: Optional[str] = ""
    provider: Optional[str] = "auto"
    image_url: Optional[str] = None
    ratio: Optional[str] = "9:16"
    model: Optional[str] = None  # конкретная модель HiggsField (см. /automation/video/models)


@router.post("/video")
async def generate_video_endpoint(body: VideoRequest):
    """Сгенерировать короткое видео (HeyGen / HiggsField / Runway)."""
    from core.media_generator import generate_clip
    try:
        result = await generate_clip(
            prompt=body.prompt, script=body.script or "", image_url=body.image_url,
            provider=body.provider or "auto", ratio=body.ratio or "9:16", model=body.model,
        )
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


class ImageRequest(BaseModel):
    prompt: str
    provider: Optional[str] = "auto"  # auto/imagen/dalle3/stability/pollinations/higgsfield
    platform: Optional[str] = "telegram"  # влияет на размер кадра


@router.post("/image")
async def generate_image_endpoint(body: ImageRequest):
    """Создать фото/изображение по текстовому описанию.

    Провайдеры: Imagen → DALL-E 3 → Stability → Pollinations (бесплатный fallback),
    либо higgsfield (модель Soul) — через API-ключ или ваш аккаунт (браузер-агент).
    """
    if not body.prompt.strip():
        return {"ok": False, "error": "Поле 'prompt' обязательно."}
    vertical = (body.platform or "telegram") in ("tiktok", "instagram", "youtube")
    try:
        if (body.provider or "").lower() == "higgsfield":
            from core.skills import higgsfield_photo
            return await higgsfield_photo(body.prompt.strip(), ratio="9:16" if vertical else "1:1")

        from core.media_generator import generate_image
        url = await generate_image(
            body.prompt.strip(),
            provider=body.provider or "auto",
            platform=body.platform or "telegram",
        )
        return {"ok": True, "url": url}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/video/models")
async def list_video_models():
    """Список доступных моделей видео-генерации (в т.ч. много моделей HiggsField)."""
    from core.higgsfield import MODELS as HF_MODELS
    return {
        "heygen": ["avatar (озвучка текста)"],
        "higgsfield": HF_MODELS,
        "runway": ["gen3a_turbo"],
    }


@router.post("/publish/{plan_id}")
async def publish_multi(plan_id: str, bg: BackgroundTasks):
    """Опубликовать сгенерированный план во все площадки ниши (API + браузер-fallback)."""
    from core.orchestrator import nexus_core
    bg.add_task(nexus_core.publish_plan, plan_id)
    return {"ok": True, "message": "Публикация запущена в фоне."}


@router.get("/brand")
async def get_brand():
    """Бренд Pakhon Studio: голос, платформо-специфика, типы хуков."""
    from core.brand import get_brand_voice, PLATFORM_SPECS, HOOK_TYPES, BRAND, WINNING_TOPICS
    return {"brand": BRAND, "voice": get_brand_voice(), "platform_specs": PLATFORM_SPECS,
            "hook_types": HOOK_TYPES, "winning_topics": WINNING_TOPICS}


class BrandVoiceBody(BaseModel):
    voice: str


@router.post("/brand/voice")
async def update_brand_voice(body: BrandVoiceBody):
    """Обновить голос бренда (эквивалент команды /prompt)."""
    from core.brand import set_brand_voice
    if not body.voice.strip():
        return {"ok": False, "error": "Пустой текст"}
    set_brand_voice(body.voice)
    return {"ok": True}


class FactoryBody(BaseModel):
    topic: Optional[str] = None
    platforms: Optional[list] = None
    dry_run: Optional[bool] = True
    want_video: Optional[bool] = True


@router.post("/factory")
async def run_factory_endpoint(body: FactoryBody):
    """Единый конвейер: анализ → генерация (Gemini/HeyGen/HiggsField/Imagen) →
    публикация в Instagram/YouTube/TikTok/Telegram → отчёт.

    dry_run=True (по умолчанию) — всё генерируем, но не публикуем.
    """
    from core.content_factory import run_factory
    try:
        result = await run_factory(
            topic=body.topic, platforms=body.platforms,
            dry_run=body.dry_run if body.dry_run is not None else True,
            want_video=body.want_video if body.want_video is not None else True,
        )
        return {"ok": True, **result}
    except Exception as e:
        return {"ok": False, "error": str(e)}
