"""
Агенты: список ролей, их готовность и запуск задачи.
Защищено auth на уровне main.py.
"""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("")
async def list_agents(hours: int = 168):
    """Роли агентов + фактическая работа за период.

    Реестр отвечает на вопрос «кто есть и что умеет», журнал вызовов —
    «кто реально работал». Вместе это единственный честный ответ на вопрос
    пользователя «а мои агенты вообще живы?».
    """
    from agents.registry import describe
    from core.health import agents as agent_stats

    stats = {a["agent"]: a for a in await agent_stats(hours)}
    items = []
    for spec in describe():
        # Имена в журнале — это классы (viral_hunter, copywriter…), роль может
        # опираться на несколько из них: берём лучшее совпадение по названию.
        used = [s for name, s in stats.items() if name and name in " ".join(spec["backed_by"])]
        last = max((s.get("last_run") or "" for s in used), default="")
        items.append({**spec, "calls": sum(s.get("calls", 0) for s in used),
                      "last_run": last or None})
    return {"agents": items, "ready": sum(1 for i in items if i["ready"])}


class RunBody(BaseModel):
    task: str
    context: str = ""


@router.post("/{key}/run")
async def run_agent(key: str, body: RunBody):
    """Поставить задачу роли.

    Запуск идёт задачей — чтобы он был виден в общем журнале, а не исчезал
    бесследно, как раньше исчезали прямые вызовы агентов.
    """
    from agents.registry import get, run as run_role
    from core.task_manager import create, run as run_task

    spec = get(key)
    if not spec:
        return {"ok": False, "error": f"нет такого агента: {key}"}

    task_id = await create("agent", f"{spec.title}: {body.task}"[:300], source="dashboard")
    outcome = await run_task(task_id, lambda: run_role(key, body.task, body.context))
    if not outcome.get("ok"):
        return {"ok": False, "task_id": task_id, "error": str(outcome.get("error"))[:300]}
    return {"ok": True, "task_id": task_id, "result": outcome["result"]}
