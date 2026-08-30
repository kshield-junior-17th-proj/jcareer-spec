output "deployment_stage" {
  description = "Current stage; disabled creates no resources."
  value       = var.deployment_stage
}

output "ecr_repository_url" {
  description = "Immutable worker image repository."
  value       = local.enabled ? aws_ecr_repository.worker[0].repository_url : null
  sensitive   = true
}

output "runtime_environment" {
  description = "Names the capability broker consumes; no account-qualified queue URL is exported."
  value = local.runtime ? {
    OPENDART_DISPATCH_MODE           = "serverless_queue"
    OPENDART_REFRESH_QUEUE_NAME      = aws_sqs_queue.refresh[0].name
    OPENDART_RESULT_TABLE_NAME       = aws_dynamodb_table.results[0].name
    OPENDART_PENDING_TIMEOUT_SECONDS = tostring(var.pending_timeout_seconds)
  } : null
  sensitive = true
}

output "worker_function_name" {
  description = "Worker function name only in runtime stage."
  value       = local.runtime ? aws_lambda_function.worker[0].function_name : null
}

output "resource_contract" {
  description = "Non-execution design contract."
  value = {
    disabled_managed_resources  = 0
    bootstrap_managed_resources = 8
    runtime_managed_resources   = 11
    vpc_attachment              = false
    nat_gateway                 = false
    company_database_access     = false
    score_effect                = "NONE"
  }
}
