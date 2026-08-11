"""
Контракты передачи данных между агентами.

Раньше агенты обменивались произвольными dict: следующий в цепочке не знал, какие
поля обязательны, насколько результат надёжен и откуда он взят. Ошибка одного
агента молча превращалась в пустой словарь, и конвейер шёл дальше на выдумках.

Теперь у каждой передачи есть форма: данные, уверенность, источники и предупреждения.
Это не мешает работать со словарями — `AgentResult` в них и разворачивается.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime

# Что обязан вернуть каждый агент, чтобы следующий мог на это опираться.
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "niche_analyst": ("audience", "content_pillars"),
    "viral_hunter": ("viral_topics", "hooks"),
    "strategist": ("plan",),
    "copywriter": ("text",),
    "reviewer": ("text_reviewed", "score"),
    "visual_creator": ("image_url",),
    "adapter": ("versions",),
    "trend_analyst": ("top_topics",),
    "funnel_agent": ("reply", "intent"),
}


@dataclass
class AgentResult:
    """Результат работы агента в предсказуемой форме.

    confidence — насколько агент уверен (0..1). Низкая уверенность не ошибка,
    но следующий агент должен знать, что опора шаткая.
    """
    agent: str
    data: dict = field(default_factory=dict)
    confidence: float = 1.0
    sources: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    ok: bool = True
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # ── создание ───────────────────────────────────────────────────────────
    @classmethod
    def failed(cls, agent: str, error: str) -> "AgentResult":
        """Явный провал вместо пустого словаря: следующий агент это увидит."""
        return cls(agent=agent, ok=False, error=str(error)[:500], confidence=0.0)

    @classmethod
    def from_raw(cls, agent: str, raw: dict, sources: list | None = None) -> "AgentResult":
        """Оборачивает «сырой» ответ агента, сам проверяя полноту."""
        if not isinstance(raw, dict):
            return cls.failed(agent, f"ожидался словарь, пришло {type(raw).__name__}")

        required = REQUIRED_FIELDS.get(agent, ())
        missing = [f for f in required if not raw.get(f)]
        warnings = []
        confidence = 1.0
        if missing:
            warnings.append("не заполнено: " + ", ".join(missing))
            # Чем больше дыр, тем ниже доверие к результату.
            confidence = round(max(0.1, 1 - len(missing) / (len(required) or 1)), 2)

        # Частично заполненный результат — это НЕ провал: данные передаём дальше
        # вместе с предупреждениями. Провал — когда не заполнено вообще ничего
        # из обязательного (тогда опираться не на что).
        ok = bool(raw) and (not required or len(missing) < len(required))

        return cls(agent=agent, data=raw, confidence=confidence,
                   sources=sources or [], warnings=warnings, ok=ok)

    # ── использование ──────────────────────────────────────────────────────
    def get(self, key: str, default=None):
        return self.data.get(key, default)

    @property
    def reliable(self) -> bool:
        """Можно ли строить на этом дальнейшие решения без оговорок."""
        return self.ok and self.confidence >= 0.7

    def to_dict(self) -> dict:
        return asdict(self)

    def for_prompt(self, limit: int = 3000) -> str:
        """Готовит результат к подстановке в промпт следующего агента.

        Предупреждения передаются вместе с данными: модель не должна выдавать
        неполный вход за полный.
        """
        import json
        head = f"[{self.agent}]"
        if not self.ok:
            return f"{head} ОШИБКА: {self.error}"
        body = json.dumps(self.data, ensure_ascii=False)[:limit]
        parts = [f"{head} {body}"]
        if self.confidence < 1.0:
            parts.append(f"(уверенность {self.confidence})")
        if self.warnings:
            parts.append("ВНИМАНИЕ: " + "; ".join(self.warnings))
        return " ".join(parts)


def handoff(*results: AgentResult, limit: int = 6000) -> str:
    """Склеивает результаты нескольких агентов для передачи следующему.

    Провалившиеся не выбрасываются: следующий агент должен знать, чего не хватает,
    а не гадать, почему данные скудные.
    """
    chunks = [r.for_prompt(limit // max(1, len(results))) for r in results if r]
    return "\n\n".join(chunks)


def weakest(*results: AgentResult) -> AgentResult | None:
    """Самое ненадёжное звено цепочки — на что смотреть при плохом результате."""
    valid = [r for r in results if r]
    return min(valid, key=lambda r: r.confidence) if valid else None
