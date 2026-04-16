# 🏥 Laudifier — Gerador de Laudos Médicos com IA

> Gerador de laudos médicos com reconhecimento de voz, RAG sobre repositório de laudos reais e fallback para conhecimento clínico do Claude. Exportação em PDF e DOCX. Stack 100% gratuita para portfolio.

---

## 📋 Índice

- [Visão Geral](#visão-geral)
- [Como Funciona](#como-funciona)
- [Arquitetura](#arquitetura)
- [Stack Tecnológica](#stack-tecnológica)
- [Bancos de Dados](#bancos-de-dados)
- [Reconhecimento de Voz](#reconhecimento-de-voz)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Pré-requisitos](#pré-requisitos)
- [Setup Local](#setup-local)
- [Variáveis de Ambiente](#variáveis-de-ambiente)
- [Ingestão do Repositório](#ingestão-do-repositório)
- [API Reference](#api-reference)
- [Deploy em Produção](#deploy-em-produção)
- [Custo Estimado](#custo-estimado)

---

## Visão Geral

O Laudifier combina três abordagens para gerar laudos médicos de qualidade:

- **RAG (Retrieval-Augmented Generation):** busca laudos similares em repositório vetorial (Qdrant) e usa como referência estrutural
- **Fallback inteligente:** quando o repositório não tem referências relevantes, o Claude usa conhecimento clínico base
- **Entrada por voz:** médico dita os achados usando microfone (Web Speech API nativa PT-BR, sem custo)
- **Aprendizado contínuo:** laudos aprovados são re-indexados automaticamente, enriquecendo o repositório

---

## Como Funciona

```
1. Médico seleciona especialidade
         │
2. Dita achados via microfone (Web Speech API PT-BR)
   ou digita diretamente
         │
3. Backend recebe a solicitação
         │
4. Qdrant busca laudos similares no repositório
         │
         ├── Score >= 0.60 ──> [RAG]
         │                    Usa laudos de referência como base estrutural
         │                    Claude adapta ao caso atual
         │
         └── Score < 0.60  ──> [Fallback]
                              Claude gera do zero com conhecimento clínico
                              Sinaliza ao médico que não há referência
         │
5. Laudo gerado via streaming (token a token)
         │
6. Médico revisa, edita se necessário
         │
7. Aprova ──> laudo re-indexado no Qdrant (melhora futuras gerações)
   ou
   Rejeita ──> registra correções para análise
         │
8. Exporta em PDF ou DOCX
```

### Estratégia RAG vs Fallback

| Situação | Estratégia | Indicador na UI |
|---|---|---|
| Score >= 0.60 | RAG — usa referência do repositório | Baseado no Repositório |
| Score < 0.60 | Fallback — conhecimento clínico Claude | Conhecimento Claude |

---

## Arquitetura

```
FRONTEND Angular 17          BACKEND FastAPI + LangGraph
┌────────────────────┐       ┌───────────────────────────────────┐
│ Gerar Laudo + Voz  │──────>│ POST /laudos/gerar (SSE)          │
│ Histórico          │       │   LaudoAgent (LangGraph)           │
│ Repositório        │       │   ├─ SearchAgent → Qdrant          │
│ Dashboard          │       │   └─ Claude (streaming)            │
└────────────────────┘       │ POST /repositorio/upload           │
                             │   Pipeline de Ingestão             │
                             │   ├─ Whisper (transcrição voz)     │
                             │   ├─ Claude Haiku (metadados)      │
                             │   └─ Qdrant (indexação HNSW)       │
                             └───────────────────────────────────┘
                                          │
              ┌───────────────────────────┼──────────────────┐
              │                           │                  │
         ┌────▼────┐               ┌──────▼─────┐     ┌──────▼──┐
         │ Qdrant  │               │  Supabase  │     │Langfuse │
         │ HNSW    │               │ Postgres   │     │ Traces  │
         │ Laudos  │               │  + Auth    │     │ Scores  │
         └─────────┘               └────────────┘     └─────────┘
```

---

## Stack Tecnológica

| Camada | Tecnologia | Motivo |
|---|---|---|
| Frontend | Angular 17 standalone | Signals, lazy loading |
| Voz STT | Web Speech API nativa | PT-BR, zero custo, zero latência |
| Voz TTS | SpeechSynthesis API nativa | Leitura do laudo para revisão |
| Voz Fallback | Whisper (server-side) | Browsers sem Web Speech API |
| Backend | FastAPI | Async nativo, SSE streaming |
| Orquestração | LangGraph | Grafo de agentes com estado |
| LLM Principal | Claude Sonnet 4.6 | Laudos de alta qualidade |
| LLM Metadados | Claude Haiku 4.5 | Extração de metadados (barato) |
| Vector DB | Qdrant | HNSW + payload indexes, open source |
| Embeddings | text-embedding-3-large | 3072 dimensões, alto recall |
| Banco Relacional | Supabase Postgres | Free tier, RLS, Auth integrada |
| Auth | Supabase Auth | JWT, email/senha, OAuth |
| Export PDF | ReportLab | Geração de PDF formatado |
| Export DOCX | python-docx | Documento Word editável |
| Observabilidade | Langfuse | Traces de LLM, scores |
| Deploy Frontend | Vercel | Free tier, CI/CD automático |
| Deploy Backend | Fly.io | 3 VMs grátis, sem cold start |

---

## Bancos de Dados

### 1. Qdrant — Vector DB (Repositório de Laudos)

Armazena laudos de referência como vetores. Núcleo do sistema RAG.

**Coleção:** `laudos_medicos`

**Schema de cada documento:**
```json
{
  "id": "uuid",
  "content": "texto completo do laudo ou seção",
  "source_name": "laudo_rx_torax_001.pdf",
  "especialidade": "radiologia",
  "tipo_laudo": "rx_torax",
  "aprovado": true,
  "vector": [0.023, -0.145, ...]   // 3072 dimensões
}
```

**Índices criados:**
```python
# Índices de payload para filtros rápidos
"especialidade"  → keyword index  # filtra por radiologia, patologia...
"tipo_laudo"     → keyword index  # filtra por rx_torax, tc_abdome...
"source_name"    → keyword index
"modalidade"     → keyword index
```

**Índice vetorial:** HNSW automático em todos os campos vetoriais.

**Por que Qdrant?**
- Free tier 1GB para sempre no Qdrant Cloud
- Roda localmente via Docker (dev sem custo)
- Busca híbrida (vetorial + esparsa) nativa
- Payload indexes executados dentro do índice (pré-filtragem eficiente)

### 2. Supabase Postgres — Dados Relacionais

**Tabelas:**

```sql
-- Perfis dos médicos
user_profiles (
    user_id       UUID -> auth.users,
    display_name  TEXT,
    crm           TEXT,           -- "12345/SP"
    especialidade TEXT,
    role          TEXT            -- 'medico' | 'admin'
)

-- Laudos gerados
laudos (
    user_id       UUID -> auth.users,
    especialidade TEXT,
    solicitacao   TEXT,           -- o que o médico descreveu
    laudo         TEXT,           -- laudo gerado pela IA
    laudo_editado TEXT,           -- versão editada pelo médico
    tipo_geracao  TEXT,           -- 'rag' ou 'fallback'
    laudos_ref    JSONB,          -- referências usadas do Qdrant
    aprovado      BOOLEAN,        -- feedback do médico
    correcoes     TEXT            -- anotações de ajuste
)
```

Row Level Security (RLS) habilitado — cada médico acessa apenas seus laudos.

---

## Reconhecimento de Voz

### STT — Ditado dos achados

```
Médico clica Ditar
      │
      ↓
Browser → SpeechRecognition API (PT-BR)
      │   interim results: sim (mostra texto em tempo real)
      ↓
Texto reconhecido → preenchido no campo de solicitação
      │
      ↓
Médico clica Gerar Laudo
```

**Suporte por browser:**

| Browser | Suporte |
|---|---|
| Chrome 33+ | Completo (recomendado) |
| Edge 79+ | Completo |
| Safari 14.1+ | Parcial (sem interim results) |
| Firefox | Usa fallback Whisper |

**Fallback Whisper** quando o browser não suporta:
```
MediaRecorder → grava 10s → POST /laudos/transcrever → Whisper 'small' → texto
```

**Modelo Whisper recomendado:** `small` — melhor equilíbrio para termos médicos em PT-BR (~500MB RAM).

### TTS — Leitura do laudo

Médico clica **Ouvir** para revisar o laudo gerado pelo áudio:
- SpeechSynthesis API nativa
- Voz PT-BR local quando disponível
- Velocidade 0.85x (mais pausado para termos médicos)
- Markdown removido antes da leitura

---

## Estrutura do Projeto

```
laudifier/
├── backend/
│   ├── api/
│   │   ├── main.py               # Endpoints REST + SSE streaming
│   │   └── auth.py               # JWT Supabase
│   ├── agents/
│   │   ├── laudo_agent.py        # Orquestrador RAG + fallback + streaming
│   │   └── search_agent.py       # Busca vetorial Qdrant com filtros
│   ├── services/
│   │   └── laudo_service.py      # Persistência + export PDF/DOCX/TXT
│   ├── prompts/
│   │   └── system_prompt.txt     # Prompt médico versionado
│   ├── tests/
│   │   └── test_laudo.py         # Testes pytest
│   ├── Dockerfile                # Build para Fly.io (inclui Whisper)
│   ├── fly.toml                  # Config deploy Fly.io
│   └── requirements.txt
├── pipeline/
│   └── run_pipeline.py           # Ingere PDFs/DOCX de laudos no Qdrant
├── src/
│   ├── app/
│   │   ├── app.component.ts
│   │   ├── app.config.ts         # Bootstrap + interceptor JWT
│   │   ├── app.routes.ts         # Rotas lazy com AuthGuard
│   │   ├── core/
│   │   │   ├── auth/
│   │   │   │   ├── auth.service.ts  # Supabase Auth
│   │   │   │   └── auth.guard.ts
│   │   │   └── services/
│   │   │       ├── laudo.service.ts    # Client SSE + REST
│   │   │       └── voice.service.ts    # Web Speech + Whisper fallback
│   │   ├── laudos/
│   │   │   ├── gerar-laudo.component.ts    # Tela principal + voz
│   │   │   ├── gerar-laudo.component.scss
│   │   │   └── visualizar-laudo.component.ts
│   │   ├── historico/historico.component.ts
│   │   ├── repositorio/repositorio.component.ts
│   │   ├── dashboard/dashboard.component.ts
│   │   ├── login/login.component.ts
│   │   └── shell/shell.component.ts
│   ├── environments/environment.example.ts
│   ├── index.html
│   ├── main.ts
│   └── styles.scss               # Tokens Fluent UI Light/Dark
├── .env.example
├── docker-compose.yml            # Qdrant local para dev
├── package.json
├── vercel.json
└── .github/workflows/deploy.yml  # CI/CD Vercel + Fly.io
```

---

## Pré-requisitos

- Node.js 20+
- Python 3.11+
- Docker (para Qdrant local)
- ffmpeg: `sudo apt install ffmpeg` ou `brew install ffmpeg`
- Contas gratuitas: Anthropic, OpenAI, Supabase, Qdrant Cloud

---

## Setup Local

### 1. Instale e configure

```bash
git clone https://github.com/seu-usuario/laudifier
cd laudifier
npm install
pip install -r backend/requirements.txt
cp .env.example .env
# Edite .env com suas chaves
```

### 2. Schema Supabase

No SQL Editor do Supabase:

```sql
CREATE TABLE user_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE UNIQUE,
    display_name TEXT, crm TEXT, especialidade TEXT,
    role TEXT DEFAULT 'medico', created_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users_own_profile" ON user_profiles
    FOR ALL USING (auth.uid() = user_id);

CREATE TABLE laudos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    especialidade TEXT NOT NULL, tipo_laudo TEXT, solicitacao TEXT,
    laudo TEXT NOT NULL, laudo_editado TEXT, tipo_geracao TEXT,
    laudos_ref JSONB DEFAULT '[]', aprovado BOOLEAN, correcoes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE laudos ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users_own_laudos" ON laudos
    FOR ALL USING (auth.uid() = user_id);
CREATE INDEX idx_laudos_user ON laudos(user_id, created_at DESC);
CREATE INDEX idx_laudos_esp  ON laudos(especialidade);
```

### 3. Qdrant local e coleção

```bash
docker compose up -d qdrant
npm run setup:qdrant
# Saída: "Coleção 'laudos_medicos' criada no Qdrant"
```

### 4. Ingira laudos de referência

```bash
python pipeline/run_pipeline.py --dir ./laudos-referencia/ --especialidade radiologia
python pipeline/run_pipeline.py --file laudo.pdf --especialidade patologia --tipo histopatologia
```

### 5. Rode

```bash
# Backend
npm run backend        # http://localhost:8000
#                        docs: http://localhost:8000/docs

# Frontend
cp src/environments/environment.example.ts src/environments/environment.ts
# Edite supabaseUrl, supabaseKey, apiUrl
npm start              # http://localhost:4200
```

---

## Variáveis de Ambiente

| Variável | Obrigatória | Descrição |
|---|---|---|
| `ANTHROPIC_API_KEY` | Sim | Chave API Claude |
| `ANTHROPIC_MODEL` | Não | Default: `claude-sonnet-4-6` |
| `OPENAI_API_KEY` | Sim | Embeddings |
| `QDRANT_URL` | Sim | URL Qdrant (local ou cloud) |
| `QDRANT_API_KEY` | Não | Vazio para local |
| `QDRANT_COLLECTION` | Não | Default: `laudos_medicos` |
| `SUPABASE_URL` | Sim | URL projeto Supabase |
| `SUPABASE_ANON_KEY` | Sim | Chave pública |
| `SUPABASE_SERVICE_ROLE_KEY` | Sim | Chave backend |
| `JWT_SECRET` | Sim | Segredo JWT Supabase |
| `WHISPER_MODEL` | Não | Default: `small` |
| `LANGFUSE_PUBLIC_KEY` | Não | Observabilidade (opcional) |
| `USE_LOCAL_STORAGE` | Não | `true` para dev sem S3 |
| `CORS_ORIGINS` | Não | Default: `http://localhost:4200` |

---

## API Reference

### `POST /laudos/gerar` — Gera laudo (SSE)

```json
// Request
{
  "solicitacao": "RX tórax PA. Campos pulmonares sem condensações.",
  "especialidade": "Radiologia",
  "dados_clinicos": { "paciente": "João Silva", "idade": "45" }
}

// Stream de eventos SSE
data: {"type": "meta", "tipo_geracao": "rag", "laudos_ref": 3, "score": 0.87}
data: {"type": "token", "text": "## LAUDO DE RADIOLOGIA\n\n"}
...
data: {"type": "done", "campos_faltando": ["NOME DO MÉDICO"], "laudo_id": "uuid"}
```

### `POST /laudos/transcrever` — Whisper fallback

Multipart form com campo `audio` (webm/mp3/wav).
```json
{ "transcript": "RX de tórax PA, campos pulmonares livres..." }
```

### `GET /laudos` — Lista laudos
Query: `page`, `size`, `especialidade`

### `GET /laudos/{id}` — Laudo por ID

### `PUT /laudos/{id}` — Salva edição do médico

### `POST /laudos/{id}/feedback`
```json
{ "laudo_id": "uuid", "aprovado": true, "correcoes": null }
```

### `GET /laudos/{id}/exportar/{formato}`
Formatos: `pdf`, `docx`, `txt`

### `POST /repositorio/upload` — Adiciona referência (admin)
Form: `arquivo`, `especialidade`, `tipo_laudo`

### `GET /dashboard/stats` — Métricas de uso

### `GET /health` — Status dos serviços

---

## Deploy em Produção

### Frontend → Vercel

```bash
npm install -g vercel
vercel deploy --prod
```

### Backend → Fly.io

```bash
cd backend
flyctl launch
flyctl secrets set ANTHROPIC_API_KEY=sk-ant-...
flyctl secrets set OPENAI_API_KEY=sk-...
flyctl secrets set QDRANT_URL=https://cluster.qdrant.io
flyctl secrets set QDRANT_API_KEY=chave
flyctl secrets set SUPABASE_URL=https://projeto.supabase.co
flyctl secrets set SUPABASE_SERVICE_ROLE_KEY=chave
flyctl secrets set JWT_SECRET=chave-longa
flyctl deploy

# Verificação
curl https://laudifier-backend.fly.dev/health
```

---

## Custo Estimado

### Produção — 1 médico, ~20 laudos/mês

| Serviço | Custo |
|---|---|
| Vercel (frontend) | $0 |
| Fly.io (backend 1GB) | $0 |
| Qdrant Cloud (1GB) | $0 |
| Supabase (banco + auth) | $0 |
| Langfuse (observabilidade) | $0 |
| Claude Sonnet 4.6 (~20 laudos) | ~$0.30 |
| OpenAI Embeddings | ~$0.02 |
| **Total** | **~$0.32/mês** |

---

## Testes

```bash
cd backend
pytest tests/ -v
pytest tests/ --cov=api --cov=agents --cov-report=term-missing
```

---

## Licença

MIT — uso livre para portfolio, estudos e projetos pessoais.
