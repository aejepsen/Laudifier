locals {
  # ── Prefixo de nomes ──────────────────────────────────────────────────────
  name_prefix = "${var.app_name}-${var.environment}"

  # Resource Group
  resource_group_name = "rg-${local.name_prefix}"

  # ACR: 5-50 chars, só alfanumérico
  acr_name = substr(replace("acr${var.app_name}${var.environment}", "-", ""), 0, 50)

  # Storage Account: 3-24 chars, só alfanumérico minúsculo
  storage_account_name = substr(lower(replace("st${var.app_name}${var.environment}", "-", "")), 0, 24)

  # Whisper model size → caminho do modelo no Azure Files
  whisper_model = "small"

  # ── Tags comuns ───────────────────────────────────────────────────────────
  common_tags = {
    project     = var.app_name
    environment = var.environment
    managed_by  = "terraform"
    repository  = "laudifier"
  }
}
