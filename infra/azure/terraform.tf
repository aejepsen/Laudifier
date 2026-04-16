terraform {
  required_version = ">= 1.7"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.110"
    }
  }

  backend "azurerm" {
    resource_group_name  = "rg-aiprofessor-tfstate"
    storage_account_name = "aiprofessortfstate"
    container_name       = "tfstate"
    key                  = "laudifier.tfstate"
  }
}
