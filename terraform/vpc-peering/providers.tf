# -----------------------------------------------------------------------------
# Terraform and Provider Configuration for Cross-Region VPC Peering
# -----------------------------------------------------------------------------

terraform {
  required_version = ">= 1.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

# Provider for the production (requester) region
provider "aws" {
  alias  = "prod"
  region = var.prod_region
}

# Provider for the DR (accepter) region
provider "aws" {
  alias  = "dr"
  region = var.dr_region
}
