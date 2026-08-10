"""
Единый пульт управления: одна команда → один мозг (Claude-дирижёр) → общая лента.
Дашборд и Telegram работают через эти же функции, поэтому действия связаны.
"""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/control", tags=["control"])


class CommandBody(BaseModel):
    text: str


@router.post("/command")
async def control_command(body: CommandBody):
    """Выполнить команду с дашборда (свободный текст или слэш-команда).

    Уходит в тот же мозг, что и Telegram; результат зеркалится в Telegram и
    попадает в общую ленту.
    """
    from core.command_center import run_command
    return await run_command(body.text, source="dashboard")


@router.get("/feed")
async def control_feed(limit: int = 40):
    """Общая лента активности: команды и ответы из дашборда И из Telegram."""
    from core.command_center import get_feed
    return {"feed": await get_feed(limit)}
