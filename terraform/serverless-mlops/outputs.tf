output "deployment_stage" {
  description = "Current Terraform stage; disabled creates no resources."
  value       = var.deployment_stage
}

output "ecr_repository_url" {
  description = "Repository used to publish the immutable Lambda image."
  value       = local.enabled ? aws_ecr_repository.mlops[0].repository_url : null
  sensitive   = true
}

output "artifact_bucket_name" {
  description = "Synthetic MLOps artifact bucket."
  value       = local.enabled ? aws_s3_bucket.artifacts[0].bucket : null
  sensitive   = true
}

output "run_table_name" {
  description = "DynamoDB run-state table."
  value       = local.enabled ? aws_dynamodb_table.runs[0].name : null
}

output "lambda_function_name" {
  description = "One-shot trainer name, present only in runtime stage."
  value       = local.runtime ? aws_lambda_function.trainer[0].function_name : null
}

output "feature_snapshot_root" {
  description = "Bounded S3 key root for the three feature-only source objects."
  value       = trimsuffix(local.source_prefix, "/")
}

output "result_root" {
  description = "Bounded S3 key root for the six non-activated challenger artifacts."
  value       = trimsuffix(local.result_prefix, "/")
}

output "runtime_contract" {
  description = "Non-execution contract for operators and demonstration scripts."
  value = {
    compute                    = "lambda-one-shot"
    source_mode                = "s3-feature-snapshot"
    sagemaker_used             = false
    schedule_enabled           = false
    automatic_model_activation = false
    expected_terminal_state    = "TRAINED_PENDING_HUMAN_REVIEW"
  }
}
