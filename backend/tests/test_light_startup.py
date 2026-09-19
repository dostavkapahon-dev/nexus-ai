"""Сервис не должен держать в памяти то, чем не пользуется.

Три SDK провайдеров вместе занимают около 110 МБ из 512 МБ всего инстанса:
google.generativeai ~64, anthropic ~24, openai ~20. Загруженные на старте, они
держали эту память всегда — в том числе когда ключа к провайдеру нет вовсе.
А не хватало её потом браузеру, и ядро убивало весь сервис.
"""
import pathlib
import subprocess
import sys

# Подпроцесс запускаем из каталога backend независимо от того, откуда позвали
# pytest: иначе `import main` просто не найдётся и тест проверит пустоту.
BACKEND = pathlib.Path(__file__).resolve().parent.parent

HEAVY = ("anthropic", "openai", "google.generativeai")


def _loaded_after(statement: str) -> set:
    code = (f"import sys; {statement}; "
            f"print(','.join(m for m in {HEAVY!r} if m in sys.modules))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, cwd=str(BACKEND))
    assert out.returncode == 0, out.stderr[-800:]
    return {m for m in out.stdout.strip().split(",") if m}


def test_importing_the_router_does_not_load_provider_sdks():
    assert _loaded_after("import core.ai_router") == set()


def test_importing_the_app_does_not_load_provider_sdks():
    assert _loaded_after("import main") == set()


def test_the_sdk_is_still_reachable_when_needed():
    """Ленивость не должна означать «пакета нет»."""
    from core import ai_router
    assert ai_router._anthropic().__name__ == "anthropic"
    assert ai_router._openai().__name__ == "openai"
