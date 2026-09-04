variable "enable" {
  description = "Master safety switch. False creates no resources in this proposal."
  type        = bool
  default     = false
}

variable "enable_edge" {
  description = "Select the proposed CloudFront-scope WAF/rate-limit component; effective only when enable=true."
  type        = bool
  default     = false
}

variable "enable_bedrock_boundary" {
  description = "Select the proposed Bedrock guardrail and broker-only IAM component; effective only when enable=true."
  type        = bool
  default     = false
}

variable "enable_observability" {
  description = "Select the proposed metadata-only log/evidence component; effective only when enable=true."
  type        = bool
  default     = false
}

variable "activation_acknowledgement" {
  description = "Human gate acknowledgement. The default is deliberately non-authorizing."
  type        = string
  default     = "PROPOSED_NOT_DEPLOYED"
  sensitive   = true

  validation {
    condition = contains([
      "PROPOSED_NOT_DEPLOYED",
      "JCAREER_TOBE_AI_SECURITY_APPROVED",
    ], var.activation_acknowledgement)
    error_message = "activation_acknowledgement must remain non-authorizing or use the exact approved phrase."
  }
}

variable "approval_ref" {
  description = "Pseudonymous reference to a separately reviewed, plan-bound approval record."
  type        = string
  default     = ""

  validation {
    condition = (
      var.approval_ref == "" ||
      can(regex("^APPROVAL-[A-Z0-9_-]{8,64}$", var.approval_ref))
    )
    error_message = "approval_ref must be empty or use APPROVAL-<pseudonymous-ref>."
  }
}

variable "aws_region" {
  description = "Region for Bedrock and the metadata/evidence control plane."
  type        = string
  default     = "ap-northeast-2"

  validation {
    condition     = var.aws_region == "ap-northeast-2"
    error_message = "This proposal is intentionally restricted to ap-northeast-2."
  }
}

variable "name_prefix" {
  description = "Lowercase prefix for proposed resources."
  type        = string
  default     = "jcareer-tobe-ai-sec"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,23}$", var.name_prefix))
    error_message = "name_prefix must be 3..24 lowercase letters, digits, or hyphens and start with a letter."
  }
}

variable "exact_model_id" {
  description = "One reviewed Bedrock foundation-model ID. Empty while the proposal is disabled; wildcards are forbidden."
  type        = string
  default     = ""

  validation {
    condition = (
      var.exact_model_id == "" ||
      (
        can(regex("^[a-z0-9][a-z0-9._:-]{2,190}$", var.exact_model_id)) &&
        !strcontains(var.exact_model_id, "*")
      )
    )
    error_message = "exact_model_id must be empty or one exact foundation-model ID without wildcards."
  }
}

variable "broker_role_name" {
  description = "Existing capability-broker workload role name; no role identifier is committed in this proposal."
  type        = string
  default     = ""

  validation {
    condition     = var.broker_role_name == "" || can(regex("^[A-Za-z0-9+=,.@_-]{1,64}$", var.broker_role_name))
    error_message = "broker_role_name must be empty or a valid IAM role name."
  }
}

variable "gateway_role_name" {
  description = "Existing LLM Gateway workload role name that receives an explicit direct-Bedrock deny."
  type        = string
  default     = ""

  validation {
    condition     = var.gateway_role_name == "" || can(regex("^[A-Za-z0-9+=,.@_-]{1,64}$", var.gateway_role_name))
    error_message = "gateway_role_name must be empty or a valid IAM role name."
  }
}

variable "waf_request_limit" {
  description = "Maximum requests per source IP in the configured WAF evaluation window. This is not a tenant quota."
  type        = number
  default     = 300

  validation {
    condition     = var.waf_request_limit >= 10 && var.waf_request_limit <= 10000
    error_message = "waf_request_limit must be between 10 and 10000."
  }
}

variable "waf_evaluation_window_seconds" {
  description = "AWS WAF rate aggregation window."
  type        = number
  default     = 300

  validation {
    condition     = contains([60, 120, 300, 600], var.waf_evaluation_window_seconds)
    error_message = "waf_evaluation_window_seconds must be 60, 120, 300, or 600."
  }
}

variable "log_retention_days" {
  description = "Bounded retention for metadata-only application and WAF security logs."
  type        = number
  default     = 30

  validation {
    condition     = contains([7, 14, 30, 60, 90], var.log_retention_days)
    error_message = "log_retention_days must be 7, 14, 30, 60, or 90."
  }
}

variable "evidence_lock_days" {
  description = "Default S3 Object Lock compliance retention for de-identified metadata evidence."
  type        = number
  default     = 90

  validation {
    condition     = var.evidence_lock_days >= 30 && var.evidence_lock_days <= 365
    error_message = "evidence_lock_days must be between 30 and 365."
  }
}

variable "evidence_expiration_days" {
  description = "Lifecycle expiry after the Object Lock period; requires retention-owner approval before activation."
  type        = number
  default     = 365

  validation {
    condition     = var.evidence_expiration_days >= 90 && var.evidence_expiration_days <= 2555
    error_message = "evidence_expiration_days must be between 90 and 2555."
  }
}

variable "additional_tags" {
  description = "Optional non-authoritative tags. Reserved TO-BE trace tags cannot be overridden."
  type        = map(string)
  default     = {}

  validation {
    condition = length(setintersection(
      toset(keys(var.additional_tags)),
      toset(["jk_layer", "control_id", "gap_id", "evidence_id", "status"]),
    )) == 0
    error_message = "additional_tags cannot set reserved TO-BE trace/status keys."
  }
}
