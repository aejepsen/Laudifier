terraform {
  required_version = ">= 1.7"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.110"
    }
  }

  # Descomente para usar Azure Blob como backend remoto
  # backend "azurerm" {
  #   resource_group_name  = "rg-laudifier-tfstate"
  #   storage_account_name = "stlaudifiertfstate"
  #   container_name       = "tfstate"
  #   key                  = "laudifier.tfstate"
  # }
}
