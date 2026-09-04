output "log_group_names" {
  description = "Proposed application metadata log groups; empty when disabled."
  value       = sort([for group in aws_cloudwatch_log_group.metadata : group.name])
}

output "evidence_bucket_name" {
  description = "Proposed metadata evidence bucket name; null when disabled."
  value       = try(aws_s3_bucket.evidence[0].id, null)
}

output "evidence_table_name" {
  description = "Proposed metadata evidence index name; null when disabled."
  value       = try(aws_dynamodb_table.evidence_index[0].name, null)
}

output "kms_alias_name" {
  description = "Proposed metadata evidence key alias; null when disabled."
  value       = try(aws_kms_alias.evidence[0].name, null)
}

output "permitted_metadata_fields" {
  description = "Normative application logging allowlist. Terraform cannot inspect emitted content; runtime tests remain mandatory."
  value       = local.permitted_metadata_fields
}
