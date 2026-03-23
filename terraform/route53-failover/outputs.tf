# -----------------------------------------------------------------------------
# Outputs for Route53 DR Failover
# -----------------------------------------------------------------------------

output "hosted_zone_id" {
  description = "Route53 hosted zone ID"
  value       = local.zone_id
}

output "hosted_zone_name_servers" {
  description = "Name servers for the hosted zone (delegate from parent zone)"
  value       = var.create_hosted_zone ? aws_route53_zone.dr[0].name_servers : []
}

output "primary_health_check_id" {
  description = "Health check ID for the primary cluster"
  value       = aws_route53_health_check.primary.id
}

output "secondary_health_check_id" {
  description = "Health check ID for the secondary cluster"
  value       = aws_route53_health_check.secondary.id
}

output "failover_records" {
  description = "Map of app name to DR failover FQDN"
  value       = { for app in var.apps : app.name => "${app.name}.${var.domain}" }
}

output "domain" {
  description = "The DR failover domain"
  value       = var.domain
}
