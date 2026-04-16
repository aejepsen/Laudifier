# backend/services/memory_service.py
"""
Mem0 — Camada de Memória Persistente para o Laudifier.

O Mem0 aprende automaticamente com cada interação do médico e injeta
contexto relevante nos próximos laudos, sem que o médico precise repetir
preferências ou informações já fornecidas anteriormente.

Quatro escopos de memória:
  1. Médico (user_id)      — preferências pessoais, estilo de laudo, correções habituais
  2. Paciente (agent_id)   — histórico clínico, exames anteriores, condições conhecidas
  3. Especialidade (app_id)— padrões observados para cada especialidade
  4. Sessão (run_id)       — contexto da sessão atual (temporário)

Configuração:
  - LLM:      Claude Haiku 4.5 (extração de fatos — barato e rápido)
  - Embedder: OpenAI text-embedding-3-small (1536 dims — compatível com Mem0)
  - Vector:   Qdrant (mesma instância, coleção separada: 'laudifier_memory')
"""

import os
import functools
import logging
from datetime import datetime, timezone

from mem0 import Memory

logger = logging.getLogger(__name__)

# ── Configuração Mem0 ─────────────────────────────────────────────────────────

def _build_mem0_config() -> dict:
    """
    Configura Mem0 com:
    - Claude Haiku para extração de fatos (barato)
    - OpenAI text-embedding-3-small para vetorizar memórias
    - Qdrant para persistência (mesma instância do projeto)
    """
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_key = os.getenv("QDRANT_API_KEY", "")

    # Config base do Qdrant
    qdrant_config: dict = {
        "collection_name":       "laudifier_memory",
        "embedding_model_dims":  1536,   # text-embedding-3-small
    }

    # Qdrant Cloud usa URL, local usa host/port
    if qdrant_url.startswith("http://localhost") or qdrant_url.startswith("http://qdrant"):
        host, port = qdrant_url.replace("http://", "").split(":")
        qdrant_config["host"] = host
        qdrant_config["port"] = int(port)
    else:
        qdrant_config["url"] = qdrant_url
        if qdrant_key:
            qdrant_config["api_key"] = qdrant_key

    return {
        # Claude Haiku — extração de fatos médicos das conversas
        "llm": {
            "provider": "anthropic",
            "config": {
                "model":       "claude-haiku-4-5-20251001",
                "temperature": 0.1,
                "max_tokens":  2000,
                "api_key":     os.getenv("ANTHROPIC_API_KEY"),
            },
        },
        # OpenAI text-embedding-3-small — vetoriza as memórias
        "embedder": {
            "provider": "openai",
            "config": {
                "model":  "text-embedding-3-small",  # 1536 dims
                "api_key": os.getenv("OPENAI_API_KEY"),
            },
        },
        # Qdrant — persiste as memórias vetorizadas
        "vector_store": {
            "provider": "qdrant",
            "config": qdrant_config,
        },
        # Versão da API Mem0
        "version": "v1.1",
    }


@functools.lru_cache(maxsize=1)
def get_memory() -> Memory:
    """
    Singleton do Mem0 Memory — inicializado uma vez por processo.
    Thread-safe via lru_cache.
    """
    try:
        config = _build_mem0_config()
        mem    = Memory.from_config(config)
        logger.info("✅ Mem0 inicializado — Qdrant collection: laudifier_memory")
        return mem
    except Exception as e:
        logger.error(f"❌ Mem0 falhou ao inicializar: {e}")
        raise


# ── API Pública ───────────────────────────────────────────────────────────────

