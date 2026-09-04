output "web_acl_id" {
  description = "Proposed ACL identifier; null when disabled."
  value       = try(aws_wafv2_web_acl.edge[0].id, null)
}

output "web_acl_name" {
  description = "Proposed ACL name; null when disabled."
  value       = try(aws_wafv2_web_acl.edge[0].name, null)
}

output "web_acl_arn" {
  description = "Exact ACL ARN for the existing distribution owner's web_acl_id input; null when disabled."
  value       = try(aws_wafv2_web_acl.edge[0].arn, null)
}

output "waf_log_group_name" {
  description = "Proposed WAF log group name; null when disabled."
  value       = try(aws_cloudwatch_log_group.waf[0].name, null)
}

output "association_mode" {
  description = "Binding state contract. This module verifies but never mutates/imports the existing distribution."
  value = (
    !var.enable ? "PROPOSED_NOT_DEPLOYED" :
    var.verify_cloudfront_binding ? "LIVE_READ_BACK_REQUESTED_NOT_RECEIPT" :
    "EXTERNAL_REVIEWED_CLOUDFRONT_BINDING_REQUIRED"
  )
}

output "owner_stack_binding" {
  description = "Exact non-secret handoff contract for the distribution owner stack."
  value = {
    distribution_id_hash = var.cloudfront_distribution_id == "" ? null : sha256(var.cloudfront_distribution_id)
    web_acl_id_input     = try(aws_wafv2_web_acl.edge[0].arn, null)
    binding_ref          = var.cloudfront_owner_binding_ref == "" ? null : var.cloudfront_owner_binding_ref
    verification_enabled = var.verify_cloudfront_binding
  }
}
