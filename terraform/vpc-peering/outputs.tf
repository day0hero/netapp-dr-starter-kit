# -----------------------------------------------------------------------------
# Outputs for VPC Peering Module
# -----------------------------------------------------------------------------

output "peering_connection_id" {
  description = "VPC Peering Connection ID"
  value       = aws_vpc_peering_connection.prod_to_dr.id
}

output "peering_connection_status" {
  description = "VPC Peering Connection status"
  value       = aws_vpc_peering_connection_accepter.dr_accept.accept_status
}

output "prod_to_dr_routes" {
  description = "Route table IDs in prod VPC with peering routes added"
  value       = [for rt in aws_route.prod_to_dr : rt.route_table_id]
}

output "dr_to_prod_routes" {
  description = "Route table IDs in DR VPC with peering routes added"
  value       = [for rt in aws_route.dr_to_prod : rt.route_table_id]
}

output "summary" {
  description = "Summary of the VPC peering configuration"
  value = {
    peering_id         = aws_vpc_peering_connection.prod_to_dr.id
    prod_vpc_id        = var.prod_vpc_id
    prod_vpc_cidr      = var.prod_vpc_cidr
    prod_region        = var.prod_region
    dr_vpc_id          = var.dr_vpc_id
    dr_vpc_cidr        = var.dr_vpc_cidr
    dr_region          = var.dr_region
    prod_routes_count  = length(aws_route.prod_to_dr)
    dr_routes_count    = length(aws_route.dr_to_prod)
  }
}