class LaudifierMemory:
    """
    Wrapper de alto nível do Mem0 para o domínio médico.

    Escopos:
      user_id   = ID do médico (Supabase)
      agent_id  = ID do paciente (nome ou CPF anonimizado)
      app_id    = especialidade (radiologia, patologia...)
      run_id    = ID da sessão atual
    """

    def __init__(self):
        self.mem = get_memory()

    # ── Lembrar ───────────────────────────────────────────────────────────────

    async def memorizar_interacao(
        self,
        medico_id:    str,
        solicitacao:  str,
        laudo:        str,
        especialidade: str,
        tipo_geracao: str,
        paciente_id:  str | None = None,
    ):
        """
        Extrai e persiste fatos relevantes de uma interação de geração de laudo.
        Chamado em background após cada laudo gerado.
        """
        try:
            mensagens = [
                {
                    "role": "user",
                    "content": (
                        f"[SOLICITAÇÃO DE LAUDO — {especialidade.upper()}]\n"
                        f"{solicitacao}"
                    ),
                },
                {
                    "role": "assistant",
                    "content": (
                        f"[LAUDO GERADO — {tipo_geracao.upper()}]\n"
                        f"{laudo[:2000]}"  # limita para não estourar context
                    ),
                },
            ]

            # Memória do médico: preferências, estilo, termos usados
            self.mem.add(
                mensagens,
                user_id=medico_id,
                metadata={
                    "especialidade": especialidade,
                    "tipo_geracao":  tipo_geracao,
                    "data":          datetime.now(timezone.utc).isoformat(),
                },
            )

            # Memória da especialidade: padrões observados
            self.mem.add(
                mensagens,
                app_id=f"especialidade_{especialidade.lower().replace(' ', '_')}",
                metadata={"tipo_geracao": tipo_geracao},
            )

            # Memória do paciente (se identificado)
            if paciente_id:
                self.mem.add(
                    mensagens,
                    agent_id=f"paciente_{paciente_id}",
                    metadata={"especialidade": especialidade},
                )

        except Exception as e:
            logger.warning(f"[Mem0] Falha ao memorizar interação: {e}")

    async def memorizar_correcao(
        self,
        medico_id:      str,
        laudo_original: str,
        laudo_editado:  str,
        especialidade:  str,
    ):
        """
        Aprende com as correções que o médico faz nos laudos.
        Cada correção é uma informação valiosa sobre preferências do médico.
        """
        try:
            diff_context = (
                f"O médico corrigiu este laudo de {especialidade}.\n\n"
                f"ANTES (gerado pela IA):\n{laudo_original[:800]}\n\n"
                f"DEPOIS (corrigido pelo médico):\n{laudo_editado[:800]}"
            )

            self.mem.add(
                [{"role": "user", "content": diff_context}],
                user_id=medico_id,
                metadata={
                    "tipo":         "correcao",
                    "especialidade": especialidade,
                    "data":          datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as e:
            logger.warning(f"[Mem0] Falha ao memorizar correção: {e}")

    # ── Recuperar ─────────────────────────────────────────────────────────────

    def buscar_contexto_medico(
        self,
        medico_id:    str,
        solicitacao:  str,
        especialidade: str,
        limite:       int = 5,
    ) -> str:
        """
        Recupera memórias relevantes do médico para contextualizar a geração.
        Retorna string formatada para injetar no prompt do Claude.
        """
        try:
            # Memórias do médico
            resultado = self.mem.search(
                query=f"{especialidade}: {solicitacao}",
                user_id=medico_id,
                limit=limite,
            )
            memorias_medico = resultado.get("results", [])

            # Padrões da especialidade
            resultado_esp = self.mem.search(
                query=solicitacao,
                app_id=f"especialidade_{especialidade.lower().replace(' ', '_')}",
                limit=3,
            )
            memorias_esp = resultado_esp.get("results", [])

            return _formatar_memorias(memorias_medico, memorias_esp)

        except Exception as e:
            logger.warning(f"[Mem0] Falha ao buscar contexto: {e}")
            return ""

    def buscar_historico_paciente(
        self,
        paciente_id:  str,
        solicitacao:  str,
        limite:       int = 3,
    ) -> str:
        """
        Recupera histórico clínico do paciente de exames anteriores.
        """
        try:
            resultado = self.mem.search(
                query=solicitacao,
                agent_id=f"paciente_{paciente_id}",
                limit=limite,
            )
            memorias = resultado.get("results", [])
            if not memorias:
                return ""

            items = [f"  • {m['memory']}" for m in memorias if m.get("score", 0) > 0.5]
            if not items:
                return ""

            return "HISTÓRICO DO PACIENTE (exames anteriores):\n" + "\n".join(items)

        except Exception as e:
            logger.warning(f"[Mem0] Falha ao buscar histórico do paciente: {e}")
            return ""

    def listar_memorias_medico(self, medico_id: str) -> list[dict]:
        """Lista todas as memórias armazenadas de um médico (para exibir na UI)."""
        try:
            resultado = self.mem.get_all(user_id=medico_id)
            return resultado.get("results", [])
        except Exception as e:
            logger.warning(f"[Mem0] Falha ao listar memórias: {e}")
            return []

    def deletar_memoria(self, memory_id: str):
        """Remove uma memória específica (para o médico gerenciar)."""
        try:
            self.mem.delete(memory_id=memory_id)
        except Exception as e:
            logger.warning(f"[Mem0] Falha ao deletar memória {memory_id}: {e}")

    def limpar_memorias_medico(self, medico_id: str):
        """Remove todas as memórias de um médico (GDPR / privacidade)."""
        try:
            self.mem.delete_all(user_id=medico_id)
            logger.info(f"[Mem0] Memórias do médico {medico_id} removidas")
        except Exception as e:
            logger.warning(f"[Mem0] Falha ao limpar memórias: {e}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _formatar_memorias(
    memorias_medico: list[dict],
    memorias_esp:    list[dict],
) -> str:
    """Formata memórias recuperadas para injeção no prompt do Claude."""
    partes = []

    # Preferências e padrões do médico
    itens_medico = [
        f"  • {m['memory']}"
        for m in memorias_medico
        if m.get("score", 0) > 0.45
    ]
    if itens_medico:
        partes.append(
            "PREFERÊNCIAS E PADRÕES DO MÉDICO (aprendidos de laudos anteriores):\n"
            + "\n".join(itens_medico)
        )

    # Padrões da especialidade
    itens_esp = [
        f"  • {m['memory']}"
        for m in memorias_esp
        if m.get("score", 0) > 0.45
    ]
    if itens_esp:
        partes.append(
            "PADRÕES OBSERVADOS NESTA ESPECIALIDADE:\n"
            + "\n".join(itens_esp)
        )

    return "\n\n".join(partes)
