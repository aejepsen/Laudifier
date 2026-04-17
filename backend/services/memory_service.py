# backend/services/memory_service.py
"""
Mem0 Cloud — Camada de Memória Persistente para o Laudifier.

Usa o serviço gerenciado Mem0 (app.mem0.ai) — sem modelo local, sem RAM duplicada.
Free tier: 10 000 memories + 1 000 retrievals/mês (suficiente para MVP).

Quatro escopos de memória:
  1. Médico (user_id)      — preferências pessoais, estilo de laudo, correções habituais
  2. Paciente (agent_id)   — histórico clínico, exames anteriores, condições conhecidas
  3. Especialidade (app_id)— padrões observados para cada especialidade
  4. Sessão (run_id)       — contexto da sessão atual (temporário)
"""

import os
import functools
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def get_memory():
    """
    Singleton do Mem0 MemoryClient — inicializado uma vez por processo.
    Usa o serviço cloud: sem modelo local, sem RAM extra.
    """
    from mem0 import MemoryClient

    api_key = os.getenv("MEM0_API_KEY", "")
    if not api_key:
        raise ValueError("MEM0_API_KEY não configurada")

    client = MemoryClient(api_key=api_key)
    logger.info("✅ Mem0 Cloud inicializado (MemoryClient)")
    return client


def _safe_results(raw) -> list:
    """Normaliza resultado do Mem0 — MemoryClient retorna lista, Memory retorna dict."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return raw.get("results", [])
    return []


# ── API Pública ───────────────────────────────────────────────────────────────

class LaudifierMemory:
    """
    Wrapper de alto nível do Mem0 Cloud para o domínio médico.

    Escopos:
      user_id   = ID do médico (Supabase)
      agent_id  = ID do paciente (nome ou CPF anonimizado)
      app_id    = especialidade (radiologia, patologia...)
    """

    def __init__(self):
        try:
            self.mem = get_memory()
        except Exception as e:
            logger.warning(f"[Mem0] Não inicializado: {e}")
            self.mem = None

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
        if not self.mem:
            return
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
                        f"{laudo[:2000]}"
                    ),
                },
            ]

            self.mem.add(
                mensagens,
                user_id=medico_id,
                metadata={
                    "especialidade": especialidade,
                    "tipo_geracao":  tipo_geracao,
                    "data":          datetime.now(timezone.utc).isoformat(),
                },
            )

            self.mem.add(
                mensagens,
                app_id=f"especialidade_{especialidade.lower().replace(' ', '_')}",
                metadata={"tipo_geracao": tipo_geracao},
            )

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
        """Aprende com as correções que o médico faz nos laudos."""
        if not self.mem:
            return
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
                    "tipo":          "correcao",
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
        if not self.mem:
            return ""
        try:
            memorias_medico = _safe_results(
                self.mem.search(
                    query=f"{especialidade}: {solicitacao}",
                    user_id=medico_id,
                    limit=limite,
                )
            )
            memorias_esp = _safe_results(
                self.mem.search(
                    query=solicitacao,
                    app_id=f"especialidade_{especialidade.lower().replace(' ', '_')}",
                    limit=3,
                )
            )
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
        """Recupera histórico clínico do paciente de exames anteriores."""
        if not self.mem:
            return ""
        try:
            memorias = _safe_results(
                self.mem.search(
                    query=solicitacao,
                    agent_id=f"paciente_{paciente_id}",
                    limit=limite,
                )
            )
            items = [f"  • {m['memory']}" for m in memorias if m.get("score", 0) > 0.5]
            if not items:
                return ""
            return "HISTÓRICO DO PACIENTE (exames anteriores):\n" + "\n".join(items)
        except Exception as e:
            logger.warning(f"[Mem0] Falha ao buscar histórico do paciente: {e}")
            return ""

    def listar_memorias_medico(self, medico_id: str) -> list[dict]:
        """Lista todas as memórias armazenadas de um médico (para exibir na UI)."""
        if not self.mem:
            return []
        try:
            return _safe_results(self.mem.get_all(user_id=medico_id))
        except Exception as e:
            logger.warning(f"[Mem0] Falha ao listar memórias: {e}")
            return []

    def deletar_memoria(self, memory_id: str):
        """Remove uma memória específica."""
        if not self.mem:
            return
        try:
            self.mem.delete(memory_id=memory_id)
        except Exception as e:
            logger.warning(f"[Mem0] Falha ao deletar memória {memory_id}: {e}")

    def limpar_memorias_medico(self, medico_id: str):
        """Remove todas as memórias de um médico (LGPD art. 18, VI)."""
        if not self.mem:
            return
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
