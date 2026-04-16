#!/usr/bin/env bash
# scripts/sync-secrets.sh
# Sincroniza todos os segredos do .env.ci para o GitHub Actions com um comando.
#
# Pré-requisitos:
#   gh auth login  (autenticado no GitHub CLI)
#
# Uso:
#   cp .env.ci.example .env.ci   # preencha os valores
#   ./scripts/sync-secrets.sh

set -euo pipefail

ENV_FILE="$(dirname "$0")/../.env.ci"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "❌ Arquivo .env.ci não encontrado."
  echo "   Execute: cp .env.ci.example .env.ci e preencha os valores."
  exit 1
fi

# Verifica se ainda tem placeholder não preenchido
if grep -q "change-me" "$ENV_FILE"; then
  echo "⚠️  Atenção: existem valores 'change-me' em .env.ci."
  echo "   Preencha todos antes de continuar."
  read -rp "   Continuar mesmo assim? (s/N) " resp
  [[ "$resp" =~ ^[sS]$ ]] || exit 1
fi

echo "🔐 Sincronizando segredos para o repositório atual..."
gh secret set --env-file "$ENV_FILE"

echo ""
echo "✅ Segredos sincronizados. Verifique em:"
echo "   github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner)/settings/secrets/actions"
