# Laudifier — OCI Always Free deploy

Stack: VM ARM Ampere A1 (4 OCPU / 24GB) + Object Storage + VCN/subnet pública.
Caddy faz reverse proxy + TLS automático Let's Encrypt.
Containers na VM: `qdrant`, `backend`, `frontend`, `caddy`.

## Pré-requisitos

1. Conta OCI Always Free, region `us-ashburn-1`.
2. API key gerada no Console (Profile → User Settings → API Keys).
   - Baixar `oci_api_key.pem` para `~/.oci/`.
   - Anotar `tenancy_ocid`, `user_ocid`, `fingerprint`.
3. Compartment de destino (root tenancy serve, mas dedicado é melhor).
4. SSH key local (`ssh-keygen -t ed25519`).
5. PAT do GitHub com scope `repo` (read).
6. DNS de `laudifier.com.br` no registrador (apontar A record após apply).

## Deploy

```bash
cd infra/oci
cp terraform.tfvars.example terraform.tfvars
# Editar terraform.tfvars com OCIDs, secrets e SSH key

terraform init
terraform plan -out tfplan
terraform apply tfplan
```

## Pós-apply

```bash
terraform output public_ip
# Configure A record: laudifier.com.br -> <public_ip>
# Aguarde ~5min para cloud-init completar (ssh ubuntu@<ip> + tail /var/log/laudifier-bootstrap.log)
# Caddy emite cert TLS automaticamente quando DNS resolver
```

## Atualização da app

```bash
ssh ubuntu@<ip>
cd /opt/laudifier/repo && git pull
cd /opt/laudifier
sudo docker compose -f docker-compose.prod.yml build
sudo docker compose -f docker-compose.prod.yml up -d
```

## Backup Object Storage

Bucket `laudifier-storage` substitui Azure Blob (versionamento ativado).
Adapte `services/azure_blob.py` para SDK OCI ou use `oci-cli` em cron.

## Always Free limites

- Compute: 4 OCPU + 24GB RAM ARM (1 instância grande OU múltiplas)
- Boot volume total: 200GB (estamos usando 100GB)
- Object Storage: 20GB
- Egress: 10TB/mês
- Egress saída p/ Anthropic/Supabase/Langfuse não conta como interno OCI.
