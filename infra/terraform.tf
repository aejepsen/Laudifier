terraform {
  required_version = ">= 1.7"

  required_providers {
    fly = {
      source  = "fly-apps/fly"
      version = "~> 0.1"
    }
    vercel = {
      source  = "vercel/vercel"
      version = "~> 2.0"
    }
  }

  backend "local" {}
}
