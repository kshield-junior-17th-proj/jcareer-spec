output "guardrail_id" {
  description = "Proposed guardrail ID; null when disabled."
  value       = try(aws_bedrock_guardrail.bounded_explanation[0].guardrail_id, null)
}

output "guardrail_version" {
  description = "Proposed immutable guardrail version; null when disabled."
  value       = try(aws_bedrock_guardrail_version.bounded_explanation[0].version, null)
}

output "broker_policy_name" {
  description = "Name of the proposed exact-model policy; null when disabled."
  value       = try(aws_iam_policy.broker_exact_model[0].name, null)
}

output "gateway_deny_policy_name" {
  description = "Name of the proposed Gateway direct-Bedrock deny policy; null when disabled."
  value       = try(aws_iam_policy.gateway_direct_bedrock_deny[0].name, null)
}
