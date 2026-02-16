# -----------------------------------------------------------------------------
# Cross-Region VPC Peering for DR
# -----------------------------------------------------------------------------
# Creates a VPC peering connection between two clusters in different AWS
# regions, adds routes in both VPCs, and enables DNS resolution across the
# peering connection.
# -----------------------------------------------------------------------------

# Data sources to validate the VPCs exist
data "aws_vpc" "prod" {
  provider = aws.prod
  id       = var.prod_vpc_id
}

data "aws_vpc" "dr" {
  provider = aws.dr
  id       = var.dr_vpc_id
}

# -----------------------------------------------------------------------------
# VPC Peering Connection (initiated from prod side)
# -----------------------------------------------------------------------------
resource "aws_vpc_peering_connection" "prod_to_dr" {
  provider    = aws.prod
  vpc_id      = var.prod_vpc_id
  peer_vpc_id = var.dr_vpc_id
  peer_region = var.dr_region
  auto_accept = false

  tags = merge(var.tags, {
    Name = "${var.prod_cluster_name}-to-${var.dr_cluster_name}"
    Side = "Requester"
  })
}

# Accept the peering connection on the DR side
resource "aws_vpc_peering_connection_accepter" "dr_accept" {
  provider                  = aws.dr
  vpc_peering_connection_id = aws_vpc_peering_connection.prod_to_dr.id
  auto_accept               = true

  tags = merge(var.tags, {
    Name = "${var.dr_cluster_name}-to-${var.prod_cluster_name}"
    Side = "Accepter"
  })
}

# -----------------------------------------------------------------------------
# Peering Connection Options - enable DNS resolution
# (Requires ec2:ModifyVpcPeeringConnectionOptions permission)
# -----------------------------------------------------------------------------
resource "aws_vpc_peering_connection_options" "prod" {
  count                     = var.enable_dns_resolution ? 1 : 0
  provider                  = aws.prod
  vpc_peering_connection_id = aws_vpc_peering_connection.prod_to_dr.id

  requester {
    allow_remote_vpc_dns_resolution = true
  }

  depends_on = [aws_vpc_peering_connection_accepter.dr_accept]
}

resource "aws_vpc_peering_connection_options" "dr" {
  count                     = var.enable_dns_resolution ? 1 : 0
  provider                  = aws.dr
  vpc_peering_connection_id = aws_vpc_peering_connection.prod_to_dr.id

  accepter {
    allow_remote_vpc_dns_resolution = true
  }

  depends_on = [aws_vpc_peering_connection_accepter.dr_accept]
}

# -----------------------------------------------------------------------------
# Routes: Prod VPC -> DR VPC (via peering)
# -----------------------------------------------------------------------------
resource "aws_route" "prod_to_dr" {
  provider                  = aws.prod
  for_each                  = toset(var.prod_route_table_ids)
  route_table_id            = each.value
  destination_cidr_block    = var.dr_vpc_cidr
  vpc_peering_connection_id = aws_vpc_peering_connection.prod_to_dr.id

  depends_on = [aws_vpc_peering_connection_accepter.dr_accept]
}

# -----------------------------------------------------------------------------
# Routes: DR VPC -> Prod VPC (via peering)
# -----------------------------------------------------------------------------
resource "aws_route" "dr_to_prod" {
  provider                  = aws.dr
  for_each                  = toset(var.dr_route_table_ids)
  route_table_id            = each.value
  destination_cidr_block    = var.prod_vpc_cidr
  vpc_peering_connection_id = aws_vpc_peering_connection.prod_to_dr.id

  depends_on = [aws_vpc_peering_connection_accepter.dr_accept]
}
