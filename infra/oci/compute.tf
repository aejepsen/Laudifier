# ─── Imagem Ubuntu 22.04 ARM ─────────────────────────────────────────────────
data "oci_core_images" "ubuntu_arm" {
  compartment_id           = var.compartment_ocid
  operating_system         = "Canonical Ubuntu"
  operating_system_version = "22.04"
  shape                    = var.vm_shape
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

locals {
  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    app_env           = var.app_env
    oci_namespace     = data.oci_objectstorage_namespace.ns.namespace
    oci_bucket        = oci_objectstorage_bucket.storage.name
    region            = var.region
    domain            = var.domain
    letsencrypt_email = var.letsencrypt_email
    git_repo_url      = var.git_repo_url
    git_branch        = var.git_branch
    deploy_key        = file(var.deploy_key_path)
    s3_access_key     = oci_identity_customer_secret_key.s3.id
    s3_secret_key     = oci_identity_customer_secret_key.s3.key
    s3_endpoint       = "https://${data.oci_objectstorage_namespace.ns.namespace}.compat.objectstorage.${var.region}.oraclecloud.com"
  })
}

# ─── VM Ampere A1 Flex (Always Free up to 4 OCPU / 24GB) ─────────────────────
resource "oci_core_instance" "vm" {
  compartment_id      = var.compartment_ocid
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  shape               = var.vm_shape
  display_name        = "${var.app_name}-vm"

  shape_config {
    ocpus         = var.vm_ocpus
    memory_in_gbs = var.vm_memory_gb
  }

  source_details {
    source_type             = "image"
    source_id               = data.oci_core_images.ubuntu_arm.images[0].id
    boot_volume_size_in_gbs = var.boot_volume_size_gb
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.public.id
    assign_public_ip = true
    hostname_label   = "vm"
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data           = base64encode(local.user_data)
  }

  preserve_boot_volume = false

  lifecycle {
    ignore_changes = [
      source_details[0].source_id, # não recriar VM se nova imagem Ubuntu sair
    ]
  }
}
