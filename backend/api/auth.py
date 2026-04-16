# backend/api/auth.py
import os
from dataclasses import dataclass, field
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from supabase import create_client

JWT_SECRET   = os.getenv("JWT_SECRET")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
security     = HTTPBearer()


@dataclass
class UserContext:
    id:           str
    email:        str
    display_name: str
    crm:          str   = ""
    role:         str   = "medico"   # medico | admin
    especialidade: str  = ""


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> UserContext:
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token, JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        user_id = payload.get("sub")
        email   = payload.get("email", "")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token inválido")

        # Busca perfil no Supabase
        sb = create_client(SUPABASE_URL, SUPABASE_KEY)
        r  = sb.table("user_profiles").select("*").eq("user_id", user_id).single().execute()
        p  = r.data or {}

        return UserContext(
            id=user_id, email=email,
            display_name=p.get("display_name", email.split("@")[0]),
            crm=p.get("crm", ""),
            role=p.get("role", "medico"),
            especialidade=p.get("especialidade", ""),
        )
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Token inválido: {e}")
