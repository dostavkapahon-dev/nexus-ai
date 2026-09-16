"""
Классификация отказов: что именно повторять, а что повторять НЕЛЬЗЯ.

Требование ТЗ §28–§29. Без него любая неудача выглядела одинаково — «задача
упала» — и повтор означал повтор ВСЕГО. А значит: не прошла отправка в
Telegram — заново генерируем видео за 32 кредита; не записался архив — снова
генерируем; сорвалась публикация — создаём новый контент. Деньги и время
сгорали на ровном месте, а в ленте появлялись дубликаты.

Правило простое: повторяем ровно тот шаг, который сломался, и пользуемся уже
готовым результатом — он сохранён артефактом.
"""

# Коды из ТЗ §28. Список закрытый: «прочее» тоже код, а не отсутствие ответа.
AUTH = "AUTH_ERROR"
RATE_LIMIT = "RATE_LIMIT"
QUOTA = "QUOTA"
INVALID = "INVALID_REQUEST"
MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
PROVIDER_DOWN = "PROVIDER_DOWN"
TIMEOUT = "TIMEOUT"
GENERATION_FAILED = "GENERATION_FAILED"
RESULT_NOT_FOUND = "RESULT_NOT_FOUND"
DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
STORAGE_FAILED = "STORAGE_FAILED"
TELEGRAM_FAILED = "TELEGRAM_FAILED"
PUBLISH_FAILED = "PUBLISH_FAILED"
BROWSER_FAILED = "BROWSER_FAILED"
UNKNOWN = "UNKNOWN"

# Что повторять при каждом коде. Главное здесь — «delivery», «storage» и
# «publish»: они НЕ должны тянуть за собой новую генерацию.
DELIVERY, STORAGE, PUBLISH, GENERATION, NOTHING = (
    "delivery", "storage", "publish", "generation", "nothing")

RETRY_SCOPE = {
    TELEGRAM_FAILED: DELIVERY,
    STORAGE_FAILED: STORAGE,
    DOWNLOAD_FAILED: STORAGE,
    PUBLISH_FAILED: PUBLISH,
    RATE_LIMIT: GENERATION,
    TIMEOUT: GENERATION,
    PROVIDER_DOWN: GENERATION,
    GENERATION_FAILED: GENERATION,
    BROWSER_FAILED: GENERATION,
    RESULT_NOT_FOUND: GENERATION,
    MODEL_UNAVAILABLE: GENERATION,
    # Эти повтором не лечатся: ключ не станет верным от второй попытки, а
    # квота не появится. Повторять их — жечь лимиты впустую.
    AUTH: NOTHING,
    QUOTA: NOTHING,
    INVALID: NOTHING,
    UNKNOWN: GENERATION,
}

HUMAN = {
    AUTH: "ключ или доступ не приняты",
    RATE_LIMIT: "слишком часто — провайдер попросил подождать",
    QUOTA: "закончилась квота или кредиты",
    INVALID: "запрос составлен неверно",
    MODEL_UNAVAILABLE: "модель недоступна",
    PROVIDER_DOWN: "провайдер не отвечает",
    TIMEOUT: "не уложились в отведённое время",
    GENERATION_FAILED: "генерация не дала результата",
    RESULT_NOT_FOUND: "результат не найден",
    DOWNLOAD_FAILED: "файл не скачался",
    STORAGE_FAILED: "не удалось сохранить",
    TELEGRAM_FAILED: "не удалось доставить в чат",
    PUBLISH_FAILED: "публикация не прошла",
    BROWSER_FAILED: "браузер не справился",
    UNKNOWN: "причина не распознана",
}

# Приметы в тексте ошибки. Порядок важен: сначала узкие признаки, потом общие,
# иначе «unauthorized» внутри длинного текста таймаута уведёт не туда.
_MARKS = (
    (TELEGRAM_FAILED, ("telegram", "sendphoto", "sendvideo", "sendmessage",
                       "chat not found", "bot was blocked")),
    (PUBLISH_FAILED, ("publish", "публикац", "instagram api", "media_publish")),
    (STORAGE_FAILED, ("drive", "storagequota", "не удалось сохранить", "storage")),
    (DOWNLOAD_FAILED, ("download", "не скачал", "скачать", "content-length")),
    (BROWSER_FAILED, ("browser", "playwright", "chromium", "page.goto",
                      "снимок экрана", "screenshot")),
    (QUOTA, ("quota", "insufficient", "credits", "кредит", "billing")),
    (RATE_LIMIT, ("rate limit", "429", "too many requests")),
    (AUTH, ("401", "403", "unauthorized", "forbidden", "invalid api key",
            "неверный ключ")),
    (MODEL_UNAVAILABLE, ("unavailable model", "model not found", "no such model",
                         "модель недоступна")),
    (INVALID, ("400", "422", "validation", "invalid request")),
    (TIMEOUT, ("timeout", "timed out", "не ответил", "не уложил")),
    (PROVIDER_DOWN, ("503", "502", "connection refused", "connecterror",
                     "connecttimeout", "service unavailable")),
    (RESULT_NOT_FOUND, ("нет ссылки", "result not found", "пустой ответ")),
    (GENERATION_FAILED, ("generation failed", "генерация не удалась",
                         "недоступен ни одним путём")),
)


def classify(error) -> str:
    """Код отказа по тексту ошибки. Незнакомое — UNKNOWN, а не выдумка."""
    text = str(error or "").lower()
    if not text.strip():
        return UNKNOWN
    for code, marks in _MARKS:
        if any(m in text for m in marks):
            return code
    return UNKNOWN


def retry_scope(code: str) -> str:
    """Что повторять. Никогда не возвращает «всё»."""
    return RETRY_SCOPE.get(code, GENERATION)


def explain(error) -> dict:
    """Код, объяснение по-человечески и что делать дальше."""
    code = classify(error)
    scope = retry_scope(code)
    what = {
        DELIVERY: "повторю доставку — файл уже создан и сохранён",
        STORAGE: "повторю сохранение — файл уже создан",
        PUBLISH: "повторю публикацию — контент уже готов",
        GENERATION: "нужна новая попытка генерации",
        NOTHING: "повтор не поможет, нужно менять настройку",
    }[scope]
    return {"code": code, "why": HUMAN.get(code, HUMAN[UNKNOWN]),
            "scope": scope, "action": what,
            "costs_money": scope == GENERATION}
