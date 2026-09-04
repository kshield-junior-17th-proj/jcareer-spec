locals {
  selected_components = compact([
    var.enable_edge ? "edge" : "",
    var.enable_bedrock_boundary ? "bedrock-boundary" : "",
    var.enable_observability ? "metadata-observability" : "",
  ])

  edge_enabled            = var.enable && var.enable_edge
  bedrock_enabled         = var.enable && var.enable_bedrock_boundary
  observability_enabled   = var.enable && var.enable_observability
  role_provenance_enabled = local.bedrock_enabled || local.observability_enabled
  publisher_roles = {
    "llm-gateway"       = var.gateway_role_name
    "capability-broker" = var.broker_role_name
  }
  broker_function_segments = split(":", var.broker_function_arn)
  broker_function_name     = try(local.broker_function_segments[6], "")
  broker_function_version  = try(local.broker_function_segments[7], "")
  bedrock_approval_input_sha256 = sha256(jsonencode({
    aws_region                       = var.aws_region
    bedrock_invocation_resource_arns = sort(tolist(var.bedrock_invocation_resource_arns))
    broker_code_sha256               = var.broker_code_sha256
    broker_function_arn              = var.broker_function_arn
    broker_role_arn                  = var.broker_role_arn
    broker_role_name                 = var.broker_role_name
    broker_role_unique_id            = var.broker_role_unique_id
    exact_model_id                   = var.exact_model_id
    gateway_role_arn                 = var.gateway_role_arn
    gateway_role_name                = var.gateway_role_name
    gateway_role_unique_id           = var.gateway_role_unique_id
  }))
}

# These read-backs are proposal activation gates, not deployment receipts. They
# run only for an explicitly enabled review and detect same-name IAM role
# replacement plus Lambda alias/$LATEST drift before any attachment is planned.
data "aws_iam_role" "broker" {
  count = local.role_provenance_enabled ? 1 : 0

  name = var.broker_role_name
}

data "aws_iam_role" "gateway" {
  count = local.role_provenance_enabled ? 1 : 0

  name = var.gateway_role_name
}

data "aws_lambda_function" "broker_published" {
  count = local.bedrock_enabled ? 1 : 0

  function_name = local.broker_function_name
  qualifier     = local.broker_function_version
}

resource "terraform_data" "role_provenance_gate" {
  count = local.role_provenance_enabled ? 1 : 0

  input = {
    broker_identity_sha256  = sha256("${var.broker_role_arn}:${var.broker_role_unique_id}")
    gateway_identity_sha256 = sha256("${var.gateway_role_arn}:${var.gateway_role_unique_id}")
    status                  = "LIVE_READBACK_REQUIRED_NOT_DEPLOYMENT_RECEIPT"
  }

  lifecycle {
    precondition {
      condition = (
        data.aws_iam_role.broker[0].arn == var.broker_role_arn &&
        data.aws_iam_role.broker[0].unique_id == var.broker_role_unique_id
      )
      error_message = "Capability Broker role ARN/unique ID read-back differs from the reviewed identity."
    }

    precondition {
      condition = (
        data.aws_iam_role.gateway[0].arn == var.gateway_role_arn &&
        data.aws_iam_role.gateway[0].unique_id == var.gateway_role_unique_id
      )
      error_message = "LLM Gateway role ARN/unique ID read-back differs from the reviewed identity."
    }
  }
}

