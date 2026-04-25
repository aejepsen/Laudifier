# backend/api/models.py
"""Pydantic models partilhados entre rotas."""
from typing import Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email:    str
    password: str


class LaudoRequest(BaseModel):
    solicitacao:    str  = Field(..., max_length=5000)
    especialidade:  str  = Field(..., max_length=100)
    dados_clinicos: dict = Field(default={})
    laudo_id:       Optional[str] = None


class FeedbackRequest(BaseModel):
    aprovado:  bool
    correcoes: Optional[str] = Field(default=None, max_length=2000)


class CorrecaoRequest(BaseModel):
    achados:     str           = Field(..., max_length=10000)
    laudo_atual: Optional[str] = Field(None, max_length=100000)


class ConclusaoRequest(BaseModel):
    dados_paciente: dict = Field(default={})


class TranscricaoRequest(BaseModel):
    audio_base64: str
