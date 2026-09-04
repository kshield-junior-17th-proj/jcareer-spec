output "proposal_status" {
  description = "A status label, never deployment or control-effectiveness evidence."
  value       = var.enable ? "PROPOSED_ACTIVATION_REQUESTED_NOT_VERIFIED" : "PROPOSED_NOT_DEPLOYED"
}

output "selected_components" {
  description = "Components selected by configuration; selection does not prove creation or association."
  value       = local.selected_components
}

output "edge" {
  description = "Proposed edge identifiers. Null values mean disabled; non-null Terraform outputs still require live verification."
  value = {
    web_acl_id       = module.edge.web_acl_id
    web_acl_name     = module.edge.web_acl_name
    waf_log_group    = module.edge.waf_log_group_name
    association_mode = module.edge.association_mode
  }
}

output "bedrock_boundary" {
  description = "Proposed guardrail/policy identifiers without account-specific role or resource identifiers."
  value = {
    guardrail_id             = module.bedrock_boundary.guardrail_id
    guardrail_version        = module.bedrock_boundary.guardrail_version
    broker_policy_name       = module.bedrock_boundary.broker_policy_name
    gateway_deny_policy_name = module.bedrock_boundary.gateway_deny_policy_name
  }
}

output "metadata_observability" {
  description = "Proposed metadata/evidence resource names; these are not Evidence Desk or proof of runtime use."
  value = {
    log_group_names   = module.metadata_observability.log_group_names
    evidence_bucket   = module.metadata_observability.evidence_bucket_name
    evidence_table    = module.metadata_observability.evidence_table_name
    kms_alias         = module.metadata_observability.kms_alias_name
    permitted_fields  = module.metadata_observability.permitted_metadata_fields
  }
}
