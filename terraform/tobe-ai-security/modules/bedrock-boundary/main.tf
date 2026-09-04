locals {
  approval_input_sha256 = sha256(jsonencode({
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

  required_tags = {
    jk_layer    = "tobe"
    control_id  = "T.1.1,T.1.2,T.1.3,T.3.1,T.3.2,T.3.3"
    gap_id      = "NF-03,NF-05,NF-04"
    evidence_id = "EXPECTED-BROKER-GUARDRAIL-DENY"
    status      = "PROPOSED_CONTROL_NOT_VERIFIED"
  }

  tags = merge(var.additional_tags, local.required_tags, {
    approval_ref = var.approval_ref
    component    = "bedrock-broker-boundary"
  })
}

resource "terraform_data" "activation_gate" {
  count = var.enable ? 1 : 0

  lifecycle {
    precondition {
      condition = (
        var.activation_acknowledgement == "JCAREER_TOBE_AI_SECURITY_APPROVED" &&
        can(regex("^APPROVAL-[A-Z0-9_-]{8,64}$", var.approval_ref))
      )
      error_message = "The Bedrock boundary requires explicit human approval before activation."
    }

    precondition {
      condition = (
        var.exact_model_id != "" &&
        !strcontains(var.exact_model_id, "*") &&
        length(var.bedrock_invocation_resource_arns) >= 1 &&
        length(var.bedrock_invocation_resource_arns) <= 8 &&
        anytrue([for resource_arn in var.bedrock_invocation_resource_arns : endswith(resource_arn, "/${var.exact_model_id}")]) &&
        var.broker_function_arn != "" &&
        var.broker_code_sha256 != "" &&
        var.broker_role_name != "" &&
        var.broker_role_arn != "" &&
        var.broker_role_unique_id != "" &&
        var.gateway_role_name != "" &&
        var.gateway_role_arn != "" &&
        var.gateway_role_unique_id != "" &&
        endswith(var.broker_role_arn, "/${var.broker_role_name}") &&
        endswith(var.gateway_role_arn, "/${var.gateway_role_name}") &&
        var.broker_role_name != var.gateway_role_name &&
        var.broker_role_arn != var.gateway_role_arn &&
        var.broker_role_unique_id != var.gateway_role_unique_id
      )
      error_message = "Use one exact model ID represented by the ARN set, 1..8 exact Bedrock model/profile ARNs, one published-version Broker Lambda ARN/CodeSha256, and distinct role names/ARNs/unique IDs."
    }

    precondition {
      condition     = var.bedrock_approval_binding_sha256 == local.approval_input_sha256
      error_message = "The Bedrock model ID/ARN set, Broker version/code, role identities, and region must match the single SHA-256 bound into the reviewed approval record."
    }
  }
}

resource "aws_bedrock_guardrail" "bounded_explanation" {
  count = var.enable ? 1 : 0

  name                      = "${var.name_prefix}-bounded-explanation"
  description               = "PROPOSED / NOT DEPLOYED guardrail for qualitative explanation only; never final score or hiring decision."
  blocked_input_messaging   = "The request cannot be processed under the approved AI safety policy."
  blocked_outputs_messaging = "The response was withheld under the approved AI safety policy."

  content_policy_config {
    filters_config {
      input_strength  = "HIGH"
      output_strength = "HIGH"
      type            = "PROMPT_ATTACK"
    }

    filters_config {
      input_strength  = "MEDIUM"
      output_strength = "HIGH"
      type            = "HATE"
    }

    filters_config {
      input_strength  = "MEDIUM"
      output_strength = "HIGH"
      type            = "INSULTS"
    }

    filters_config {
      input_strength  = "MEDIUM"
      output_strength = "HIGH"
      type            = "MISCONDUCT"
    }

    filters_config {
      input_strength  = "HIGH"
      output_strength = "HIGH"
      type            = "SEXUAL"
    }

    filters_config {
      input_strength  = "HIGH"
      output_strength = "HIGH"
      type            = "VIOLENCE"
    }
  }

  sensitive_information_policy_config {
    pii_entities_config {
      action = "ANONYMIZE"
      type   = "ADDRESS"
    }

    pii_entities_config {
      action = "ANONYMIZE"
      type   = "EMAIL"
    }

    pii_entities_config {
      action = "ANONYMIZE"
      type   = "NAME"
    }

    pii_entities_config {
      action = "ANONYMIZE"
      type   = "PHONE"
    }

    pii_entities_config {
      action = "BLOCK"
      type   = "AWS_ACCESS_KEY"
    }

    pii_entities_config {
      action = "BLOCK"
      type   = "AWS_SECRET_KEY"
    }

    pii_entities_config {
      action = "BLOCK"
      type   = "PASSWORD"
    }
  }

  word_policy_config {
    managed_word_lists_config {
      type = "PROFANITY"
    }
  }

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-bounded-explanation"
  })

  depends_on = [terraform_data.activation_gate]
}

resource "aws_bedrock_guardrail_version" "bounded_explanation" {
  count = var.enable ? 1 : 0

  description   = "PROPOSED immutable candidate; human evaluation required before use."
  guardrail_arn = aws_bedrock_guardrail.bounded_explanation[0].guardrail_arn
  # Preserve every version referenced by an approval/evidence record. A
  # dedicated retirement change may remove an obsolete version after review.
  skip_destroy = true
}

resource "aws_iam_policy" "broker_exact_model" {
  count = var.enable ? 1 : 0

  name        = "${var.name_prefix}-broker-exact-model"
  description = "PROPOSED broker-only invocation of one exact Bedrock model and this guardrail."
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "InvokeOnlyReviewedBedrockResources"
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        Resource = sort(tolist(var.bedrock_invocation_resource_arns))
        Condition = {
          StringEquals = {
            "bedrock:GuardrailIdentifier" = "${aws_bedrock_guardrail.bounded_explanation[0].guardrail_arn}:${aws_bedrock_guardrail_version.bounded_explanation[0].version}"
            "aws:RequestedRegion"         = var.aws_region
          }
        }
      },
      {
        Sid         = "DenyOtherFoundationModels"
        Effect      = "Deny"
        Action      = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        NotResource = sort(tolist(var.bedrock_invocation_resource_arns))
      },
      {
        Sid      = "DenyMissingOrWrongGuardrailVersion"
        Effect   = "Deny"
        Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        Resource = sort(tolist(var.bedrock_invocation_resource_arns))
        Condition = {
          StringNotEquals = {
            "bedrock:GuardrailIdentifier" = "${aws_bedrock_guardrail.bounded_explanation[0].guardrail_arn}:${aws_bedrock_guardrail_version.bounded_explanation[0].version}"
          }
        }
      },
      {
        Sid      = "ApplyExactlyThisGuardrail"
        Effect   = "Allow"
        Action   = ["bedrock:ApplyGuardrail"]
        Resource = aws_bedrock_guardrail.bounded_explanation[0].guardrail_arn
        Condition = {
          StringEquals = {
            "aws:RequestedRegion" = var.aws_region
          }
        }
      },
    ]
  })

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-broker-exact-model"
  })

  depends_on = [terraform_data.activation_gate]
}

