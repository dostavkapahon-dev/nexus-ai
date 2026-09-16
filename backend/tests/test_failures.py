"""Повторять надо сломавшийся шаг, а не всё подряд.

Требование §28–§29. Без разбора причин любая неудача означала повтор ВСЕГО:
не ушло сообщение в Telegram — заново генерируем видео за 32 кредита; не
записался архив — снова генерируем; сорвалась публикация — создаём новый
контент. Деньги сгорали, а в ленте появлялись дубликаты.
"""
import pytest

from core import failures as f


def test_telegram_failure_never_costs_a_generation():
    """Главное правило файла."""
    v = f.explain("Telegram error: Bad Request: chat not found")
    assert v["code"] == f.TELEGRAM_FAILED
    assert v["scope"] == f.DELIVERY
    assert v["costs_money"] is False
    assert "файл уже создан" in v["action"]


def test_storage_failure_repeats_only_storage():
    v = f.explain("Drive: storageQuotaExceeded")
    assert v["scope"] == f.STORAGE and v["costs_money"] is False


def test_publish_failure_does_not_recreate_content():
    v = f.explain("Instagram API: media_publish failed")
    assert v["scope"] == f.PUBLISH and v["costs_money"] is False


def test_auth_and_quota_are_not_retried_at_all():
    """Ключ не станет верным от второй попытки, квота не появится."""
    assert f.explain("401 Unauthorized")["scope"] == f.NOTHING
    assert f.explain("insufficient credits")["scope"] == f.NOTHING


def test_generation_failure_does_cost_money_and_says_so():
    v = f.explain("генерация не удалась: недоступен ни одним путём")
    assert v["scope"] == f.GENERATION and v["costs_money"] is True


def test_browser_failure_is_named_separately():
    assert f.classify("Page.goto: Timeout 45000ms exceeded") == f.BROWSER_FAILED


def test_unknown_is_a_code_not_a_silence():
    assert f.classify("что-то пошло не так") == f.UNKNOWN
    assert f.classify("") == f.UNKNOWN
    assert f.explain("")["why"]


def test_every_code_has_a_scope_and_a_translation():
    for code in (f.AUTH, f.RATE_LIMIT, f.QUOTA, f.INVALID, f.MODEL_UNAVAILABLE,
                 f.PROVIDER_DOWN, f.TIMEOUT, f.GENERATION_FAILED,
                 f.RESULT_NOT_FOUND, f.DOWNLOAD_FAILED, f.STORAGE_FAILED,
                 f.TELEGRAM_FAILED, f.PUBLISH_FAILED, f.BROWSER_FAILED, f.UNKNOWN):
        assert code in f.RETRY_SCOPE and code in f.HUMAN


@pytest.mark.asyncio
async def test_redelivery_does_not_generate_anything(monkeypatch):
    """Повтор доставки берёт готовый файл из артефакта."""
    from core import artifacts
    store = {}

    async def fake_get(key):
        return store.get(key, "")

    async def fake_set(key, value):
        store[key] = value

    monkeypatch.setattr(artifacts, "_kv_get", fake_get)
    monkeypatch.setattr(artifacts, "_kv_set", fake_set)
    art = await artifacts.save("https://cdn/x.mp4", "video", provider="higgsfield",
                               model="seedance_2_5", prompt="шашлык")

    sent = {}

    async def fake_video(chat_id, url, caption=""):
        sent.update(chat_id=chat_id, url=url)
        return {"ok": True}

    async def must_not_generate(*a, **k):
        raise AssertionError("повтор доставки не должен ничего генерировать")

    monkeypatch.setattr("publishers.telegram_pub.send_video", fake_video)
    monkeypatch.setattr("core.hixiit.generate", must_not_generate)
    res = await artifacts.redeliver(art, "123")
    assert res["ok"] and sent["url"] == "https://cdn/x.mp4"
    assert (await artifacts.get(art))["telegram"] == "доставлено повторно"


@pytest.mark.asyncio
async def test_redelivery_of_unknown_artifact_is_honest(monkeypatch):
    from core import artifacts

    async def fake_get(key):
        return ""

    monkeypatch.setattr(artifacts, "_kv_get", fake_get)
    res = await artifacts.redeliver("ART-нет", "123")
    assert res["ok"] is False and "не найден" in res["error"]
