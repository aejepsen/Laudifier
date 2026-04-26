# Object Storage — substitui Azure Blob para storage da app
data "oci_objectstorage_namespace" "ns" {
  compartment_id = var.tenancy_ocid
}

resource "oci_objectstorage_bucket" "storage" {
  compartment_id = var.compartment_ocid
  namespace      = data.oci_objectstorage_namespace.ns.namespace
  name           = "${var.app_name}-storage"
  access_type    = "NoPublicAccess"
  storage_tier   = "Standard"
  versioning     = "Enabled"
}

# ─── Customer Secret Key (S3-compatible API) ────────────────────────────────
# Permite uso do boto3 contra OCI Object Storage via storage_service.py existente
resource "oci_identity_customer_secret_key" "s3" {
  user_id      = var.user_ocid
  display_name = "${var.app_name}-s3-compat"
}

# IAM policy — permite ao service principal Object Storage executar lifecycle
resource "oci_identity_policy" "objectstorage_lifecycle" {
  compartment_id = var.tenancy_ocid # policies devem ficar no tenancy ou subtree
  name           = "${var.app_name}-objectstorage-lifecycle"
  description    = "Permite ao Object Storage executar lifecycle policies"
  statements = [
    "Allow service objectstorage-${var.region} to manage object-family in tenancy"
  ]
}

# Lifecycle — corta risco de versioning estourar 20GB free tier
resource "oci_objectstorage_object_lifecycle_policy" "storage" {
  depends_on = [oci_identity_policy.objectstorage_lifecycle]
  namespace = data.oci_objectstorage_namespace.ns.namespace
  bucket    = oci_objectstorage_bucket.storage.name

  # Versões antigas → deletar após 30 dias
  rules {
    name        = "delete-old-versions"
    action      = "DELETE"
    is_enabled  = true
    target      = "previous-object-versions"
    time_amount = 30
    time_unit   = "DAYS"
  }

  # Multipart uploads incompletos → abortar após 7 dias
  rules {
    name        = "abort-multipart"
    action      = "ABORT"
    is_enabled  = true
    target      = "multipart-uploads"
    time_amount = 7
    time_unit   = "DAYS"
  }
}
