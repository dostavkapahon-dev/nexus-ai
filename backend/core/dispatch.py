"""
Распределение подзадач между нейросетями (исполнителями).
=========================================================
Главный мозг — Claude (`marketing_director`). Он не пишет всё сам, а раздаёт
подзадачи дешёвым исполнителям: Gemini, DeepSeek, OpenAI, Perplexity.

Зачем: Claude хорошо декомпозирует и держит цель, но платить его ценой за
каждый черновик поста незачем. Здесь описано, кто что умеет и сколько стоит,
чтобы дирижёр выбирал осознанно, а не по жёсткой таблице ролей.

Вызовы идут через `ai_router`, поэтому бесплатно достаются его свойства:
перебор квот при 429, пропуск моделей без ключа, фолбэк «дёшево → дорого».
"""
import os

from core.ai_router import ai_router, COST_PER_1K, PROVIDER_KEY_ENV, AI_ROUTING

# Исполнители: под каким именем дирижёр их зовёт → чем они хороши.
# `model` — что реально уйдёт в ai_router.
EXECUTORS: dict[str, dict] = {
    "gemini": {
        "model": "gemini-2.0-flash",
        "provider": "google",
        "strengths": "быстрые черновики, большие объёмы текста, разбор картинок; "
                     "бесплатная квота — брать по умолчанию",
    },
    "deepseek": {
        "model": "deepseek-chat",
        "provider": "deepseek",
        "strengths": "дешёвые рассуждения, структура и логика текста, "
                     "переписывание и редактура",
    },
    "openai": {
        "model": "gpt-4o",
        "provider": "openai",
        "strengths": "чистовой копирайтинг, живой человеческий тон, "
                     "рекламные тексты и хуки",
    },
    "perplexity": {
        "model": "sonar-pro",
        "provider": "perplexity",
        "strengths": "свежие факты и тренды из интернета со ссылками",
    },
    "claude": {
        "model": "claude-sonnet-4-6",
        "provider": "anthropic",
        "strengths": "сложный анализ и стратегия; дорогой — только когда "
                     "остальные не справятся",
    },
}


def has_key(executor: str) -> bool:
    """Есть ли ключ провайдера у этого исполнителя."""
    spec = EXECUTORS.get(executor)
    if not spec:
        return False
    return bool(os.getenv(PROVIDER_KEY_ENV.get(spec["provider"], ""), ""))


def available_executors() -> list[str]:
    """Кого реально можно позвать прямо сейчас."""
    return [name for name in EXECUTORS if has_key(name)]


def executors_doc() -> str:
    """Строка для системного промпта дирижёра: кто доступен, что умеет, цена.

    Недоступных не показываем вовсе — иначе модель уверенно зовёт провайдера
    без ключа и тратит шаг на гарантированную ошибку.
    """
    lines = []
    for name in available_executors():
        spec = EXECUTORS[name]
        price = COST_PER_1K.get(spec["model"], 0)
        lines.append(f"- {name} ({spec['model']}, ~${price:.5f}/1k токенов): {spec['strengths']}")
    if not lines:
        return ("Исполнителей нет: не задан ни один ключ ИИ. Заверши через done "
                "и попроси добавить GEMINI_API_KEY (бесплатно) в Подключениях.")
    return "\n".join(lines)


def cheapest_available() -> str | None:
    """Самый дешёвый доступный исполнитель — разумный выбор по умолчанию."""
    avail = available_executors()
    if not avail:
        return None
    return min(avail, key=lambda n: COST_PER_1K.get(EXECUTORS[n]["model"], 1))


async def delegate(executor: str, task: str, system: str = "", context: str = "") -> dict:
    """Отдать подзадачу исполнителю.

    Неизвестного или бесключевого исполнителя не роняем, а подменяем самым
    дешёвым доступным: у дирижёра лимит шагов, терять шаг на опечатку в имени
    модели — дороже, чем выполнить задачу не тем, кем просили.
    """
    requested = executor
    if executor not in EXECUTORS or not has_key(executor):
        executor = cheapest_available()
        if not executor:
            return {"ok": False, "executor": requested,
                    "error": "Нет ни одного ключа ИИ. Добавьте GEMINI_API_KEY "
                             "(бесплатно) или другой ключ в Подключениях."}

    spec = EXECUTORS[executor]
    prompt = task if not context else f"{task}\n\nКОНТЕКСТ:\n{context[:4000]}"
    try:
        res = await ai_router.call(spec["model"], system or _DEFAULT_SYSTEM, prompt)
    except Exception as e:
        return {"ok": False, "executor": executor, "model": spec["model"],
                "error": str(e)[:300]}

    out = {"ok": True, "executor": executor, "text": res.get("text", ""),
           "model_used": res.get("model_used", spec["model"]),
           "cost": res.get("cost", 0), "tokens": res.get("tokens", 0)}
    if requested != executor:
        out["substituted_for"] = requested
    # ai_router мог уйти по фолбэку на другого провайдера — дирижёр должен видеть.
    if out["model_used"] != spec["model"]:
        out["note"] = f"исполнитель заменён фолбэком: {spec['model']} → {out['model_used']}"
    return out


_DEFAULT_SYSTEM = (
    "Ты — исполнитель в мультиагентной системе. Делай ровно то, что просят, "
    "без вступлений и лишних пояснений. Отвечай на русском."
)


def routing_table() -> dict:
    """Полная картина маршрутизации — для UI и диагностики."""
    return {
        "director": "claude-sonnet-4-6 (Anthropic)" if os.getenv("ANTHROPIC_API_KEY")
                    else ("gemini (резервный дирижёр)" if os.getenv("GEMINI_API_KEY") else None),
        "default_executor": cheapest_available(),
        "executors": [
            {
                "name": name,
                "model": spec["model"],
                "provider": spec["provider"],
                "cost_per_1k": COST_PER_1K.get(spec["model"], 0),
                "key_env": PROVIDER_KEY_ENV.get(spec["provider"]),
                "available": has_key(name),
                "strengths": spec["strengths"],
            }
            for name, spec in EXECUTORS.items()
        ],
    }
