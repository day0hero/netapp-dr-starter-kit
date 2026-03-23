# -----------------------------------------------------------------------------
# Route53 DR Failover
# -----------------------------------------------------------------------------
# Creates a Route53 hosted zone (or uses an existing one), health checks for
# each cluster's ingress, and failover routing records for each protected app.
#
# Traffic flow:
#   boutique.dr.example.com
#     → Route53 failover check
#       → PRIMARY healthy  → CNAME to primary ingress LB
#       → PRIMARY unhealthy → CNAME to secondary ingress LB
#     → OpenShift router matches Route with host=boutique.dr.example.com
#     → App served from whichever cluster Route53 selected
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Hosted Zone
# -----------------------------------------------------------------------------
resource "aws_route53_zone" "dr" {
  count = var.create_hosted_zone ? 1 : 0
  name  = var.domain

  tags = merge(var.tags, {
    Name = var.domain
  })
}

locals {
  zone_id = var.create_hosted_zone ? aws_route53_zone.dr[0].zone_id : var.hosted_zone_id
}

# -----------------------------------------------------------------------------
# Health Checks — one per cluster
#
# HTTPS check against the cluster's ingress router. The router responds with
# a 2xx/3xx on the wildcard domain, confirming the cluster is reachable.
# Route53 health checkers run from multiple AWS regions globally.
# -----------------------------------------------------------------------------
resource "aws_route53_health_check" "primary" {
  fqdn              = var.primary_health_check_fqdn
  port              = 443
  type              = "HTTPS"
  resource_path     = var.health_check_path
  failure_threshold = 3
  request_interval  = 30

  tags = merge(var.tags, {
    Name = "dr-primary-cluster"
  })
}

resource "aws_route53_health_check" "secondary" {
  fqdn              = var.secondary_health_check_fqdn
  port              = 443
  type              = "HTTPS"
  resource_path     = var.health_check_path
  failure_threshold = 3
  request_interval  = 30

  tags = merge(var.tags, {
    Name = "dr-secondary-cluster"
  })
}

# -----------------------------------------------------------------------------
# Failover Records — one PRIMARY + one SECONDARY per app
#
# When the primary health check is healthy, Route53 returns the primary
# ingress hostname. When unhealthy, it returns the secondary.
# -----------------------------------------------------------------------------
resource "aws_route53_record" "app_primary" {
  for_each = { for app in var.apps : app.name => app }

  zone_id = local.zone_id
  name    = "${each.value.name}.${var.domain}"
  type    = "CNAME"
  ttl     = var.record_ttl

  failover_routing_policy {
    type = "PRIMARY"
  }

  set_identifier  = "${each.value.name}-primary"
  records         = [var.primary_ingress_hostname]
  health_check_id = aws_route53_health_check.primary.id
}

resource "aws_route53_record" "app_secondary" {
  for_each = { for app in var.apps : app.name => app }

  zone_id = local.zone_id
  name    = "${each.value.name}.${var.domain}"
  type    = "CNAME"
  ttl     = var.record_ttl

  failover_routing_policy {
    type = "SECONDARY"
  }

  set_identifier  = "${each.value.name}-secondary"
  records         = [var.secondary_ingress_hostname]
  health_check_id = aws_route53_health_check.secondary.id
}
