# ─── Fly.io ───────────────────────────────────────────────────────────────────

output "backend_app_name" {
  description = "Nome do app Fly.io criado"
  value       = fly_app.backend.name
}

output "backend_url" {
  description = "URL pública do backend (HTTPS)"
  value       = "https://${fly_app.backend.name}.fly.dev"
}

output "backend_ipv4" {
  description = "IPv4 dedicado do backend"
  value       = fly_ip.backend_ipv4.address
}

output "whisper_volume_id" {
  description = "ID do volume persistente do Whisper (não destruir sem backup)"
  value       = fly_volume.whisper_cache.id
}

# ─── Vercel ───────────────────────────────────────────────────────────────────

output "frontend_project_id" {
  description = "ID do projeto Vercel"
  value       = vercel_project.frontend.id
}

output "frontend_url" {
  description = "URL de produção do frontend"
  value       = "https://${var.vercel_project_name}.vercel.app"
}
