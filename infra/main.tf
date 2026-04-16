# ─── Fly.io — Backend ─────────────────────────────────────────────────────────

resource "fly_app" "backend" {
  name = local.fly_app_name
  org  = "personal"
}

resource "fly_ip" "backend_ipv4" {
  app  = fly_app.backend.name
  type = "v4"
}

resource "fly_ip" "backend_ipv6" {
  app  = fly_app.backend.name
  type = "v6"
}

resource "fly_volume" "whisper_cache" {
  app    = fly_app.backend.name
  name   = "whisper_models"
  region = var.fly_region
  size   = var.fly_whisper_volume_size_gb

  lifecycle {
    prevent_destroy = true
  }
}

# ─── Vercel — Frontend ────────────────────────────────────────────────────────

resource "vercel_project" "frontend" {
  name      = var.vercel_project_name
  framework = null # Angular com output customizado — sem framework preset

  git_repository = {
    type = "github"
    repo = "aejepsen/laudifier"
  }

  build_command    = "npm run build"
  output_directory = "dist/laudifier/browser"
  root_directory   = ""
}

resource "vercel_project_environment_variable" "api_url" {
  project_id = vercel_project.frontend.id
  key        = "NEXT_PUBLIC_API_URL"
  value      = var.api_url
  target     = ["production", "preview"]
}
