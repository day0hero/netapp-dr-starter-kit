# -----------------------------------------------------------------------------
# Outputs for FSx ONTAP Terraform Module
# -----------------------------------------------------------------------------

output "file_system_id" {
  description = "FSx ONTAP file system ID"
  value       = aws_fsx_ontap_file_system.this.id
}

output "file_system_arn" {
  description = "FSx ONTAP file system ARN"
  value       = aws_fsx_ontap_file_system.this.arn
}

output "file_system_dns_name" {
  description = "FSx ONTAP file system DNS name"
  value       = aws_fsx_ontap_file_system.this.dns_name
}

output "management_endpoint_dns_name" {
  description = "FSx ONTAP management endpoint DNS name"
  value       = aws_fsx_ontap_file_system.this.endpoints[0].management[0].dns_name
}

output "management_endpoint_ip_addresses" {
  description = "FSx ONTAP management endpoint IP addresses"
  value       = aws_fsx_ontap_file_system.this.endpoints[0].management[0].ip_addresses
}

output "intercluster_endpoint_dns_name" {
  description = "FSx ONTAP intercluster endpoint DNS name"
  value       = aws_fsx_ontap_file_system.this.endpoints[0].intercluster[0].dns_name
}

output "intercluster_endpoint_ip_addresses" {
  description = "FSx ONTAP intercluster endpoint IP addresses"
  value       = aws_fsx_ontap_file_system.this.endpoints[0].intercluster[0].ip_addresses
}

output "svm_id" {
  description = "Storage Virtual Machine (SVM) ID"
  value       = aws_fsx_ontap_storage_virtual_machine.this.id
}

output "svm_uuid" {
  description = "Storage Virtual Machine (SVM) UUID"
  value       = aws_fsx_ontap_storage_virtual_machine.this.uuid
}

output "svm_name" {
  description = "Storage Virtual Machine (SVM) name"
  value       = aws_fsx_ontap_storage_virtual_machine.this.name
}

output "svm_management_endpoint_dns_name" {
  description = "SVM management endpoint DNS name"
  value       = try(aws_fsx_ontap_storage_virtual_machine.this.endpoints[0].management[0].dns_name, "")
}

output "svm_management_endpoint_ip_addresses" {
  description = "SVM management endpoint IP addresses"
  value       = try(aws_fsx_ontap_storage_virtual_machine.this.endpoints[0].management[0].ip_addresses, [])
}

output "svm_iscsi_endpoint_dns_name" {
  description = "SVM iSCSI endpoint DNS name"
  value       = try(aws_fsx_ontap_storage_virtual_machine.this.endpoints[0].iscsi[0].dns_name, "")
}

output "svm_iscsi_endpoint_ip_addresses" {
  description = "SVM iSCSI endpoint IP addresses"
  value       = try(aws_fsx_ontap_storage_virtual_machine.this.endpoints[0].iscsi[0].ip_addresses, [])
}

output "svm_nfs_endpoint_dns_name" {
  description = "SVM NFS endpoint DNS name"
  value       = try(aws_fsx_ontap_storage_virtual_machine.this.endpoints[0].nfs[0].dns_name, "")
}

output "svm_nfs_endpoint_ip_addresses" {
  description = "SVM NFS endpoint IP addresses"
  value       = try(aws_fsx_ontap_storage_virtual_machine.this.endpoints[0].nfs[0].ip_addresses, [])
}

output "security_group_id" {
  description = "Security group ID for FSx ONTAP"
  value       = aws_security_group.fsx_ontap.id
}

output "fsx_admin_secret_arn" {
  description = "ARN of the FSx admin password secret in Secrets Manager"
  value       = var.create_secrets ? aws_secretsmanager_secret.fsx_admin[0].arn : ""
}

output "svm_admin_secret_arn" {
  description = "ARN of the SVM admin password secret in Secrets Manager"
  value       = var.create_secrets ? aws_secretsmanager_secret.svm_admin[0].arn : ""
}

# Output for Trident integration
output "trident_config" {
  description = "Configuration values for Trident integration"
  value = {
    mgmtLIF = try(aws_fsx_ontap_storage_virtual_machine.this.endpoints[0].management[0].dns_name, "")
    svm     = aws_fsx_ontap_storage_virtual_machine.this.name
  }
}
