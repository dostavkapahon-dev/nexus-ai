"""
Аналитика опубликованного: реальные метрики, топ постов, обучение на результатах.
Защищено auth на уровне main.py.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/performance", tags=["analytics"])


@router.get("")
async def performance_overview(days: int = 30, niche_id: str = ""):
    """Сводка результатов: посты, охваты, средняя вовлечённость, разбивка по площадкам."""
    from core.post_analytics import performance
    return await performance(days, niche_id)


@router.get("/top")
async def performance_top(days: int = 30, limit: int = 10, worst: bool = False):
    """Лучшие или худшие публикации по вовлечённости."""
    from core.post_analytics import top_posts
    return {"posts": await top_posts(days, limit, worst)}


@router.post("/collect")
async def performance_collect():
    """Собрать метрики вручную (обычно это делает джоб в 23:00)."""
    from core.post_analytics import collect_metrics
    return await collect_metrics()


@router.post("/learn")
async def performance_learn(days: int = 30):
    """Превратить реальные результаты в уроки для памяти агента."""
    from core.post_analytics import learn_from_results
    return await learn_from_results(days)
