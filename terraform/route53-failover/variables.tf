# -----------------------------------------------------------------------------
# Variables for Route53 DR Failover
# -----------------------------------------------------------------------------

variable "aws_region" {
  description = "AWS region for the Route53 resources (Route53 is global but provider needs a region)"
  type        = string
}

variable "domain" {
  description = "Base domain for DR failover routes (e.g. dr.example.com)"
  type        = string
}

variable "create_hosted_zone" {
  description = "Whether to create a new Route53 hosted zone (false = use existing hosted_zone_id)"
  type        = bool
  default     = true
}

variable "hosted_zone_id" {
  description = "Existing Route53 hosted zone ID (only used when create_hosted_zone = false)"
  type        = string
  default     = ""
}

variable "primary_ingress_hostname" {
  description = "DNS hostname of the primary cluster's ingress load balancer (e.g. router-default.apps.primary.example.com)"
  type        = string
}

variable "secondary_ingress_hostname" {
  description = "DNS hostname of the secondary cluster's ingress load balancer (e.g. router-default.apps.secondary.example.com)"
  type        = string
}

variable "primary_health_check_fqdn" {
  description = "FQDN for the primary cluster health check (typically the console or router hostname)"
  type        = string
}

variable "secondary_health_check_fqdn" {
  description = "FQDN for the secondary cluster health check"
  type        = string
}

variable "apps" {
  description = "List of applications to create failover records for"
  type = list(object({
    name = string
  }))
  default = []
}

variable "health_check_path" {
  description = "Path for HTTPS health checks against the cluster ingress"
  type        = string
  default     = "/"
}

variable "record_ttl" {
  description = "TTL for DNS failover records (seconds)"
  type        = number
  default     = 60
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default = {
    ManagedBy = "Terraform"
    Purpose   = "DR-Failover"
  }
}
