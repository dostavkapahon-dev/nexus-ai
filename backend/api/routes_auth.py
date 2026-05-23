import os
import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from core.auth import make_token, check_rate

router = APIRouter(tags=["auth"])

ALLOWED_EMAILS_ENV = "ALLOWED_EMAILS"  # comma-separated list, empty = allow all

def _is_allowed(email: str) -> bool:
    allowed = os.getenv(ALLOWED_EMAILS_ENV, "")
    if not allowed:
        return True
    return email.lower() in [e.strip().lower() for e in allowed.split(",")]

class LoginBody(BaseModel):
    password: str

class GoogleLoginBody(BaseModel):
    credential: str  # Google ID token from frontend

@router.post("/api/auth/login")
async def login(body: LoginBody, request: Request):
    ip = request.client.host if request.client else "unknown"
    check_rate(f"login:{ip}")
    expected = os.getenv("ADMIN_PASSWORD", "nexus-change-me")
    if body.password != expected:
        raise HTTPException(status_code=401, detail="Неверный пароль")
    return {"token": make_token(), "method": "password"}

@router.post("/api/auth/google")
async def google_login(body: GoogleLoginBody, request: Request):
    """Verify Google ID token and issue NEXUS token."""
    ip = request.client.host if request.client else "unknown"
    check_rate(f"login:{ip}")

    # Verify token with Google
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": body.credential}
            )
            info = r.json()
    except Exception:
        raise HTTPException(status_code=401, detail="Не удалось проверить Google токен")

    if "error" in info or not info.get("email_verified"):
        raise HTTPException(status_code=401, detail="Google токен недействителен")

    email = info.get("email", "")
    if not _is_allowed(email):
        raise HTTPException(status_code=403, detail=f"Email {email} не в списке разрешённых")

    return {
        "token": make_token(),
        "method": "google",
        "email": email,
        "name": info.get("name", ""),
        "picture": info.get("picture", "")
    }

@router.get("/api/auth/google-client-id")
async def google_client_id():
    """Frontend fetches this to init Google sign-in button."""
    cid = os.getenv("GOOGLE_CLIENT_ID", "")
    return {"client_id": cid, "enabled": bool(cid)}

@router.get("/api/health")
async def health():
    return {"status": "ok"}