# ─── Infra ────────────────────────────────────────────────────────────────────

variable "environment" {
  type        = string
  description = "Ambiente de deploy: production | staging"
  default     = "production"
  validation {
    condition     = contains(["production", "staging"], var.environment)
    error_message = "environment deve ser 'production' ou 'staging'."
  }
}

variable "location" {
  type        = string
  description = "Região Azure (ex: brazilsouth, eastus)"
  default     = "eastus2"
}

variable "app_name" {
  type        = string
  description = "Nome base da aplicação — usado nos resource names"
  default     = "laudifier"
  validation {
    condition     = can(regex("^[a-z0-9-]{3,20}$", var.app_name))
    error_message = "app_name deve conter apenas letras minúsculas, números e hífens (3-20 chars)."
  }
}

# ─── Container App ────────────────────────────────────────────────────────────

variable "backend_cpu" {
  type        = number
  description = "CPU alocada para o Container App (0.25 | 0.5 | 0.75 | 1.0 | 1.25 | 1.5 | 1.75 | 2.0)"
  default     = 1.0
}

variable "backend_memory" {
  type        = string
  description = "Memória alocada para o Container App (ex: '2Gi')"
  default     = "2Gi"
}

variable "backend_min_replicas" {
  type        = number
  description = "Réplicas mínimas (0 = scale-to-zero)"
  default     = 1
  validation {
    condition     = var.backend_min_replicas >= 0 && var.backend_min_replicas <= 10
    error_message = "backend_min_replicas deve estar entre 0 e 10."
  }
}

variable "backend_max_replicas" {
  type        = number
  description = "Réplicas máximas"
  default     = 3
  validation {
    condition     = var.backend_max_replicas >= 1 && var.backend_max_replicas <= 10
    error_message = "backend_max_replicas deve estar entre 1 e 10."
  }
}

variable "whisper_share_quota_gb" {
  type        = number
  description = "Quota em GB do Azure Files share para modelos Whisper"
  default     = 10
  validation {
    condition     = var.whisper_share_quota_gb >= 5
    error_message = "whisper_share_quota_gb deve ser >= 5 (modelo 'small' ocupa ~244MB, 'medium' ~1.5GB)."
  }
}

variable "cors_origins" {
  type        = string
  description = "Origens permitidas no CORS — URL do Static Web App (disponível após primeiro apply)"
  default     = "https://laudifier.azurestaticapps.net"
}

# ─── Docker Hub ───────────────────────────────────────────────────────────────
# 1 repo privado grátis, sem limite de pulls autenticados.
# Alternativa gratuita ao ACR (~R$29/mês) e ao ghcr.io (500MB limit no plano free privado).
# Pré-requisito: conta Docker Hub + Access Token (Hub > Account Settings > Security).

variable "dockerhub_username" {
  type        = string
  description = "Username do Docker Hub"
}

variable "dockerhub_token" {
  type        = string
  sensitive   = true
  description = "Docker Hub Access Token (read/write) — nunca usar senha da conta"
}


# ─── Secrets — AI ─────────────────────────────────────────────────────────────

variable "anthropic_api_key" {
  type        = string
  description = "Anthropic API key (sk-ant-api03-...)"
  sensitive   = true
  validation {
    condition     = startswith(var.anthropic_api_key, "sk-ant-")
    error_message = "anthropic_api_key deve começar com 'sk-ant-'."
  }
}

# ─── Secrets — Auth ───────────────────────────────────────────────────────────

variable "supabase_url" {
  type        = string
  description = "URL do projeto Supabase (https://xxx.supabase.co)"
  validation {
    condition     = startswith(var.supabase_url, "https://")
    error_message = "supabase_url deve começar com 'https://'."
  }
}

variable "supabase_anon_key" {
  type      = string
  sensitive = true
}

variable "supabase_service_role_key" {
  type      = string
  sensitive = true
}

variable "jwt_secret" {
  type        = string
  sensitive   = true
  description = "Secret JWT — mínimo 32 caracteres"
  validation {
    condition     = length(var.jwt_secret) >= 32
    error_message = "jwt_secret deve ter no mínimo 32 caracteres."
  }
}

# ─── Secrets — Qdrant ─────────────────────────────────────────────────────────

variable "qdrant_url" {
  type        = string
  description = "URL do cluster Qdrant Cloud (https://xxx.cloud.qdrant.io:6333)"
  validation {
    condition     = startswith(var.qdrant_url, "https://")
    error_message = "qdrant_url deve usar HTTPS (Qdrant Cloud)."
  }
}

variable "qdrant_api_key" {
  type      = string
  sensitive = true
}

variable "qdrant_collection" {
  type    = string
  default = "laudos_medicos"
}

# ─── Secrets — Observabilidade ────────────────────────────────────────────────

variable "langfuse_public_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "langfuse_secret_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "langfuse_host" {
  type    = string
  default = "https://cloud.langfuse.com"
}