resource "terraform_data" "broker_code_provenance_gate" {
  count = local.bedrock_enabled ? 1 : 0

  input = {
    code_sha256     = var.broker_code_sha256
    function_arn    = var.broker_function_arn
    approval_sha256 = var.bedrock_approval_binding_sha256
    status          = "LIVE_READBACK_REQUIRED_NOT_DEPLOYMENT_RECEIPT"
  }

  lifecycle {
    precondition {
      condition = (
        data.aws_lambda_function.broker_published[0].qualified_arn == var.broker_function_arn &&
        data.aws_lambda_function.broker_published[0].version == local.broker_function_version &&
        data.aws_lambda_function.broker_published[0].code_sha256 == var.broker_code_sha256
      )
      error_message = "Published Broker Lambda ARN/version/CodeSha256 read-back differs from the reviewed identity."
    }
  }
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
          length(var.bedrock_invocation_resource_arns) >= 1 &&
          length(var.bedrock_invocation_resource_arns) <= 8 &&
          anytrue([for resource_arn in var.bedrock_invocation_resource_arns : endswith(resource_arn, "/${var.exact_model_id}")]) &&
          var.broker_function_arn != "" &&
          var.broker_code_sha256 != "" &&
          var.broker_role_name != "" &&
          var.gateway_role_name != "" &&
          var.broker_role_name != var.gateway_role_name
        )
      )
      error_message = "The Bedrock boundary requires one exact model ID represented by the ARN set, 1..8 exact resource ARNs, one published-version Broker Lambda ARN with CodeSha256, and distinct existing Broker/Gateway roles."
    }

    precondition {
      condition     = !local.bedrock_enabled || var.bedrock_approval_binding_sha256 == local.bedrock_approval_input_sha256
      error_message = "The Bedrock model ID, exact ARN set, Broker function, roles, and region do not match the reviewed approval digest."
    }

    precondition {
      condition = (
        !local.edge_enabled ||
        (
          var.cloudfront_distribution_id != "" &&
          can(regex("^EDGE-BINDING-[A-Z0-9_-]{8,64}$", var.cloudfront_owner_binding_ref))
        )
      )
      error_message = "The edge component requires an exact distribution ID and a separately reviewed owner-stack binding reference."
    }

    precondition {
      condition     = !var.verify_cloudfront_binding || local.edge_enabled
      error_message = "verify_cloudfront_binding requires the edge component to be enabled."
    }

    precondition {
      condition     = !local.observability_enabled || var.evidence_expiration_days > var.evidence_lock_days
      error_message = "Evidence expiration must be later than the Object Lock retention period."
    }

    precondition {
      condition = (
        !local.role_provenance_enabled ||
        (
          var.broker_role_arn != "" &&
          var.broker_role_unique_id != "" &&
          var.gateway_role_arn != "" &&
          var.gateway_role_unique_id != "" &&
          endswith(var.broker_role_arn, "/${var.broker_role_name}") &&
          endswith(var.gateway_role_arn, "/${var.gateway_role_name}") &&
          var.broker_role_arn != var.gateway_role_arn &&
          var.broker_role_unique_id != var.gateway_role_unique_id
        )
      )
      error_message = "Bedrock or observability activation requires distinct exact Broker/Gateway role ARNs and unique IDs matching the reviewed role names."
    }
  }
}

module "edge" {
  source = "./modules/edge"

  providers = {
    aws = aws.cloudfront_control_plane
  }

  enable                       = local.edge_enabled
  activation_acknowledgement   = var.activation_acknowledgement
  approval_ref                 = var.approval_ref
  cloudfront_distribution_id   = var.cloudfront_distribution_id
  cloudfront_owner_binding_ref = var.cloudfront_owner_binding_ref
  verify_cloudfront_binding    = var.verify_cloudfront_binding
  name_prefix                  = var.name_prefix
  request_limit                = var.waf_request_limit
  evaluation_window_seconds    = var.waf_evaluation_window_seconds
  log_retention_days           = var.log_retention_days
  additional_tags              = var.additional_tags

  depends_on = [terraform_data.activation_gate]
}

module "bedrock_boundary" {
  source = "./modules/bedrock-boundary"

  enable                           = local.bedrock_enabled
  activation_acknowledgement       = var.activation_acknowledgement
  approval_ref                     = var.approval_ref
  aws_region                       = var.aws_region
  name_prefix                      = var.name_prefix
  exact_model_id                   = var.exact_model_id
  bedrock_invocation_resource_arns = var.bedrock_invocation_resource_arns
  broker_function_arn              = var.broker_function_arn
  broker_code_sha256               = var.broker_code_sha256
  bedrock_approval_binding_sha256  = var.bedrock_approval_binding_sha256
  broker_role_name                 = var.broker_role_name
  broker_role_arn                  = var.broker_role_arn
  broker_role_unique_id            = var.broker_role_unique_id
  gateway_role_name                = var.gateway_role_name
  gateway_role_arn                 = var.gateway_role_arn
  gateway_role_unique_id           = var.gateway_role_unique_id
  additional_tags                  = var.additional_tags

  depends_on = [
    terraform_data.activation_gate,
    terraform_data.role_provenance_gate,
    terraform_data.broker_code_provenance_gate,
  ]
}

module "metadata_observability" {
  source = "./modules/metadata-observability"

  enable                          = local.observability_enabled
  activation_acknowledgement      = var.activation_acknowledgement
  approval_ref                    = var.approval_ref
  aws_region                      = var.aws_region
  name_prefix                     = var.name_prefix
  publisher_roles                 = local.publisher_roles
  log_retention_days              = var.log_retention_days
  guardrail_block_alarm_threshold = var.guardrail_block_alarm_threshold
  evidence_lock_days              = var.evidence_lock_days
  evidence_expiration_days        = var.evidence_expiration_days
  additional_tags                 = var.additional_tags

  depends_on = [
    terraform_data.activation_gate,
    terraform_data.role_provenance_gate,
  ]
}
