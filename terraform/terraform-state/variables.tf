# -----------------------------------------------------------------------------
# Variables for Terraform State Backend
# -----------------------------------------------------------------------------

variable "aws_region" {
  description = "AWS region to create the S3 bucket and DynamoDB table in"
  type        = string
}

variable "bucket_name" {
  description = "Name of the S3 bucket for Terraform state (from values-trident.yaml .terraform.state.bucket)"
  type        = string
}

variable "dynamodb_table_name" {
  description = "Name of the DynamoDB table for Terraform state locking"
  type        = string
  default     = "terraform-state-lock"
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default = {
    ManagedBy = "Terraform"
    Purpose   = "Terraform-State-Backend"
  }
}
