# backend/api/routes/auth.py
"""Endpoints de autenticação."""
import os

from fastapi import APIRouter, Request
from supabase import create_client

from .._shared import limiter
from ..models import LoginRequest

router = APIRouter()


@router.post("/auth/token")
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest):
    """Login via email/senha. Credenciais no body, nunca na URL."""
    sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_ANON_KEY"))
    r  = sb.auth.sign_in_with_password({"email": body.email, "password": body.password})
    return {"access_token": r.session.access_token, "user_id": r.user.id}
