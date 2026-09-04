output "web_acl_id" {
  description = "Proposed ACL identifier; null when disabled."
  value       = try(aws_wafv2_web_acl.edge[0].id, null)
}

output "web_acl_name" {
  description = "Proposed ACL name; null when disabled."
  value       = try(aws_wafv2_web_acl.edge[0].name, null)
}

output "waf_log_group_name" {
  description = "Proposed WAF log group name; null when disabled."
  value       = try(aws_cloudwatch_log_group.waf[0].name, null)
}

output "association_mode" {
  description = "The existing CloudFront distribution must consume the ACL in a separately reviewed stack change."
  value       = "EXTERNAL_REVIEWED_CLOUDFRONT_BINDING_REQUIRED"
}
