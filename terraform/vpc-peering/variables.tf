# -----------------------------------------------------------------------------
# Variables for Cross-Region VPC Peering
# -----------------------------------------------------------------------------

# Production cluster
variable "prod_region" {
  description = "AWS region of the production cluster"
  type        = string
}

variable "prod_vpc_id" {
  description = "VPC ID of the production cluster"
  type        = string
}

variable "prod_vpc_cidr" {
  description = "VPC CIDR block of the production cluster"
  type        = string
}

variable "prod_cluster_name" {
  description = "Name of the production cluster (used for tagging)"
  type        = string
}

variable "prod_route_table_ids" {
  description = "Route table IDs in the production VPC to add peering routes to"
  type        = list(string)
}

# DR cluster
variable "dr_region" {
  description = "AWS region of the DR cluster"
  type        = string
}

variable "dr_vpc_id" {
  description = "VPC ID of the DR cluster"
  type        = string
}

variable "dr_vpc_cidr" {
  description = "VPC CIDR block of the DR cluster"
  type        = string
}

variable "dr_cluster_name" {
  description = "Name of the DR cluster (used for tagging)"
  type        = string
}

variable "dr_route_table_ids" {
  description = "Route table IDs in the DR VPC to add peering routes to"
  type        = list(string)
}

# Options
variable "enable_dns_resolution" {
  description = "Enable DNS resolution across the VPC peering connection. Requires ec2:ModifyVpcPeeringConnectionOptions permission."
  type        = bool
  default     = true
}

# Tags
variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default = {
    ManagedBy = "Terraform"
    Purpose   = "DR-VPC-Peering"
  }
}
