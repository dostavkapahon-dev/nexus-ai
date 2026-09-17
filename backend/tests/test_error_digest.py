"""«Ошибок за 24ч: 118» — это не диагноз, а число.

Сотня ошибок почти всегда оказывается одной поломкой, повторившейся сто раз.
Пока не видно, какая причина повторяется, чинить нечего.
"""
import pytest
from datetime import datetime

from core import notify


def _rows(groups):
    return {(g["who"], g["code"]): g["count"] for g in groups}


@pytest.mark.asyncio
async def test_digest_groups_repeats_by_cause(monkeypatch):
    from database.db import init_db, AsyncSessionLocal
    from database.models import AgentLog
    await init_db()
    async with AsyncSessionLocal() as db:
        for _ in range(5):
            db.add(AgentLog(agent_name="media", status="error",
                            error="Higgsfield: 400 Unavailable model"))
        db.add(AgentLog(agent_name="media", status="error",
                        error="timeout while waiting for job"))
        await db.commit()

    data = await notify.error_digest(24)
    rows = _rows(data["groups"])
    assert data["total"] >= 6
    # Пять одинаковых — одной строкой с числом, а не пятью строками.
    assert rows[("media", "MODEL_UNAVAILABLE")] == 5
    assert rows[("media", "TIMEOUT")] == 1
    # Самое частое — первым: с него и начинают чинить. (Сравниваем порядок, а
    # не абсолютное число: в общей базе могут лежать ошибки других тестов.)
    counts = [g["count"] for g in data["groups"]]
    assert counts == sorted(counts, reverse=True)


def test_digest_text_says_what_to_do():
    data = {"hours": 24, "total": 5, "kinds": 1,
            "groups": [{"who": "media", "code": "MODEL_UNAVAILABLE", "count": 5,
                        "sample": "400 Unavailable model",
                        "last": datetime(2026, 9, 17, 12, 0)}]}
    text = notify.digest_text(data)
    assert "5×" in text and "MODEL_UNAVAILABLE" in text
    assert "17.09 12:00" in text


def test_no_errors_says_so():
    assert "ошибок нет" in notify.digest_text({"hours": 24, "total": 0})
