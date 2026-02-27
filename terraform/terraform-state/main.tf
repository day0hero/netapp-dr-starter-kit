# -----------------------------------------------------------------------------
# Terraform State Backend - S3 Bucket + DynamoDB Lock Table
# -----------------------------------------------------------------------------
#
# This module bootstraps the remote state backend used by all other modules.
# It intentionally uses local state (chicken-and-egg: it creates the bucket
# that other modules store their state in).
#
# The S3 bucket stores state for resources across both regions:
#   - vpc-peering/terraform.tfstate
#   - fsx-ontap/<cluster>/<region>/terraform.tfstate
# -----------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

# -----------------------------------------------------------------------------
# S3 Bucket for Terraform State
# -----------------------------------------------------------------------------
resource "aws_s3_bucket" "state" {
  bucket = var.bucket_name

  tags = merge(var.tags, {
    Name = var.bucket_name
  })

  # Allow terraform destroy to remove the bucket even when it contains objects
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket = aws_s3_bucket.state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    id     = "cleanup-old-versions"
    status = "Enabled"

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

# -----------------------------------------------------------------------------
# DynamoDB Table for State Locking
# -----------------------------------------------------------------------------
resource "aws_dynamodb_table" "lock" {
  name         = var.dynamodb_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = merge(var.tags, {
    Name    = var.dynamodb_table_name
    Purpose = "Terraform State Locking"
  })
}
