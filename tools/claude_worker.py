#!/usr/bin/env python3
"""
Клод-исполнитель на вашей подписке: забирает задания системы и отвечает сам.

Зачем: подписку claude.ai нельзя подключить к серверу как API — она привязана к
вашему входу в приложение, а не к машине. Но можно наоборот: Claude Code,
запущенный под вашим аккаунтом, сам ходит в систему за заданиями. Оплата API не
нужна, ручная пересылка вопросов в чат — тоже.

Запуск (там, где установлен и залогинен Claude Code):

    export NEXUS_URL=https://nexus-ai-emog.onrender.com
    export NEXUS_TOKEN=...            # или NEXUS_PASSWORD=<пароль админа>
    python tools/claude_worker.py

Пока воркер работает, система складывает вопросы в очередь и получает ответы за
секунды. Останавливаете — система возвращается к автономному режиму и никого не
дёргает.
"""
import json
import os
import subprocess
import sys
import time
from urllib import error, request

URL = os.getenv("NEXUS_URL", "").rstrip("/")
TOKEN = os.getenv("NEXUS_TOKEN", "")
PASSWORD = os.getenv("NEXUS_PASSWORD", "")
CLAUDE = os.getenv("CLAUDE_BIN", "claude")
IDLE_SLEEP = 15          # пусто в очереди — столько ждём до следующего захода
BUSY_SLEEP = 2           # задание взято — сразу за следующим


def api(path: str, payload: dict | None = None, method: str = "") -> dict:
    """Запрос к системе. Ошибку сети не считаем фатальной: воркер живёт долго."""
    req = request.Request(
        f"{URL}{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        method=method or ("POST" if payload is not None else "GET"),
    )
    try:
        with request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.read()[:200].decode('utf-8', 'ignore')}"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def login() -> str:
    """Токен по паролю администратора — чтобы не хранить его в переменных."""
    body = json.dumps({"password": PASSWORD}).encode()
    req = request.Request(f"{URL}/api/auth/login", data=body,
                          headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())["token"]


def ask_claude(prompt: str) -> str:
    """Вопрос локальному Claude Code. Это ваша подписка, ключ API не нужен."""
    out = subprocess.run([CLAUDE, "-p", prompt], capture_output=True, text=True,
                         timeout=600)
    if out.returncode != 0:
        raise RuntimeError((out.stderr or "claude завершился с ошибкой")[:300])
    return out.stdout.strip()


def main() -> int:
    global TOKEN

    if not URL:
        print("Задайте NEXUS_URL — адрес вашей системы", file=sys.stderr)
        return 2
    if not TOKEN and PASSWORD:
        TOKEN = login()
    if not TOKEN:
        print("Задайте NEXUS_TOKEN или NEXUS_PASSWORD", file=sys.stderr)
        return 2

    print(f"Клод-исполнитель на связи: {URL}")
    last_beat = 0.0

    while True:
        # Отметка «я на связи»: система наполняет очередь, только если есть кому
        # её разбирать. Иначе она идёт автономным путём и никого не ждёт.
        if time.time() - last_beat > 60:
            api("/api/production/worker/beat", {})
            last_beat = time.time()

        job = api("/api/production/next").get("job")
        if not job:
            time.sleep(IDLE_SLEEP)
            continue

        job_id = job["id"]
        brief = job.get("brief") or {}
        prompt = brief.get("prompt") or json.dumps(brief, ensure_ascii=False)
        system = brief.get("system") or ""
        print(f"→ задание {job_id[:8]}: {prompt[:80]}")

        try:
            answer = ask_claude(f"{system}\n\n{prompt}" if system else prompt)
            res = api(f"/api/production/{job_id}/result", {"text": answer})
            print(f"← ответ отправлен ({len(answer)} символов), {res.get('next', '')}")
        except Exception as e:
            api(f"/api/production/{job_id}/fail", {"error": str(e)[:300]})
            print(f"× не смог: {e}", file=sys.stderr)

        time.sleep(BUSY_SLEEP)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nОстановлен. Система вернулась в автономный режим.")
