# -----------------------------------------------------------------------------
# Variables for FSx ONTAP Terraform Module
# -----------------------------------------------------------------------------

# AWS Configuration
variable "aws_region" {
  description = "AWS region for FSx ONTAP deployment"
  type        = string
}

# Network Configuration
variable "vpc_id" {
  description = "VPC ID where FSx ONTAP will be deployed"
  type        = string
}

variable "subnet_ids" {
  description = "List of subnet IDs for FSx ONTAP (2 subnets in different AZs for MULTI_AZ)"
  type        = list(string)
}

variable "route_table_ids" {
  description = "List of route table IDs for FSx ONTAP endpoint access"
  type        = list(string)
}

variable "allowed_cidrs" {
  description = "List of CIDR blocks allowed to access FSx ONTAP (e.g. local VPC + peered VPC)"
  type        = list(string)
  default     = ["10.0.0.0/16"]
}

# FSx ONTAP Configuration
variable "file_system_name" {
  description = "Name for the FSx ONTAP file system (defaults to cluster_name-region-fsx)"
  type        = string
}

variable "storage_capacity" {
  description = "Storage capacity in GiB (minimum 1024)"
  type        = number
  default     = 1024
}

variable "throughput_capacity" {
  description = "Throughput capacity in MBps (128, 256, 512, 1024, 2048, 4096)"
  type        = number
  default     = 1024
}

variable "storage_type" {
  description = "Storage type: SSD or HDD"
  type        = string
  default     = "SSD"
}

variable "deployment_type" {
  description = "Deployment type: MULTI_AZ_1 or SINGLE_AZ_1"
  type        = string
  default     = "MULTI_AZ_1"
}

variable "weekly_maintenance_time" {
  description = "Weekly maintenance window in format d:HH:MM (UTC)"
  type        = string
  default     = "7:01:00"
}

variable "fsx_admin_password" {
  description = "Password for the fsxadmin user"
  type        = string
  sensitive   = true
}

variable "automatic_backup_retention_days" {
  description = "Number of days to retain automatic backups"
  type        = number
  default     = 3
}

variable "daily_automatic_backup_start_time" {
  description = "Time for daily automatic backup in HH:MM format (UTC)"
  type        = string
  default     = "01:00"
}

# SVM Configuration
variable "svm_name" {
  description = "Name for the Storage Virtual Machine (SVM)"
  type        = string
  default     = "SVM1"
}

variable "root_volume_security_style" {
  description = "Security style for SVM root volume: UNIX, NTFS, or MIXED"
  type        = string
  default     = "UNIX"
}

variable "svm_admin_password" {
  description = "Password for the vsadmin user"
  type        = string
  sensitive   = true
}

# Secrets Manager Configuration
variable "create_secrets" {
  description = "Whether to create secrets in AWS Secrets Manager"
  type        = bool
  default     = true
}

# Tags
variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default = {
    Environment = "production"
    ManagedBy   = "Terraform"
  }
}
