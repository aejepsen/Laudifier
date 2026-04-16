locals {
  common_tags = {
    Project     = "laudifier"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }

  fly_app_name = var.environment == "prod" ? var.fly_app_name : "${var.fly_app_name}-${var.environment}"
}
