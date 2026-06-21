from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from core.automation import get_config, save_config
from core.scheduler import reschedule, trigger_now, JOBS

router = APIRouter(prefix="/api/automation", tags=["automation"])


class AutomationBody(BaseModel):
    enabled: Optional[bool] = None
    autopilot: Optional[bool] = None
    auto_video: Optional[bool] = None
    video_provider: Optional[str] = None
    schedule_trends: Optional[int] = None
    schedule_generate: Optional[int] = None
    schedule_publish: Optional[int] = None
    schedule_report: Optional[int] = None
    batch_size: Optional[int] = None


@router.get("")
async def read_config():
    return await get_config()


@router.post("")
async def update_config(body: AutomationBody):
    cfg = await save_config(body.model_dump(exclude_none=True))
    await reschedule()
    return cfg


@router.post("/run/{job_id}")
async def run_job(job_id: str):
    valid = set(JOBS.keys()) | {"autopilot"}
    if job_id not in valid:
        raise HTTPException(400, f"Unknown job '{job_id}'. Valid: {sorted(valid)}")
    await trigger_now(job_id)
    return {"ok": True, "ran": job_id}
