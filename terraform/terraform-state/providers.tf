# -----------------------------------------------------------------------------
# Terraform and Provider Configuration
# -----------------------------------------------------------------------------

terraform {
  required_version = ">= 1.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }

  # This module uses local state intentionally - it bootstraps the remote
  # backend that all other modules will use.
}

provider "aws" {
  region = var.aws_region
}
