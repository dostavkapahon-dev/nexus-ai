"""
Ключ Higgsfield неверного формата: сказать это словами, а не дампом JSON.

С живого сервера пришло: `422 {"detail":[{"type":"uuid_parsing",
"loc":["header","hf-api-key"],"msg":"Input should be a valid UUID..."}]}`.
Платформа жаловалась не на промпт, а на САМ КЛЮЧ в заголовке — но человек видел
«Higgsfield отверг параметры (422)» с куском JSON и шёл искать поломку в коде.

Здесь проверяется: неверная форма ключа распознаётся до запроса, ответ платформы
переводится на человеческий, а перепутанные местами ключ и секрет называются
прямо.
"""
import pytest

from core import higgsfield as hf


UUID_A = "3f8c1a2b-4d5e-6f70-8192-a3b4c5d6e7f8"
UUID_B = "9e8d7c6b-5a49-3827-1605-f4e3d2c1b0a9"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("HF_KEY", "HF_API_KEY", "HF_SECRET", "HF_API_SECRET",
              "HIGGSFIELD_API_KEY", "HIGGSFIELD_SECRET"):
        monkeypatch.delenv(k, raising=False)


def test_proper_pair_has_no_complaint(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_API_KEY", UUID_A)
    monkeypatch.setenv("HIGGSFIELD_SECRET", UUID_B)

    assert hf.key_problem() == ""


def test_short_key_is_explained_with_its_length(monkeypatch):
    """Именно этот случай пришёл с сервера: ключ короче, чем ждёт платформа."""
    key = "sk-abcdef123456"                      # 15 символов вместо 36
    monkeypatch.setenv("HIGGSFIELD_API_KEY", key)
    monkeypatch.setenv("HIGGSFIELD_SECRET", "also-not-a-uuid")

    problem = hf.key_problem()

    assert "HIGGSFIELD_API_KEY" in problem
    assert "36" in problem, "человеку нужна ожидаемая длина"
    assert str(len(key)) in problem, "и фактическая, чтобы увидеть расхождение"
    assert "API keys" in problem, "надо сказать, где взять правильный ключ"


def test_swapped_values_are_named_as_swapped(monkeypatch):
    """Секрет похож на ключ, ключ — нет: почти наверняка перепутаны местами."""
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "not-a-uuid")
    monkeypatch.setenv("HIGGSFIELD_SECRET", UUID_B)

    assert "перепутаны местами" in hf.key_problem()


def test_missing_pair_asks_for_both(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_API_KEY", UUID_A)

    assert hf.key_problem() == hf.NO_KEY


@pytest.mark.asyncio
async def test_request_is_not_wasted_on_a_broken_key(monkeypatch):
    """Форма заведомо негодная — в сеть не идём вовсе."""
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "sk-short")
    monkeypatch.setenv("HIGGSFIELD_SECRET", UUID_B)

    def forbidden(*a, **kw):
        raise AssertionError("запрос с заведомо негодным ключом не нужен")

    monkeypatch.setattr("httpx.AsyncClient.post", forbidden)
    res = await hf._post(hf.PATH_IMAGE, {"prompt": "тест"})

    assert res["ok"] is False
    assert "HIGGSFIELD_API_KEY" in res["error"]


def test_platform_complaint_about_the_key_is_translated():
    """Настоящий ответ платформы — не JSON в чат, а объяснение."""
    real = {"detail": [{"type": "uuid_parsing",
                        "loc": ["header", "hf-api-key"],
                        "msg": "Input should be a valid UUID, invalid length"}]}

    text = hf._error_text(422, real)

    assert "HIGGSFIELD_API_KEY" in text
    assert "API keys" in text, "надо сказать, где взять правильное значение"
    assert "uuid_parsing" not in text, "внутренности платформы человеку не нужны"


def test_complaint_about_the_secret_names_the_secret():
    data = {"detail": [{"loc": ["header", "hf-secret"], "msg": "invalid"}]}

    assert "HIGGSFIELD_SECRET" in hf._error_text(422, data)


def test_real_parameter_errors_are_still_shown():
    """Жалоба на промпт — это другая ошибка, её подменять нельзя."""
    data = {"detail": [{"loc": ["body", "params", "prompt"],
                        "msg": "field required"}]}

    text = hf._error_text(422, data)

    assert "field required" in text
    assert "API keys" not in text


# ── чем похоже вставленное значение ───────────────────────────────────────────
#
# «Не тот формат» человеку мало что даёт: он уже вставил то, что нашёл в
# кабинете, и не понимает, что нашёл не то. С сервера пришёл ключ из 64
# hex-символов — это токен доступа, а не ключ платформы.

HEX64 = "8f" * 32


def test_hex_token_is_recognised_as_a_token(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_API_KEY", HEX64)
    monkeypatch.setenv("HIGGSFIELD_SECRET", "not-a-uuid-either")

    problem = hf.key_problem()

    assert "токен" in problem, "надо сказать, ЧЕМ похоже вставленное"
    assert "HIGGSFIELD_MCP_TOKEN" in problem, "и где его настоящее место"
    assert HEX64 not in problem, "значение показывать нельзя"


def test_key_of_another_service_is_named_as_such(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "sk-proj-abcdef")
    monkeypatch.setenv("HIGGSFIELD_SECRET", "also-wrong")

    assert "другого сервиса" in hf.key_problem()


def test_unrecognisable_value_gets_no_invented_guess(monkeypatch):
    """Не знаем — молчим, а не сочиняем."""
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "qwerty12345")
    monkeypatch.setenv("HIGGSFIELD_SECRET", "asdfgh67890")

    problem = hf.key_problem()

    assert "36" in problem
    assert "токен" not in problem and "другого сервиса" not in problem


def test_hint_does_not_fire_on_a_correct_pair(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_API_KEY", UUID_A)
    monkeypatch.setenv("HIGGSFIELD_SECRET", UUID_B)

    assert hf.key_problem() == ""
