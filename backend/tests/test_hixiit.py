"""HIXIIT — генеративный слой: выбор модели, фолбэки, честные причины отказа."""
import pytest

from core import hixiit


def test_kind_is_detected_from_wording():
    """Тип генерации виден из формулировки — отдельная команда не нужна."""
    assert hixiit.detect_kind("сделай reels про доставку") == "video"
    assert hixiit.detect_kind("нужен ролик о кофе") == "video"
    assert hixiit.detect_kind("сторис на завтра") == "video"
    assert hixiit.detect_kind("обложка для поста") == "image"
    assert hixiit.detect_kind("что угодно", explicit="video") == "video"


def test_ratio_follows_the_platform_hint():
    assert hixiit.detect_ratio("вертикальный ролик") == "9:16"
    assert hixiit.detect_ratio("горизонтальное видео для youtube") == "16:9"
    assert hixiit.detect_ratio("квадрат для аватара") == "1:1"


def test_model_needing_foreign_input_is_rejected():
    """Каталог рекомендует и модели, которым нужен чужой вход (напр. ссылка на
    YouTube). Такую взять нельзя — задача упадёт уже после списания кредитов."""
    catalog = {"items": [
        {"id": "clipify", "name": "Personal Clipper",
         "parameters": [{"name": "urls", "required": "required"}]},
        {"id": "seedance", "name": "Seedance",
         "parameters": [{"name": "prompt", "required": "required"},
                        {"name": "aspect_ratio", "required": "optional"}]},
    ]}
    assert [m["id"] for m in hixiit._as_model_list(catalog, has_reference=False)] == ["seedance"]


def test_model_requiring_reference_only_when_we_have_one():
    catalog = {"items": [{"id": "img2vid", "parameters": [
        {"name": "prompt", "required": "required"},
        {"name": "image_url", "required": "required"}]}]}
    assert hixiit._as_model_list(catalog, has_reference=False) == []
    assert len(hixiit._as_model_list(catalog, has_reference=True)) == 1


def test_media_url_is_found_in_any_response_shape():
    assert hixiit._find_media_url({"result": {"video_url": "https://x/y.mp4"}}) == "https://x/y.mp4"
    assert hixiit._find_media_url({"items": [{"output": {"url": "https://x/z.png"}}]}) == "https://x/z.png"
    assert hixiit._find_media_url({"status": "queued"}) is None


@pytest.mark.asyncio
async def test_video_failure_explains_every_path(monkeypatch):
    """Молчаливый отказ — худший исход: человек не знает, что чинить."""
    for var in ("HIGGSFIELD_MCP_URL", "HIGGSFIELD_API_KEY"):
        monkeypatch.delenv(var, raising=False)

    res = await hixiit.generate("ролик про доставку", kind="video")

    assert res["ok"] is False
    assert "MCP" in res["error"]
    assert any("HIGGSFIELD_API_KEY" in t for t in res["tried"])


@pytest.mark.asyncio
async def test_image_always_returns_something(monkeypatch):
    """Для картинки есть бесплатный запасной путь — визуал не должен пропадать."""
    for var in ("HIGGSFIELD_MCP_URL", "HIGGSFIELD_API_KEY"):
        monkeypatch.delenv(var, raising=False)

    res = await hixiit.generate("обложка про кофе", kind="image")

    assert res["ok"] is True
    assert res["provider"] == "pollinations_free"
    assert res["tried"], "причины недоступности HIXIIT должны сохраняться"


@pytest.mark.asyncio
async def test_broken_mcp_client_does_not_kill_the_task(monkeypatch):
    """Сломанная сборка mcp роняет интерпретатор через pyo3 PanicException,
    а она не наследуется от Exception и проходит сквозь обычные except."""
    monkeypatch.setenv("HIGGSFIELD_MCP_URL", "https://example.invalid/mcp")
    monkeypatch.delenv("HIGGSFIELD_API_KEY", raising=False)

    class Panic(BaseException):
        pass

    async def boom(tool, args, timeout=600.0):
        raise Panic("Python API call failed")

    monkeypatch.setattr(hixiit, "_mcp_call", boom)

    res = await hixiit.generate("ролик", kind="video")
    assert res["ok"] is False


def test_api_auth_uses_the_documented_scheme(monkeypatch):
    """Оба варианта авторизации сразу — так, как их шлёт официальный SDK.

    v1 (job-sets, /v1/text2image/soul) читает заголовки `hf-api-key` и
    `hf-secret`; v2 — `Authorization: Key ключ:секрет`. Раньше уходил
    `Bearer ключ`, который не принимается ни там, ни там.
    """
    from core import higgsfield as hf

    monkeypatch.delenv("HF_KEY", raising=False)
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "key123")
    monkeypatch.setenv("HIGGSFIELD_SECRET", "secret456")

    headers = hf._headers()
    assert headers["Authorization"] == "Key key123:secret456"
    assert headers["hf-api-key"] == "key123"
    assert headers["hf-secret"] == "secret456"


def test_key_without_secret_is_not_a_working_credential(monkeypatch):
    """Один ключ без секрета — заведомо отклонённый запрос: лучше сказать сразу."""
    from core import higgsfield as hf

    monkeypatch.delenv("HF_KEY", raising=False)
    monkeypatch.delenv("HF_API_SECRET", raising=False)
    monkeypatch.delenv("HIGGSFIELD_SECRET", raising=False)
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "key123")

    assert hf.credentials() == ""


def test_credentials_accept_sdk_names_and_joined_pair(monkeypatch):
    """Ключ, скопированный из документации Higgsfield, должен работать как есть."""
    from core import higgsfield as hf

    for var in ("HF_KEY", "HIGGSFIELD_API_KEY", "HIGGSFIELD_SECRET",
                "HF_API_KEY", "HF_API_SECRET"):
        monkeypatch.delenv(var, raising=False)

    monkeypatch.setenv("HF_API_KEY", "k")
    monkeypatch.setenv("HF_API_SECRET", "s")
    assert hf.credentials() == "k:s"

    monkeypatch.setenv("HF_KEY", "one:two")
    assert hf.credentials() == "one:two"
