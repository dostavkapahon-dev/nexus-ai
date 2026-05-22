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

def make_token() -> str:
    payload = f"nexus:{int(time.time() // 3600)}"  # rotates every hour
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"

def verify_token(token: str) -> bool:
    try:
        prefix, sig = token.rsplit(".", 1)
        # accept current hour and previous hour
        for ts in [int(time.time() // 3600), int(time.time() // 3600) - 1]:
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
