"""
Ключ с неправильным именем — это отсутствующий ключ.

Повторявшаяся боль: переменная стоит в списке хостинга, человек считает
интеграцию подключённой, а код читает переменную с другим именем и ключа не
видит. Снаружи это «ключ есть, но ничего не работает», и чинить начинают код.

Здесь проверяется, что такие имена находятся, подсказка не меняется от запуска
к запуску, чужие переменные не трогаются и значения нигде не всплывают.
"""
import pytest

from core import env_audit
from core import telegram_bot as tb


# Настоящий список переменных из Render, на котором это и вскрылось.
REAL = {"Ayrshare": "v", "DATABASE_URL": "v", "Deepseek": "v",
        "GEMINI_API_KEY": "v", "GEMINI_API_KEY1": "v", "github": "v",
        "HIGGSFIELD_API_KEY": "v", "HIGGSFIELD_MCP_URL": "v",
        "HIGGSFIELD_SECRET": "v", "instagram": "v", "OPENAI_API_KEY": "v",
        "qroc": "v", "TELEGRAM_BOT_TOKEN": "v", "TELEGRAM_CHAT_ID": "v"}


def test_correctly_named_keys_are_not_reported():
    found = {x["given"] for x in env_audit.misnamed(REAL)}

    for good in ("DATABASE_URL", "GEMINI_API_KEY", "OPENAI_API_KEY",
                 "HIGGSFIELD_API_KEY", "HIGGSFIELD_SECRET",
                 "HIGGSFIELD_MCP_URL", "TELEGRAM_BOT_TOKEN"):
        assert good not in found, f"{good} назван верно — тревожить нельзя"


def test_every_misnamed_key_is_caught():
    found = {x["given"]: x["expected"] for x in env_audit.misnamed(REAL)}

    assert found["Deepseek"] == "DEEPSEEK_API_KEY"
    assert found["qroc"] == "GROQ_API_KEY", "частая опечатка в «groq»"
    assert found["github"] == "GITHUB_MODELS_TOKEN"
    assert found["instagram"] == "INSTAGRAM_ACCESS_TOKEN"
    assert found["GEMINI_API_KEY1"] == "GEMINI_API_KEY"


def test_retired_integration_is_marked_for_deletion():
    """Ayrshare заменён бесплатной разведкой — предлагать имя бессмысленно."""
    item = [x for x in env_audit.misnamed(REAL) if x["given"] == "Ayrshare"][0]

    assert item["expected"] == ""
    assert "удалить" in item["note"]


def test_hint_does_not_change_between_runs():
    """Подсказка, меняющаяся от запуска к запуску, хуже отсутствия подсказки."""
    runs = [{x["given"]: x["expected"] for x in env_audit.misnamed(REAL)}
            for _ in range(5)]

    assert all(r == runs[0] for r in runs)


def test_system_variables_are_left_alone():
    env = {"PATH": "/bin", "PORT": "8000", "HOME": "/root", "PWD": "/app",
           "RENDER_EXTERNAL_URL": "https://x", "PYTHONPATH": "."}

    assert env_audit.misnamed(env) == []


def test_unrelated_variables_are_not_guessed_at():
    """Догадка про чужую переменную — это ложная тревога, а не помощь."""
    env = {"MY_CUSTOM_FLAG": "1", "SENTRY_DSN": "x", "REDIS_URL": "x"}

    assert env_audit.misnamed(env) == []


def test_values_never_appear_in_the_report():
    lines = "\n".join(env_audit.as_lines(env_audit.misnamed(
        {"qroc": "sk-super-secret-value"})))

    assert "qroc" in lines
    assert "sk-super-secret-value" not in lines, "секрет не должен попадать в чат"


def test_nothing_to_report_means_no_section():
    assert env_audit.as_lines([]) == []


@pytest.mark.asyncio
async def test_diag_shows_the_warning(client, monkeypatch):
    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append(text)
        return {}

    monkeypatch.setattr(tb, "send_message", fake_send)
    monkeypatch.setattr(env_audit, "misnamed",
                        lambda environ=None: [{"given": "qroc",
                                               "expected": "GROQ_API_KEY",
                                               "note": "переименуйте в GROQ_API_KEY"}])
    await tb._handle_command("930", "/diag")

    text = "\n".join(sent)
    assert "не читаются" in text
    assert "qroc" in text and "GROQ_API_KEY" in text
