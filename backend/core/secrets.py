"""
Шифрование сохранённых доступов.

Ключи площадок и AI-провайдеров лежат в таблице `Connection`. Пока они хранились
открытым текстом, любой, кто получил дамп базы (бэкап, чужой доступ к хостингу),
получал вместе с ним рабочие токены Instagram и бота. Теперь значение шифруется
Fernet-ключом, выведенным из переменной окружения `NEXUS_SECRET_KEY`.

Принцип совместимости: шифрование — не обязательное условие работы.
  * ключа в окружении нет  → пишем и читаем как раньше, открытым текстом,
    и честно говорим об этом в интерфейсе, а не делаем вид, что всё защищено;
  * ключ появился          → новые записи шифруются, старые перешифровываются
    один раз на старте;
  * ключ пропал, а записи зашифрованы → значение недоступно. Мы не роняем сервер
    и не притворяемся, что ключа нет: возвращаем None и говорим, что нужно
    вернуть NEXUS_SECRET_KEY.
"""
import base64
import hashlib
import os

_PREFIX = "enc:v1:"          # метка формата прямо в значении — видно, что зашифровано


def key_material() -> str:
    return (os.getenv("NEXUS_SECRET_KEY", "") or "").strip()


def enabled() -> bool:
    """Есть ли чем шифровать. Пустой ключ — это выключенное шифрование."""
    return bool(key_material())


def _fernet():
    """Fernet требует 32 байта в base64; пользователь задаёт произвольную строку."""
    from cryptography.fernet import Fernet
    digest = hashlib.sha256(key_material().encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def is_encrypted(value: str) -> bool:
    return bool(value) and value.startswith(_PREFIX)


def encrypt(value: str) -> str:
    """Шифрует значение. Без ключа возвращает его как есть — вызывающему коду
    не нужно каждый раз спрашивать, включено ли шифрование."""
    if not value or not enabled() or is_encrypted(value):
        return value
    return _PREFIX + _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt(value: str) -> str | None:
    """Расшифровывает значение. None — значение зашифровано, а прочитать нечем
    (ключ не задан или задан другой): это не то же самое, что «ключа нет»."""
    if not value:
        return value
    if not is_encrypted(value):
        return value
    if not enabled():
        return None
    try:
        from cryptography.fernet import InvalidToken
        try:
            return _fernet().decrypt(value[len(_PREFIX):].encode("ascii")).decode("utf-8")
        except InvalidToken:
            return None
    except Exception:
        return None


def status(values: list[str] | None = None) -> dict:
    """Сводка для интерфейса: включено ли шифрование и сколько записей защищено."""
    values = values or []
    encrypted = sum(1 for v in values if is_encrypted(v))
    return {"enabled": enabled(), "encrypted": encrypted,
            "plaintext": len([v for v in values if v]) - encrypted,
            "hint": "" if enabled() else
                    ("Задайте переменную окружения NEXUS_SECRET_KEY — тогда ключи "
                     "будут храниться в базе в зашифрованном виде.")}
