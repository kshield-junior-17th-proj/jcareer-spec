output "deployment_stage" {
  value = var.deployment_stage
}

output "endpoint_instance_ids" {
  description = "SSM targets for the three Windows endpoints."
  value       = local.enabled ? aws_instance.windows[*].id : []
  sensitive   = true
}

output "endpoint_security_group_id" {
  description = "Security group that must be the sole group on every Windows endpoint."
  value       = local.enabled ? aws_security_group.endpoints[0].id : null
  sensitive   = true
}

output "endpoint_contract" {
  value = {
    disabled_managed_resources = 0
    windows_three_resources    = 9
    requested_windows_count    = 3
    requested_macos_count      = 3
    deployed_macos_count       = 0
    instance_type              = "t3.small"
    inbound_rules              = 0
    access                     = "SSM_TUNNELED_RDP_OR_FLEET_MANAGER"
    auto_stop_minutes          = var.auto_stop_minutes
  }
}
