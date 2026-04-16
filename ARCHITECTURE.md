# Laudifier — Architecture

## O que é

Assistente de IA para radiologistas. O médico descreve o caso clínico em voz ou texto; o agente gera o laudo estruturado com base em laudos reais do Compêndio de Radiologia, com seções TÉCNICA / INDICAÇÃO / ANÁLISE / OPINIÃO.

---

## Stack

### Backend

| Ferramenta | Versão | Por que |
|---|---|---|
| **Python** | 3.11 | Ecossistema AI/ML mais maduro; tipo nativo para async; compatível com todas as libs da stack |
| **FastAPI** | latest | Mais rápido que Flask; OpenAPI nativo; async first; validação Pydantic embutida |
| **LangGraph** | latest | Permite agente com loops controlados (max steps, fallback); mais confiável que LangChain puro para agentes stateful |
| **Claude Sonnet 4.6** | via Anthropic SDK | Melhor relação qualidade/custo para geração de laudos; contexto longo; instrução clínica segue bem |
| **Qdrant** | v1.9.4 | Vector DB self-hosted; sem vendor lock-in; payload filtering nativo (modalidade, região); deploy via Docker |
| **Supabase** | hosted | Auth + Postgres gerenciado; JWT nativo; RLS para isolamento por médico; custo zero no free tier |
| **Mem0** | hosted | Memória persistente entre sessões sem implementar vector store customizado |
| **Whisper** | small | Transcrição de voz offline; modelo `small` balanceia velocidade/precisão para PT-BR clínico; nunca baked na imagem |
| **Langfuse** | hosted | Observabilidade de LLM: traces, custo por geração, latência por etapa |

### Frontend

| Ferramenta | Versão | Por que |
|---|---|---|
| **Angular** | 17 | Usado pela maioria das integrações HIS/PACS hospitalares; TypeScript strict; signals para reatividade |
| **Supabase JS** | ^2.43 | Auth client; session management; sem JWT handling manual |

### Deploy

| Serviço | Target | Por que |
|---|---|---|
| **Fly.io** | Backend | Containers com persistent volumes; regiões próximas ao Brasil; mais barato que Azure Container Apps para escala baixa |
| **Vercel** | Frontend | Deploy automático via GitHub; CDN global; Angular SSR se necessário |
| **Qdrant Cloud** (futuro) | Vector DB | Migração quando volume de laudos escalar além do single-node |

---

## Arquitetura

```
Médico
  │
  ├─ voz (mp3/wav/webm) ──→ Whisper ──→ transcrição
  │
  └─ texto ──────────────────────────────────────────→ FastAPI
                                                           │
                                              LangGraph Agent Loop
                                           ┌──────────────────────┐
                                           │ 1. Classificar caso   │
                                           │ 2. Buscar RAG (Qdrant)│
                                           │ 3. Gerar rascunho     │
                                           │ 4. Revisar / iterar   │
                                           │ 5. Retornar laudo     │
                                           └──────────────────────┘
                                                           │
                                               Mem0 (memória médico)
                                               Langfuse (trace/cost)
                                               Supabase (persist laudo)
```

---

## Estrutura de pastas

```
laudifier/
├── backend/                   # FastAPI + LangGraph
│   ├── api/                   # Rotas HTTP (main.py, routers)
│   ├── agents/                # LangGraph agents e tools
│   ├── services/              # Lógica de domínio (whisper, qdrant, mem0)
│   ├── prompts/               # Templates de prompt (fora do código)
│   ├── tests/                 # Testes unitários e integração
│   ├── Dockerfile             # Multi-stage, non-root, sem Whisper baked
│   ├── .dockerignore          # Exclui .env, __pycache__, tests, storage
│   ├── .env.example           # Todas as variáveis com placeholders
│   └── requirements.txt
│
├── pipeline/                  # ETL de laudos (scraper → processor → ingestão)
│   └── run_pipeline.py
│
├── src/                       # Angular 17 frontend
│   └── app/
│
├── docker-compose.yml         # Base: produção (sem source mounts, versões fixas)
├── docker-compose.override.yml # Dev: source mounts + --reload
├── Dockerfile                 # Frontend: Angular build → nginx, non-root
├── nginx.conf                 # SPA routing + security headers
├── .dockerignore              # Frontend: exclui node_modules, .angular, backend
├── .gitignore                 # Global: .env, storage, caches
└── ARCHITECTURE.md
```

---

## Segurança

| Decisão | Razão |
|---|---|
| Multi-stage Dockerfile backend | gcc/libffi apenas no builder; imagem final ~150MB sem dev tools |
| Non-root user (`app`) no container | Container comprometido não tem root no host |
| Whisper carrega de volume, nunca baked | Evita 460MB na imagem; modelo atualizado sem rebuild |
| `.dockerignore` em cada serviço | `.env` jamais entra nas layers da imagem |
| `docker-compose.yml` sem source mounts | Prod usa código da imagem; source mount só em `override.yml` |
| CORS via env var `CORS_ORIGINS` | Nunca `*`; nunca hardcoded localhost em produção |
| JWT via Supabase + RLS | Isolamento por médico na camada de banco; sem bypass possível |

---

## Como rodar

```bash
# 1. Clone e configure
cp backend/.env.example .env
# Edite .env com suas chaves reais

# 2. Suba infra (dev — com hot reload)
docker compose up -d          # aplica override.yml automaticamente

# 3. Frontend (dev local sem Docker)
npm install
npm start                     # http://localhost:4200

# 4. Backend direto (alternativa ao Docker)
cd backend && uvicorn api.main:app --reload --port 8000
```

### Portas

| Serviço | Porta |
|---|---|
| Frontend (ng serve) | 4200 |
| Backend API | 8000 |
| Qdrant HTTP | 6333 |

---

## Estimativa de custo por laudo gerado

| Operação | Custo estimado |
|---|---|
| Claude Sonnet 4.6 (~3k tokens entrada, ~800 saída) | ~$0.012 |
| Qdrant search (self-hosted) | $0 |
| Mem0 (free tier: 1000 ops/mês) | $0 / $0.002+ |
| Whisper (self-hosted) | $0 |
| **Total por laudo** | **~$0.01–0.02** |
