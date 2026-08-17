"""
Резервная копия доступов: один файл вместо пятнадцати полей заново.

Пока в Render не подключена внешняя база, диск контейнера стирается при каждом
деплое — вместе с ключами. Правильное решение одно: задать `DATABASE_URL`. Но
пока этого не сделано, восстановление должно занимать одно действие, а не вечер.

Копия шифруется **отдельным паролем пользователя**, а не серверным
`NEXUS_SECRET_KEY`: если потерян сервер, потерян и он, и копия оказалась бы
бесполезной ровно тогда, когда нужна. Пароль в файл не попадает — только соль,
по которой из него выводится ключ.
"""
import base64
import json
import os
from datetime import datetime

FORMAT = "nexus-credentials-v1"
ITERATIONS = 200_000          # PBKDF2: столько же, сколько берут для паролей
MIN_PASSWORD = 8


def _key(password: str, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=ITERATIONS)
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


async def export_all(password: str) -> dict:
    """Все сохранённые доступы одним зашифрованным свёртком."""
    if len((password or "").strip()) < MIN_PASSWORD:
        return {"ok": False,
                "error": f"Пароль копии должен быть не короче {MIN_PASSWORD} символов — "
                         f"этим файлом открываются все ваши ключи."}

    from cryptography.fernet import Fernet
    from core import credentials

    values: dict[str, str] = {}
    for field in credentials.FIELDS:
        val = await credentials.get(field.key)
        if val:
            values[field.key] = val

    if not values:
        return {"ok": False, "error": "Сохранять нечего: ни одного доступа не задано."}

    salt = os.urandom(16)
    payload = json.dumps({"values": values,
                          "saved_at": datetime.utcnow().isoformat()},
                         ensure_ascii=False).encode("utf-8")
    blob = Fernet(_key(password, salt)).encrypt(payload)

    return {"ok": True, "count": len(values),
            "file": {"format": FORMAT,
                     "salt": base64.b64encode(salt).decode("ascii"),
                     "data": blob.decode("ascii"),
                     "saved_at": datetime.utcnow().isoformat()}}


async def import_all(file: dict, password: str) -> dict:
    """Восстанавливает доступы из копии. Значения ложатся в базу заново
    зашифрованными серверным ключом — как при обычном сохранении."""
    from cryptography.fernet import Fernet, InvalidToken
    from core import credentials

    if not isinstance(file, dict) or file.get("format") != FORMAT:
        return {"ok": False, "error": "Это не файл резервной копии доступов."}
    try:
        salt = base64.b64decode(file.get("salt", ""))
        blob = (file.get("data") or "").encode("ascii")
        raw = Fernet(_key(password or "", salt)).decrypt(blob)
        values = json.loads(raw.decode("utf-8")).get("values") or {}
    except (InvalidToken, ValueError, TypeError):
        # Разделять «не тот пароль» и «файл побит» не нужно: действие в обоих
        # случаях одно — взять правильный файл и правильный пароль.
        return {"ok": False, "error": "Неверный пароль или повреждённый файл."}

    known = {f.key for f in credentials.FIELDS}
    restored, skipped = [], []
    for key, value in values.items():
        if key in known and value:
            await credentials.set(key, value)
            restored.append(key)
        else:
            skipped.append(key)

    return {"ok": True, "restored": len(restored), "keys": restored,
            "skipped": skipped}
