"""Automation configuration — single source of truth for the scheduler.

Stored as a one-row table (AutomationConfig). Helpers read/write it and mirror
the content-related options into env vars so publishers/generators pick them up.
"""
import os
from sqlalchemy import select
from database.db import AsyncSessionLocal
from database.models import AutomationConfig

FIELDS = (
    "enabled", "autopilot", "auto_video", "video_provider",
    "schedule_trends", "schedule_generate", "schedule_publish", "schedule_report",
    "batch_size",
)


def to_dict(cfg: AutomationConfig) -> dict:
    return {f: getattr(cfg, f) for f in FIELDS}


def apply_env(cfg) -> None:
    """Mirror content options into env so generator/publisher code can read them."""
    data = cfg if isinstance(cfg, dict) else to_dict(cfg)
    os.environ["AUTO_VIDEO"] = "1" if data.get("auto_video") else "0"
    os.environ["VIDEO_PROVIDER"] = data.get("video_provider") or "auto"


async def get_config_row(db) -> AutomationConfig:
    cfg = await db.scalar(select(AutomationConfig).limit(1))
    if not cfg:
        cfg = AutomationConfig(id=1)
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


async def get_config() -> dict:
    async with AsyncSessionLocal() as db:
        cfg = await get_config_row(db)
        apply_env(cfg)
        return to_dict(cfg)


async def save_config(data: dict) -> dict:
    async with AsyncSessionLocal() as db:
        cfg = await get_config_row(db)
        for k, v in data.items():
            if k in FIELDS and v is not None:
                setattr(cfg, k, v)
        await db.commit()
        await db.refresh(cfg)
        apply_env(cfg)
        return to_dict(cfg)
