#!/usr/bin/env bash
# infra/azure/bootstrap.sh
# Cria o Storage Account para o Terraform remote state.
# Rodar UMA VEZ antes do primeiro "terraform init".
# Pré-requisito: az login + az account set --subscription <id>

set -euo pipefail

RG="rg-laudifier-tfstate"
SA="stlaudifiertfstate"
CONTAINER="tfstate"
LOCATION="${1:-brazilsouth}"

echo "→ Criando resource group $RG..."
az group create \
  --name     "$RG" \
  --location "$LOCATION" \
  --output   none

echo "→ Criando storage account $SA..."
az storage account create \
  --name                   "$SA" \
  --resource-group         "$RG" \
  --location               "$LOCATION" \
  --sku                    Standard_LRS \
  --kind                   StorageV2 \
  --min-tls-version        TLS1_2 \
  --allow-blob-public-access false \
  --output                 none

echo "→ Criando container $CONTAINER..."
az storage container create \
  --name              "$CONTAINER" \
  --account-name      "$SA" \
  --auth-mode         login \
  --output            none

echo "✓ Backend remoto pronto. Execute:"
echo "  cd infra/azure && terraform init"
