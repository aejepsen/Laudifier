output "backend_url" {
  description = "URL pública do backend (Azure Container Apps)"
  value       = "https://${azurerm_container_app.backend.ingress[0].fqdn}"
}

output "frontend_url" {
  description = "URL pública do frontend (Azure Static Web Apps)"
  value       = "https://${azurerm_static_web_app.frontend.default_host_name}"
}

output "swa_deploy_token" {
  description = "Token de deploy da Static Web App — configure no GitHub Actions secret SWA_DEPLOY_TOKEN"
  value       = azurerm_static_web_app.frontend.api_key
  sensitive   = true
}

output "storage_account_name" {
  description = "Nome da Storage Account (para referência no pipeline de seed)"
  value       = azurerm_storage_account.main.name
}

output "storage_connection_string" {
  description = "Connection string da Storage Account — use no .env"
  value       = azurerm_storage_account.main.primary_connection_string
  sensitive   = true
}

output "resource_group_name" {
  description = "Nome do Resource Group"
  value       = azurerm_resource_group.main.name
}
