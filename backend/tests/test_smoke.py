"""
Smoke-тесты: главная цепочка собирается и маршрутизируется.
Запуск: cd backend && python -m pytest tests -q   (или python tests/test_smoke.py)
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_all_modules_import():
    """Все модули бэкенда импортируются — ловит опечатки и битые связи."""
    import main  # noqa: F401
    import core.telegram_bot, core.hixiit, core.memory  # noqa: F401
    import core.marketing_director, core.orchestrator  # noqa: F401


def test_hixiit_detects_kind_and_ratio():
    """HIXIIT сам понимает, что нужно генерировать и в каком формате."""
    from core.hixiit import detect_kind, detect_ratio
    assert detect_kind("сделай reels про доставку") == "video"
    assert detect_kind("нужна обложка поста") == "image"
    assert detect_kind("что угодно", explicit="video") == "video"
    assert detect_ratio("вертикальный ролик") == "9:16"
    assert detect_ratio("горизонтальное видео для youtube") == "16:9"


def test_hixiit_reports_reason_when_unavailable():
    """Без доступов HIXIIT объясняет причину, а не молчит."""
    from core.hixiit import generate
    for var in ("HIGGSFIELD_MCP_URL", "HIGGSFIELD_API_KEY"):
        os.environ.pop(var, None)
    res = asyncio.run(generate("тестовый ролик", kind="video"))
    assert res["ok"] is False
    assert res["tried"], "должен быть список испробованных путей"
    assert "MCP" in res["error"]


def test_director_collects_media():
    """Медиа из инструментов доходят до Telegram-слоя."""
    from core.marketing_director import _collect_media
    media = []
    _collect_media("make_image", {"ok": True, "url": "http://x/y.png", "kind": "image"}, media)
    _collect_media("publish", {"ok": True, "url": "http://x/z.png"}, media)
    assert len(media) == 1 and media[0]["kind"] == "image"


def test_telegram_buttons_wired():
    """Кнопки подтверждения/публикации существуют и содержат id пункта плана."""
    from core.telegram_bot import _plan_buttons
    flat = [b["callback_data"] for row in _plan_buttons("plan123") for b in row]
    assert {"ok:plan123", "regen:plan123", "edit:plan123",
            "queue:plan123", "pub:plan123"} == set(flat)


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"✅ {name}")
            except Exception as e:
                failed += 1
                print(f"❌ {name}: {e}")
    sys.exit(1 if failed else 0)
