locals {
  metric_prefix = replace(var.name_prefix, "-", "_")

  required_tags = {
    jk_layer    = "tobe"
    control_id  = "T.6.1,T.6.2"
    gap_id      = "NF-06,NF-05"
    evidence_id = "EXPECTED-EDGE-WAF-RATE"
    status      = "PROPOSED_NOT_DEPLOYED"
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
