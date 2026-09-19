import os
import hmac
import hashlib
import time
from collections import defaultdict
from fastapi import HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

_bearer = HTTPBearer(auto_error=False)

# --- token ---

def _secret() -> bytes:
    return os.getenv("ADMIN_PASSWORD", "nexus-change-me").encode()

# Сколько живёт вход. Раньше метка считалась по часу и принималась только
# текущая и предыдущая — то есть через час-два работы дашборд выкидывал на
# экран пароля посреди дела, и это выглядело как «панель не грузится».
# Владелец у системы один, вход только по его паролю, поэтому сутки как шаг и
# неделя как срок — разумная плата за то, чтобы не вводить пароль каждый час.
_BUCKET = 86400
_DAYS_VALID = 7


def make_token() -> str:
    payload = f"nexus:{int(time.time() // _BUCKET)}"
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"

def verify_token(token: str) -> bool:
    try:
        prefix, sig = token.rsplit(".", 1)
        # Принимаем сегодняшнюю метку и несколько предыдущих: смена пароля
        # по-прежнему обрывает все входы сразу, потому что подпись считается им.
        now = int(time.time() // _BUCKET)
        for ts in range(now, now - _DAYS_VALID, -1):
            expected_payload = f"nexus:{ts}"
            expected_sig = hmac.new(_secret(), expected_payload.encode(), hashlib.sha256).hexdigest()
            if hmac.compare_digest(sig, expected_sig) and prefix == expected_payload:
                return True
        return False
    except Exception:
        return False

async def require_auth(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
):
    # skip auth for login endpoint
    if request.url.path in ("/api/auth/login", "/api/health"):
        return
    if not creds or not verify_token(creds.credentials):
        raise HTTPException(status_code=401, detail="Unauthorized")

# --- rate limiting ---

_rate: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT = 60       # requests
RATE_WINDOW = 60.0    # seconds

def check_rate(ip: str):
    now = time.time()
    hits = _rate[ip]
    _rate[ip] = [t for t in hits if now - t < RATE_WINDOW]
    if len(_rate[ip]) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many requests")
    _rate[ip].append(now)
