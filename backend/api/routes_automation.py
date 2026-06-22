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
