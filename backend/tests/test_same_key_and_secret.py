"""
Ключ и секрет — разные значения, и одинаковые надо ловить до запроса.

С сервера пришло: `401 {"detail":"Invalid credentials"}`, а рядом — хвосты обеих
половин: `ключ …2cb5` и `секрет …2cb5`. Форма у обоих безупречная (UUID из 36
символов), поэтому прежняя проверка их пропускала, и человек шёл искать причину
в самом ключе. На деле в оба поля попало одно и то же значение.
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


def test_identical_halves_are_caught(monkeypatch):
    """Именно этот случай пришёл с сервера."""
    monkeypatch.setenv("HIGGSFIELD_API_KEY", UUID_A)
    monkeypatch.setenv("HIGGSFIELD_SECRET", UUID_A)

    problem = hf.key_problem()

    assert problem, "две одинаковые половины — гарантированный 401"
    assert "ОДНО И ТО ЖЕ" in problem
    assert UUID_A not in problem, "значение показывать нельзя"


def test_different_halves_pass(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_API_KEY", UUID_A)
    monkeypatch.setenv("HIGGSFIELD_SECRET", UUID_B)

    assert hf.key_problem() == ""


@pytest.mark.asyncio
async def test_no_request_is_made_with_identical_halves(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_API_KEY", UUID_A)
    monkeypatch.setenv("HIGGSFIELD_SECRET", UUID_A)

    def forbidden(*a, **kw):
        raise AssertionError("заведомый 401 не стоит сетевого запроса")

    monkeypatch.setattr("httpx.AsyncClient.get", forbidden)
    res = await hf.check()

    assert res["ok"] is False
    assert "ОДНО И ТО ЖЕ" in res["error"]


def test_pair_pasted_into_one_field_still_works(monkeypatch):
    """«ключ:секрет» одной строкой — это разные половины, а не дубль."""
    monkeypatch.setenv("HIGGSFIELD_API_KEY", f"{UUID_A}:{UUID_B}")

    assert hf.key_problem() == ""
