"""
HOOKS & MARKETING LOGIC — зашитая экспертиза маркетолога Pakhon Studio.
=====================================================================
Конкретные формулы вирусных хуков, контент-столпы (80/20), темы по дням недели,
и логика РОТАЦИИ хуков (не повторять тип за последние 7 дней) + контроль.

Это «мозг» в коде: даже без живого AI система знает, КАК делать вирусный Reels.
"""
import os
import json
from datetime import date, datetime

BASE = os.path.dirname(os.path.dirname(__file__))
HISTORY_PATH = os.path.join(BASE, "data", "hook_history.json")

# Конкретные формулы хуков по типам (первые 1-3 сек). {X}/{N}/{prof} — подставить.
HOOK_FORMULAS = {
    "провокация": [
        "Все делают {X} НЕПРАВИЛЬНО",
        "{prof} больше не нужны. Вот почему",
        "Перестань {X} — это убивает твой результат",
        "Тебя обманывают про {X}",
    ],
    "цифра": [
        "{N} способа сделать {X} за 60 секунд",
        "{N} AI-инструмента, что заменят {prof}",
        "Сделал {X} за {N} минут — вот как",
        "{N} ошибки, из-за которых нет клиентов",
    ],
    "боль": [
        "Устал работать и не зарабатывать?",
        "Ты теряешь клиентов каждый день из-за {X}",
        "Почему у тебя нет заказов (горькая правда)",
        "Делаешь {X} вручную? Ты теряешь часы",
    ],
    "тайна": [
        "Вот почему у тебя нет клиентов",
        "Секрет {X}, о котором молчат",
        "Что на самом деле стоит за {X}",
        "Я нашёл способ {X} — досмотри до конца",
    ],
}

# Контент-столпы 80/20 (ценность/обучение vs прямое продвижение)
CONTENT_PILLARS = {
    "value": 0.8,       # обучение, инсайты, до/после, разоблачения
    "promo": 0.2,       # услуги Pakhon Studio
}

# Темы по дням недели (0=Пн .. 6=Вс)
DAY_THEMES = {
    0: "мотивация/старт недели — как начать с AI",
    1: "инструмент дня — конкретный AI-кейс",
    2: "до/после — трансформация за секунды",
    3: "разоблачение — как на самом деле делают результат",
    4: "результаты/итоги — цифры и кейсы",
    5: "обучение — пошаговый разбор",
    6: "обучение/вдохновение — большой гайд",
}

# Форматы для ротации (алгоритм любит разнообразие)
FORMAT_ROTATION = ["talking_head", "b_roll", "slideshow"]


def _load_history() -> list:
    try:
        if os.path.exists(HISTORY_PATH):
            with open(HISTORY_PATH, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_history(hist: list) -> None:
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(hist[-60:], f, ensure_ascii=False, indent=2)


def recent_hook_types(days: int = 7) -> list:
    """Типы хуков, использованные за последние N дней."""
    hist = _load_history()
    cutoff = datetime.now().timestamp() - days * 86400
    return [h["type"] for h in hist if h.get("ts", 0) >= cutoff]


def pick_hook_type() -> str:
    """Выбирает тип хука, которого НЕ было за 7 дней (ротация)."""
    used = set(recent_hook_types(7))
    for t in HOOK_FORMULAS:
        if t not in used:
            return t
    # все использованы — берём наименее частый
    used_list = recent_hook_types(7)
    return min(HOOK_FORMULAS, key=lambda t: used_list.count(t))


def pick_format() -> str:
    """Ротация форматов по истории."""
    hist = _load_history()
    last = hist[-1].get("format") if hist else None
    for f in FORMAT_ROTATION:
        if f != last:
            return f
    return FORMAT_ROTATION[0]


def day_theme(d: date = None) -> str:
    d = d or date.today()
    return DAY_THEMES.get(d.weekday(), "обучение")


def pillar_today() -> str:
    """80/20: каждый 5-й пост — промо, остальные — ценность."""
    n = len(_load_history())
    return "promo" if (n % 5 == 4) else "value"


def record(hook_type: str, fmt: str = "", theme: str = "") -> None:
    """Записывает использованный хук/формат для ротации и контроля."""
    hist = _load_history()
    hist.append({"ts": datetime.now().timestamp(), "date": date.today().isoformat(),
                 "type": hook_type, "format": fmt, "theme": theme})
    _save_history(hist)


def guidance() -> dict:
    """Сводка-указание для мозга на сегодня: тип хука, формат, тема, столп, формулы."""
    ht = pick_hook_type()
    return {
        "hook_type": ht,
        "hook_formulas": HOOK_FORMULAS[ht],
        "format": pick_format(),
        "day_theme": day_theme(),
        "pillar": pillar_today(),
        "avoid_hook_types": list(set(recent_hook_types(7))),
    }
