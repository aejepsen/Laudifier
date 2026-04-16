# ─── Resource Group ───────────────────────────────────────────────────────────

resource "azurerm_resource_group" "main" {
  name     = local.resource_group_name
  location = var.location
  tags     = local.common_tags
}


# ─── Storage Account (Whisper cache + Blob laudos) ────────────────────────────

resource "azurerm_storage_account" "main" {
  name                            = local.storage_account_name
  resource_group_name             = azurerm_resource_group.main.name
  location                        = azurerm_resource_group.main.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  tags                            = local.common_tags
}

resource "azurerm_storage_share" "whisper" {
  name                 = "whisper-models"
  storage_account_name = azurerm_storage_account.main.name
  quota                = var.whisper_share_quota_gb

  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_storage_container" "laudos" {
  name                  = "laudos"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}


# ─── Log Analytics ────────────────────────────────────────────────────────────

resource "azurerm_log_analytics_workspace" "main" {
  name                = "${local.name_prefix}-logs"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.common_tags
}


# ─── Container Apps Environment ───────────────────────────────────────────────

resource "azurerm_container_app_environment" "main" {
  name                       = "${local.name_prefix}-env"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  tags                       = local.common_tags
}

resource "azurerm_container_app_environment_storage" "whisper" {
  name                         = "whisper-storage"
  container_app_environment_id = azurerm_container_app_environment.main.id
  account_name                 = azurerm_storage_account.main.name
  share_name                   = azurerm_storage_share.whisper.name
  access_key                   = azurerm_storage_account.main.primary_access_key
  access_mode                  = "ReadWrite"
}


# ─── Container App — Backend ──────────────────────────────────────────────────
# Registry: Docker Hub (1 repo privado grátis — sem rate limit autenticado)
# Custo: $0 com scale-to-zero (min_replicas = 0)

resource "azurerm_container_app" "backend" {
  name                         = "${local.name_prefix}-backend"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  tags                         = local.common_tags

  registry {
    server               = "index.docker.io"
    username             = var.dockerhub_username
    password_secret_name = "dockerhub-token"
  }

  secret {
    name  = "dockerhub-token"
    value = var.dockerhub_token
  }
  secret {
    name  = "anthropic-api-key"
    value = var.anthropic_api_key
  }

  secret {
    name  = "supabase-url"
    value = var.supabase_url
  }
  secret {
    name  = "supabase-anon-key"
    value = var.supabase_anon_key
  }
  secret {
    name  = "supabase-service-key"
    value = var.supabase_service_role_key
  }
  secret {
    name  = "jwt-secret"
    value = var.jwt_secret
  }
  secret {
    name  = "qdrant-url"
    value = var.qdrant_url
  }
  secret {
    name  = "qdrant-api-key"
    value = var.qdrant_api_key
  }
  secret {
    name  = "langfuse-public-key"
    value = var.langfuse_public_key
  }
  secret {
    name  = "langfuse-secret-key"
    value = var.langfuse_secret_key
  }
  secret {
    name  = "storage-conn-string"
    value = azurerm_storage_account.main.primary_connection_string
  }

  template {
    min_replicas = var.backend_min_replicas
    max_replicas = var.backend_max_replicas

    volume {
      name         = "whisper-cache"
      storage_type = "AzureFile"
      storage_name = azurerm_container_app_environment_storage.whisper.name
    }

    container {
      name   = "backend"
      image  = "docker.io/${var.dockerhub_username}/laudifier-backend:latest"
      cpu    = var.backend_cpu
      memory = var.backend_memory

      env {
        name  = "APP_ENV"
        value = var.environment
      }
      env {
        name  = "CORS_ORIGINS"
        value = var.cors_origins
      }
      env {
        name  = "QDRANT_COLLECTION"
        value = var.qdrant_collection
      }
      env {
        name  = "WHISPER_MODEL"
        value = local.whisper_model
      }
      env {
        name  = "WHISPER_CACHE_DIR"
        value = "/home/app/.cache/whisper"
      }
      env {
        name  = "USE_LOCAL_STORAGE"
        value = "false"
      }
      env {
        name  = "LANGFUSE_HOST"
        value = var.langfuse_host
      }
      env {
        name        = "ANTHROPIC_API_KEY"
        secret_name = "anthropic-api-key"
      }

      env {
        name        = "SUPABASE_URL"
        secret_name = "supabase-url"
      }
      env {
        name        = "SUPABASE_ANON_KEY"
        secret_name = "supabase-anon-key"
      }
      env {
        name        = "SUPABASE_SERVICE_ROLE_KEY"
        secret_name = "supabase-service-key"
      }
      env {
        name        = "JWT_SECRET"
        secret_name = "jwt-secret"
      }
      env {
        name        = "QDRANT_URL"
        secret_name = "qdrant-url"
      }
      env {
        name        = "QDRANT_API_KEY"
        secret_name = "qdrant-api-key"
      }
      env {
        name        = "LANGFUSE_PUBLIC_KEY"
        secret_name = "langfuse-public-key"
      }
      env {
        name        = "LANGFUSE_SECRET_KEY"
        secret_name = "langfuse-secret-key"
      }
      env {
        name        = "AZURE_STORAGE_CONNECTION_STRING"
        secret_name = "storage-conn-string"
      }

      volume_mounts {
        name = "whisper-cache"
        path = "/home/app/.cache/whisper"
      }

      liveness_probe {
        path                    = "/health/live"
        port                    = 8000
        transport               = "HTTP"
        initial_delay           = 30
        interval_seconds        = 30
        failure_count_threshold = 3
      }

      readiness_probe {
        path                    = "/health/ready"
        port                    = 8000
        transport               = "HTTP"
        interval_seconds        = 10
        failure_count_threshold = 3
      }

      startup_probe {
        path                    = "/health"
        port                    = 8000
        transport               = "HTTP"
        interval_seconds        = 5
        failure_count_threshold = 10
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }
}


# ─── Static Web App — Frontend Angular ────────────────────────────────────────
# Custo: $0 permanente — Free tier inclui 100 GB/mês de bandwidth

resource "azurerm_static_web_app" "frontend" {
  name                = "${local.name_prefix}-frontend"
  resource_group_name = azurerm_resource_group.main.name
  location            = "eastus2"
  sku_tier            = "Free"
  sku_size            = "Free"
  tags                = local.common_tags
}
