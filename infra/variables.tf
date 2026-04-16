# ─── Ambiente ─────────────────────────────────────────────────────────────────

variable "environment" {
  description = "Ambiente de deploy: staging ou prod"
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["staging", "prod"], var.environment)
    error_message = "Environment deve ser 'staging' ou 'prod'."
  }
}

# ─── Fly.io — backend ────────────────────────────────────────────────────────

variable "fly_app_name" {
  description = "Nome do app no Fly.io (deve ser único globalmente)"
  type        = string
  default     = "laudifier-backend"
}

variable "fly_region" {
  description = "Região primária do Fly.io (gru = São Paulo)"
  type        = string
  default     = "gru"
}

variable "fly_vm_memory_mb" {
  description = "Memória da VM em MB (Whisper small exige ~512 MB)"
  type        = number
  default     = 1024

  validation {
    condition     = var.fly_vm_memory_mb >= 512
    error_message = "Whisper requer pelo menos 512 MB de memória."
  }
}

variable "fly_min_machines" {
  description = "Número mínimo de machines sempre rodando (0 = escala para zero)"
  type        = number
  default     = 1
}

variable "fly_whisper_volume_size_gb" {
  description = "Tamanho do volume persistente para cache do Whisper em GB"
  type        = number
  default     = 5
}

# ─── Vercel — frontend ────────────────────────────────────────────────────────

variable "vercel_team_id" {
  description = "Team ID da conta Vercel (opcional; omitir para contas pessoais)"
  type        = string
  default     = ""
}

variable "vercel_project_name" {
  description = "Nome do projeto no Vercel"
  type        = string
  default     = "laudifier"
}

variable "api_url" {
  description = "URL pública da API backend (usada como variável de ambiente no frontend)"
  type        = string
}
