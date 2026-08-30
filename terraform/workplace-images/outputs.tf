output "deployment_stage" {
  value       = var.deployment_stage
  description = "Current stage; disabled creates no resources."
}

output "pipeline_arn" {
  value       = local.enabled ? aws_imagebuilder_image_pipeline.windows[0].arn : null
  description = "Manual image pipeline definition; not an image build receipt."
  sensitive   = true
}

output "lifecycle_execution_role_name" {
  value       = local.enabled ? aws_iam_role.lifecycle[0].name : null
  description = "Role name consumed only by a separately approved image artifact cleanup operation."
  sensitive   = true
}

output "image_contract" {
  description = "Non-execution endpoint image contract."
  value = {
    disabled_managed_resources = 0
    definition_resources       = 12
    build_instance_type        = "t3.small"
    automatic_schedule         = false
    image_build_invoked        = false
    windows_11_claimed         = false
    macos_resources            = 0
    consultant_endpoint_count  = 0
  }
}
