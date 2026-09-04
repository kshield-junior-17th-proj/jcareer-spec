locals {
  metric_prefix = replace(var.name_prefix, "-", "_")

  required_tags = {
    jk_layer    = "tobe"
    control_id  = "T.6.1,T.6.2"
    gap_id      = "NF-06,NF-05"
    evidence_id = "EXPECTED-EDGE-WAF-RATE"
    status      = "PROPOSED_CONTROL_NOT_VERIFIED"
  }

  tags = merge(var.additional_tags, local.required_tags, {
    approval_ref = var.approval_ref
    component    = "edge-waf-rate-limit"
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
      error_message = "The edge module requires explicit human approval before activation."
    }

    precondition {
      condition = (
        var.cloudfront_distribution_id != "" &&
        can(regex("^EDGE-BINDING-[A-Z0-9_-]{8,64}$", var.cloudfront_owner_binding_ref))
      )
      error_message = "The edge module requires an exact distribution ID and a separately reviewed owner-stack binding reference."
    }
  }
}

resource "aws_cloudwatch_log_group" "waf" {
  count = var.enable ? 1 : 0

  name              = "aws-waf-logs-${var.name_prefix}-edge"
  retention_in_days = var.log_retention_days

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-waf-logs"
  })

  depends_on = [terraform_data.activation_gate]
}

resource "aws_wafv2_web_acl" "edge" {
  count = var.enable ? 1 : 0

  name        = "${var.name_prefix}-edge"
  description = "PROPOSED / NOT DEPLOYED CloudFront edge policy for bounded synthetic assessment traffic."
  scope       = "CLOUDFRONT"

  default_action {
    allow {}
  }

  rule {
    name     = "source-ip-rate-limit"
    priority = 10

    action {
      block {}
    }

    statement {
      rate_based_statement {
        aggregate_key_type    = "IP"
        evaluation_window_sec = var.evaluation_window_seconds
        limit                 = var.request_limit
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${local.metric_prefix}_ip_rate_limit"
      sampled_requests_enabled   = false
    }
  }

  rule {
    name     = "aws-managed-common"
    priority = 20

    override_action {
      count {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${local.metric_prefix}_managed_common"
      sampled_requests_enabled   = false
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${local.metric_prefix}_edge"
    sampled_requests_enabled   = false
  }

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-edge"
  })

  depends_on = [terraform_data.activation_gate]
}

# Only blocked/count records are retained. Request headers, cookies, query
# strings, and URI paths are redacted. Source IP remains security telemetry and
# requires the documented privacy/retention approval before activation.
resource "aws_wafv2_web_acl_logging_configuration" "edge" {
  count = var.enable ? 1 : 0

  log_destination_configs = [aws_cloudwatch_log_group.waf[0].arn]
  resource_arn            = aws_wafv2_web_acl.edge[0].arn

  logging_filter {
    default_behavior = "DROP"

    filter {
      behavior    = "KEEP"
      requirement = "MEETS_ANY"

      condition {
        action_condition {
          action = "BLOCK"
        }
      }

      condition {
        action_condition {
          action = "COUNT"
        }
      }
    }
  }

  redacted_fields {
    single_header {
      name = "authorization"
    }
  }

  redacted_fields {
    single_header {
      name = "cookie"
    }
  }

  redacted_fields {
    query_string {}
  }

  redacted_fields {
    uri_path {}
  }
}

# CloudFront is the exception to aws_wafv2_web_acl_association: its owning
# aws_cloudfront_distribution resource must set web_acl_id. This data read is a
# second-pass verification gate after that separately reviewed owner-stack
# change. It never mutates or imports the existing distribution.
data "aws_cloudfront_distribution" "target" {
  count = var.enable && var.verify_cloudfront_binding ? 1 : 0

  id = var.cloudfront_distribution_id
}

resource "terraform_data" "cloudfront_binding_verification" {
  count = var.enable && var.verify_cloudfront_binding ? 1 : 0

  input = {
    binding_ref          = var.cloudfront_owner_binding_ref
    distribution_id_hash = sha256(var.cloudfront_distribution_id)
    verification_state   = "LIVE_READ_REQUIRED_NOT_DEPLOYMENT_RECEIPT"
  }

  lifecycle {
    precondition {
      condition     = data.aws_cloudfront_distribution.target[0].status == "Deployed"
      error_message = "The target CloudFront distribution must report Deployed before edge binding verification."
    }

    precondition {
      condition     = data.aws_cloudfront_distribution.target[0].web_acl_id == aws_wafv2_web_acl.edge[0].arn
      error_message = "The target distribution web_acl_id does not match the proposed edge ACL ARN. Apply the separately reviewed owner-stack change first."
    }
  }

  depends_on = [aws_wafv2_web_acl_logging_configuration.edge]
}
