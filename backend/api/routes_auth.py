import os
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from core.auth import make_token, check_rate

router = APIRouter(tags=["auth"])

class LoginBody(BaseModel):
    password: str

@router.post("/api/auth/login")
async def login(body: LoginBody, request: Request):
    ip = request.client.host if request.client else "unknown"
    check_rate(f"login:{ip}")
    expected = os.getenv("ADMIN_PASSWORD", "nexus-change-me")
    if body.password != expected:
        raise HTTPException(status_code=401, detail="Неверный пароль")
    return {"token": make_token()}

@router.get("/api/health")
async def health():
    return {"status": "ok"}
