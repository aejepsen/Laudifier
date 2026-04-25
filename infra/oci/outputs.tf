output "public_ip" {
  description = "IP público da VM — apontar A record do domínio aqui"
  value       = oci_core_instance.vm.public_ip
}

output "ssh_command" {
  description = "Comando SSH (usuário padrão Ubuntu cloud image)"
  value       = "ssh ubuntu@${oci_core_instance.vm.public_ip}"
}

output "domain" {
  value = var.domain
}

output "object_storage_namespace" {
  value = data.oci_objectstorage_namespace.ns.namespace
}

output "object_storage_bucket" {
  value = oci_objectstorage_bucket.storage.name
}

output "dns_setup_hint" {
  description = "Configure no registrador do domínio"
  value       = "A record: ${var.domain} -> ${oci_core_instance.vm.public_ip}"
}
