# ─── OCI auth ────────────────────────────────────────────────────────────────
variable "tenancy_ocid" {
  description = "OCID do tenancy"
  type        = string
}

variable "user_ocid" {
  description = "OCID do usuário API"
  type        = string
}

variable "fingerprint" {
  description = "Fingerprint da API key"
  type        = string
}

variable "private_key_path" {
  description = "Path local da private key OCI (PEM)"
  type        = string
}

variable "region" {
  description = "Região OCI"
  type        = string
  default     = "us-ashburn-1"
}

variable "compartment_ocid" {
  description = "OCID do compartment alvo (root tenancy se não criar dedicado)"
  type        = string
}

# ─── App ─────────────────────────────────────────────────────────────────────
variable "app_name" {
  description = "Prefixo para recursos"
  type        = string
  default     = "laudifier"
}

variable "domain" {
  description = "Domínio público (Caddy emite TLS via Let's Encrypt)"
  type        = string
  default     = "laudifier.com.br"
}

variable "letsencrypt_email" {
  description = "E-mail para Let's Encrypt"
  type        = string
}

# ─── VM ──────────────────────────────────────────────────────────────────────
variable "ssh_public_key" {
  description = "Chave SSH pública (conteúdo, não path)"
  type        = string
}

variable "vm_shape" {
  description = "Shape ARM Ampere — Always Free permite até 4 OCPU / 24GB"
  type        = string
  default     = "VM.Standard.A1.Flex"
}

variable "vm_ocpus" {
  description = "OCPUs (cores ARM)"
  type        = number
  default     = 4
}

variable "vm_memory_gb" {
  description = "RAM em GB (Always Free: até 24)"
  type        = number
  default     = 24
}

variable "boot_volume_size_gb" {
  description = "Boot volume em GB (Always Free: até 200 total)"
  type        = number
  default     = 100
}

# ─── Source da app (para cloud-init clonar/pull) ─────────────────────────────
variable "git_repo_url" {
  description = "URL Git do repo Laudifier (https com PAT ou ssh)"
  type        = string
}

variable "git_branch" {
  description = "Branch a fazer checkout"
  type        = string
  default     = "main"
}

variable "deploy_key_path" {
  description = "Path local da private SSH deploy key (cadastrada no GitHub Settings → Deploy keys)"
  type        = string
}

# ─── Secrets app (passados via cloud-init para /opt/laudifier/.env) ──────────
variable "app_env" {
  description = <<-EOT
    Mapa de variáveis de ambiente da aplicação (ANTHROPIC_API_KEY, SUPABASE_*,
    QDRANT_*, LANGFUSE_*, JWT_SECRET, ADMIN_API_KEY, etc).
    OCI_NAMESPACE/OCI_BUCKET são adicionados automaticamente.
  EOT
  type        = map(string)
  sensitive   = true
}

# ─── SSH ingress (restrinja em produção) ─────────────────────────────────────
variable "ssh_cidr_allowlist" {
  description = "CIDRs autorizados a SSH (default 0.0.0.0/0 — restringir em prod)"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}
