"""
Человеческая формулировка вместо технического мусора.

Пользователь не должен видеть `429`, `RuntimeError`, `None` и трассировки: по
такому тексту непонятно, сломалось что-то у него или у нас, и что делать
дальше. Техническая причина при этом не теряется — она пишется в шаги задачи и
в лог, где её и ищут при разборе.
"""

# Порядок важен: первое совпадение выигрывает, поэтому частные случаи выше общих.
RULES: list[tuple[tuple[str, ...], str]] = [
    (("insufficient_quota", "resource_exhausted", "quota", "429", "rate limit",
      "too many requests"),
     "Генератор занят или исчерпал дневной лимит. Переключаюсь на резервный."),
    (("timeout", "timed out", "read timeout"),
     "Сервис не ответил вовремя. Пробую ещё раз."),
    (("unauthorized", "authentication", "401", "invalid api key", "invalid_api_key"),
     "Ключ не принят — похоже, он истёк или введён с ошибкой. "
     "Проверьте его в Подключениях."),
    (("403", "forbidden", "permission"),
     "Нет прав на это действие. Проверьте доступы аккаунта в Подключениях."),
    (("not found", "404", "unsupported", "deprecat"),
     "Такой модели или ресурса больше нет. Беру доступную замену."),
    (("нет ни одного ключа", "no api key", "all ai providers failed",
      "все ии-провайдеры отказали"),
     "Ни одна модель сейчас не отвечает. Передаю задачу Клоду."),
    (("connection", "network", "dns", "ssl", "eof occurred"),
     "Сеть до сервиса недоступна. Повторю попытку."),
    (("database", "sqlalchemy", "operationalerror"),
     "База данных не ответила. Повторю операцию."),
    (("ffmpeg", "moviepy"),
     "Не удалось собрать видео из готовых кусков. Пробую другой способ монтажа."),
]

DEFAULT = "Не получилось выполнить шаг. Подробности — в логе задачи."


def human(error) -> str:
    """Короткая понятная причина. Пустая ошибка — тоже причина, а не пустая строка."""
    text = str(error or "").strip().lower()
    if not text or text in ("none", "null", "undefined"):
        return DEFAULT
    for needles, message in RULES:
        if any(n in text for n in needles):
            return message
    return DEFAULT


def explain(error) -> dict:
    """Человеку — текст, в лог — техника. Одним объектом, чтобы не разъезжались."""
    return {"message": human(error), "detail": str(error or "")[:500]}