resource "aws_iam_role_policy_attachment" "broker_exact_model" {
  count = var.enable ? 1 : 0

  policy_arn = aws_iam_policy.broker_exact_model[0].arn
  role       = var.broker_role_name
}

# The Gateway receives exactly one positive AWS effect: invoke the reviewed
# Capability Broker Lambda. It receives no model/profile permission.
resource "aws_iam_policy" "gateway_invoke_broker" {
  count = var.enable ? 1 : 0

  name        = "${var.name_prefix}-gateway-invoke-broker"
  description = "PROPOSED LLM Gateway permission to invoke exactly one Capability Broker Lambda."
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "InvokeExactCapabilityBroker"
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = var.broker_function_arn
    }]
  })

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-gateway-invoke-broker"
  })

  depends_on = [terraform_data.activation_gate]
}

resource "aws_iam_role_policy_attachment" "gateway_invoke_broker" {
  count = var.enable ? 1 : 0

  policy_arn = aws_iam_policy.gateway_invoke_broker[0].arn
  role       = var.gateway_role_name
}

# This identity-policy deny makes the intended negative boundary explicit. It
# does not replace an organization-level SCP or a live IAM simulation test.
resource "aws_iam_policy" "gateway_direct_bedrock_deny" {
  count = var.enable ? 1 : 0

  name        = "${var.name_prefix}-gateway-bedrock-deny"
  description = "PROPOSED explicit deny for direct LLM Gateway Bedrock model and guardrail actions."
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "DenyDirectBedrockUse"
      Effect   = "Deny"
      Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:ApplyGuardrail"]
      Resource = "*"
    }]
  })

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-gateway-bedrock-deny"
  })

  depends_on = [terraform_data.activation_gate]
}

resource "aws_iam_role_policy_attachment" "gateway_direct_bedrock_deny" {
  count = var.enable ? 1 : 0

  policy_arn = aws_iam_policy.gateway_direct_bedrock_deny[0].arn
  role       = var.gateway_role_name
}
