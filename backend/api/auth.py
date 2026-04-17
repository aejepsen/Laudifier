# backend/api/auth.py
import os
from dataclasses import dataclass
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
security     = HTTPBearer()

_sb_admin = None

def _get_sb_admin():
    global _sb_admin
    if _sb_admin is None:
        _sb_admin = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _sb_admin


@dataclass
class UserContext:
    id:            str
    email:         str
    display_name:  str
    crm:           str  = ""
    role:          str  = "medico"
    especialidade: str  = ""


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> UserContext:
    token = credentials.credentials
    try:
        sb = _get_sb_admin()
        resp = sb.auth.get_user(token)
        user = resp.user
        if not user:
            raise HTTPException(status_code=401, detail="Token inválido")

        user_id = user.id
        email   = user.email or ""

        r = sb.table("user_profiles").select("*").eq("user_id", user_id).single().execute()
        p = r.data or {}

        return UserContext(
            id=user_id, email=email,
            display_name=p.get("display_name", email.split("@")[0]),
            crm=p.get("crm", ""),
            role=p.get("role", "medico"),
            especialidade=p.get("especialidade", ""),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token inválido: {e}")
