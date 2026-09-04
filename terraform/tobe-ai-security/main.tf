locals {
  selected_components = compact([
    var.enable_edge ? "edge" : "",
    var.enable_bedrock_boundary ? "bedrock-boundary" : "",
    var.enable_observability ? "metadata-observability" : "",
  ])

  edge_enabled          = var.enable && var.enable_edge
  bedrock_enabled       = var.enable && var.enable_bedrock_boundary
  observability_enabled = var.enable && var.enable_observability
}

# This state-only gate adds no AWS object. It fails closed if somebody changes
# enable without the separate human authority described in README.md.
resource "terraform_data" "activation_gate" {
  count = var.enable ? 1 : 0

  input = {
    approval_ref = var.approval_ref
    components   = local.selected_components
    status       = "PROPOSED_ACTIVATION_REQUESTED_NOT_VERIFIED"
  }

  lifecycle {
    precondition {
      condition     = length(local.selected_components) > 0
      error_message = "enable=true requires at least one explicitly selected component."
    }

    precondition {
      condition = (
        var.activation_acknowledgement == "JCAREER_TOBE_AI_SECURITY_APPROVED" &&
        can(regex("^APPROVAL-[A-Z0-9_-]{8,64}$", var.approval_ref))
      )
      error_message = "Activation requires the exact acknowledgement and a separately reviewed approval reference."
    }

    precondition {
      condition = (
        !local.bedrock_enabled ||
        (
          var.exact_model_id != "" &&
          var.broker_role_name != "" &&
          var.gateway_role_name != "" &&
          var.broker_role_name != var.gateway_role_name
        )
      )
      error_message = "The Bedrock boundary requires one exact model ID and distinct existing Broker/Gateway roles."
    }

    precondition {
      condition     = !local.observability_enabled || var.evidence_expiration_days > var.evidence_lock_days
      error_message = "Evidence expiration must be later than the Object Lock retention period."
    }
  }
}

module "edge" {
  source = "./modules/edge"

  providers = {
    aws = aws.cloudfront_control_plane
  }

  enable                        = local.edge_enabled
  activation_acknowledgement   = var.activation_acknowledgement
  approval_ref                  = var.approval_ref
  name_prefix                   = var.name_prefix
  request_limit                 = var.waf_request_limit
  evaluation_window_seconds     = var.waf_evaluation_window_seconds
  log_retention_days            = var.log_retention_days
  additional_tags               = var.additional_tags

  depends_on = [terraform_data.activation_gate]
}

module "bedrock_boundary" {
  source = "./modules/bedrock-boundary"

  enable                      = local.bedrock_enabled
  activation_acknowledgement = var.activation_acknowledgement
  approval_ref                = var.approval_ref
  aws_region                  = var.aws_region
  name_prefix                 = var.name_prefix
  exact_model_id              = var.exact_model_id
  broker_role_name            = var.broker_role_name
  gateway_role_name           = var.gateway_role_name
  additional_tags             = var.additional_tags

  depends_on = [terraform_data.activation_gate]
}

module "metadata_observability" {
  source = "./modules/metadata-observability"

  enable                      = local.observability_enabled
  activation_acknowledgement = var.activation_acknowledgement
  approval_ref                = var.approval_ref
  name_prefix                 = var.name_prefix
  log_retention_days          = var.log_retention_days
  evidence_lock_days          = var.evidence_lock_days
  evidence_expiration_days    = var.evidence_expiration_days
  additional_tags             = var.additional_tags

  depends_on = [terraform_data.activation_gate]
}
