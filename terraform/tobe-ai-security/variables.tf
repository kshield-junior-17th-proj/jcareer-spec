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

variable "cloudfront_distribution_id" {
  description = "Exact existing CloudFront distribution ID owned by the delivery stack. Required only when edge is enabled."
  type        = string
  default     = ""

  validation {
    condition = (
      var.cloudfront_distribution_id == "" ||
      can(regex("^[A-Z0-9]{8,32}$", var.cloudfront_distribution_id))
    )
    error_message = "cloudfront_distribution_id must be empty or an exact CloudFront distribution ID."
  }
}

variable "cloudfront_owner_binding_ref" {
  description = "Pseudonymous review reference for the owner-stack change that sets CloudFront web_acl_id."
  type        = string
  default     = ""

  validation {
    condition = (
      var.cloudfront_owner_binding_ref == "" ||
      can(regex("^EDGE-BINDING-[A-Z0-9_-]{8,64}$", var.cloudfront_owner_binding_ref))
    )
    error_message = "cloudfront_owner_binding_ref must be empty or EDGE-BINDING-<pseudonymous-ref>."
  }
}

variable "verify_cloudfront_binding" {
  description = "After the separate owner-stack change, read CloudFront and fail if web_acl_id is not this proposal ACL."
  type        = bool
  default     = false
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

variable "bedrock_invocation_resource_arns" {
  description = "Exact Bedrock inference target and reviewed destination model ARNs. Cross-region inference may require more than one ARN; wildcards are forbidden."
  type        = set(string)
  default     = []

  validation {
    condition = alltrue([
      for resource_arn in var.bedrock_invocation_resource_arns : (
        !strcontains(resource_arn, "*") &&
        can(regex("^arn:(aws|aws-us-gov|aws-cn):bedrock:[a-z0-9-]+:([0-9]{12})?:(foundation-model|inference-profile|application-inference-profile)/[A-Za-z0-9._:/-]+$", resource_arn))
      )
    ])
    error_message = "bedrock_invocation_resource_arns must contain only exact Bedrock model/profile ARNs without wildcards."
  }
}

variable "broker_function_arn" {
  description = "Exact published numeric Capability Broker Lambda version ARN that the LLM Gateway may invoke."
  type        = string
  default     = ""

  validation {
    condition = (
      var.broker_function_arn == "" ||
      (
        !strcontains(var.broker_function_arn, "*") &&
        can(regex("^arn:(aws|aws-us-gov|aws-cn):lambda:[a-z0-9-]+:[0-9]{12}:function:[A-Za-z0-9_-]{1,64}:[1-9][0-9]*$", var.broker_function_arn))
      )
    )
    error_message = "broker_function_arn must be empty or one exact numeric published Lambda version ARN without wildcards, aliases, or $LATEST."
  }
}

variable "broker_code_sha256" {
  description = "Base64-encoded 32-byte CodeSha256 expected from the exact published Broker Lambda version."
  type        = string
  default     = ""

  validation {
    condition     = var.broker_code_sha256 == "" || can(regex("^[A-Za-z0-9+/]{43}=$", var.broker_code_sha256))
    error_message = "broker_code_sha256 must be empty or the 44-character base64 Lambda CodeSha256 value."
  }
}

variable "bedrock_approval_binding_sha256" {
  description = "SHA-256 of the reviewed model ID/ARN set, Broker published version/CodeSha256, role names/ARNs/unique IDs, and region."
  type        = string
  default     = ""

  validation {
    condition = (
      var.bedrock_approval_binding_sha256 == "" ||
      can(regex("^[0-9a-f]{64}$", var.bedrock_approval_binding_sha256))
    )
    error_message = "bedrock_approval_binding_sha256 must be empty or 64 lowercase hexadecimal characters."
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

variable "guardrail_block_alarm_threshold" {
  description = "Blocked guardrail actions in one five-minute period that move the proposed metadata alarm to ALARM."
  type        = number
  default     = 5

  validation {
    condition     = var.guardrail_block_alarm_threshold >= 1 && var.guardrail_block_alarm_threshold <= 1000
    error_message = "guardrail_block_alarm_threshold must be between 1 and 1000."
  }
}

variable "gateway_role_arn" {
  description = "Exact reviewed ARN of the existing LLM Gateway role; live read-back must match."
  type        = string
  default     = ""

  validation {
    condition = (
      var.gateway_role_arn == "" ||
      (
        !strcontains(var.gateway_role_arn, "*") &&
        can(regex("^arn:(aws|aws-us-gov|aws-cn):iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_/-]{1,512}$", var.gateway_role_arn))
      )
    )
    error_message = "gateway_role_arn must be empty or one exact IAM role ARN without wildcards."
  }
}

variable "gateway_role_unique_id" {
  description = "Exact reviewed IAM unique ID for the LLM Gateway role; detects same-name role replacement."
  type        = string
  default     = ""

  validation {
    condition     = var.gateway_role_unique_id == "" || can(regex("^AROA[A-Z0-9]{17}$", var.gateway_role_unique_id))
    error_message = "gateway_role_unique_id must be empty or an AROA-prefixed 21-character IAM role unique ID."
  }
}

variable "broker_role_arn" {
  description = "Exact reviewed ARN of the existing Capability Broker role; live read-back must match."
  type        = string
  default     = ""

  validation {
    condition = (
      var.broker_role_arn == "" ||
      (
        !strcontains(var.broker_role_arn, "*") &&
        can(regex("^arn:(aws|aws-us-gov|aws-cn):iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_/-]{1,512}$", var.broker_role_arn))
      )
    )
    error_message = "broker_role_arn must be empty or one exact IAM role ARN without wildcards."
  }
}

variable "broker_role_unique_id" {
  description = "Exact reviewed IAM unique ID for the Capability Broker role; detects same-name role replacement."
  type        = string
  default     = ""

  validation {
    condition     = var.broker_role_unique_id == "" || can(regex("^AROA[A-Z0-9]{17}$", var.broker_role_unique_id))
    error_message = "broker_role_unique_id must be empty or an AROA-prefixed 21-character IAM role unique ID."
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
