"""Всё, что нужно интеграции для работы, должно сохраняться через сайт.

Поле, которого нет в FIELDS, невозможно сохранить в дашборде — только через
переменные окружения хостинга. Для пары «ключ + секрет» это означает, что
интеграция выглядит подключённой, но каждый запрос отклоняется.
"""
import pytest

from core import credentials


def _keys():
    return {f.key for f in credentials.FIELDS}


def test_higgsfield_secret_is_savable():
    """Higgsfield требует пару: заголовок «Authorization: Key ключ:секрет».

    Раньше в дашборде было только поле ключа, поэтому подключить Higgsfield
    через сайт было нельзя в принципе.
    """
    keys = _keys()
    assert "higgsfield_api_key" in keys
    assert "higgsfield_secret" in keys


def test_paired_credentials_are_complete():
    """У интеграций, где нужны две части, обе части должны быть в списке."""
    pairs = [
        ("instagram_access_token", "instagram_account_id"),
        ("vk_access_token", "vk_group_id"),
        ("threads_access_token", "threads_user_id"),
        ("higgsfield_api_key", "higgsfield_secret"),
    ]
    keys = _keys()
    missing = [(a, b) for a, b in pairs if (a in keys) != (b in keys)]
    assert not missing, f"половина пары доступов недоступна для сохранения: {missing}"


@pytest.mark.asyncio
async def test_saved_field_reaches_the_process(client):
    """Сохранённое в дашборде сразу видно коду, который читает os.getenv."""
    import os

    await credentials.set("higgsfield_secret", "secret-123")
    assert os.environ.get("HIGGSFIELD_SECRET") == "secret-123"

    from core.higgsfield import credentials as hf_credentials
    os.environ["HIGGSFIELD_API_KEY"] = "key-123"
    os.environ.pop("HF_KEY", None)
    assert hf_credentials() == "key-123:secret-123"
