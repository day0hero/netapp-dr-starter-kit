# -----------------------------------------------------------------------------
# Outputs for Terraform State Backend
# -----------------------------------------------------------------------------

output "bucket_name" {
  description = "S3 bucket name for Terraform state"
  value       = aws_s3_bucket.state.id
}

output "bucket_arn" {
  description = "S3 bucket ARN"
  value       = aws_s3_bucket.state.arn
}

output "bucket_region" {
  description = "S3 bucket region"
  value       = aws_s3_bucket.state.region
}

output "dynamodb_table_name" {
  description = "DynamoDB table name for state locking"
  value       = aws_dynamodb_table.lock.name
}

output "dynamodb_table_arn" {
  description = "DynamoDB table ARN"
  value       = aws_dynamodb_table.lock.arn
}

output "backend_config" {
  description = "Backend configuration summary for other modules"
  value = {
    bucket         = aws_s3_bucket.state.id
    region         = aws_s3_bucket.state.region
    dynamodb_table = aws_dynamodb_table.lock.name
    encrypt        = true
  }
}
