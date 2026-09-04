variable "enable" {
  description = "False creates no module resources."
  type        = bool
  default     = false
}

variable "activation_acknowledgement" {
  description = "Exact human acknowledgement propagated by the composition root."
  type        = string
  default     = "PROPOSED_NOT_DEPLOYED"
  sensitive   = true
}

variable "approval_ref" {
  description = "Pseudonymous reference to the plan-bound approval record."
  type        = string
  default     = ""
}

variable "cloudfront_distribution_id" {
  description = "Existing CloudFront distribution owned by the delivery stack. Required when this module is enabled."
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
  description = "Pseudonymous owner-stack change reference that sets the distribution web_acl_id to this module output."
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
  description = "Read the existing distribution and fail unless its web_acl_id equals this module ACL. False during ACL creation and by default."
  type        = bool
  default     = false
}

variable "name_prefix" {
  description = "Resource name prefix."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,23}$", var.name_prefix))
    error_message = "name_prefix must be 3..24 lowercase letters, digits, or hyphens and start with a letter."
  }
}

variable "request_limit" {
  description = "Requests per source IP during evaluation_window_seconds."
  type        = number
  default     = 300

  validation {
    condition     = var.request_limit >= 10 && var.request_limit <= 10000
    error_message = "request_limit must be between 10 and 10000."
  }
}

variable "evaluation_window_seconds" {
  description = "WAF rate aggregation window."
  type        = number
  default     = 300

  validation {
    condition     = contains([60, 120, 300, 600], var.evaluation_window_seconds)
    error_message = "evaluation_window_seconds must be 60, 120, 300, or 600."
  }
}

variable "log_retention_days" {
  description = "Retention for blocked/count WAF security metadata."
  type        = number
  default     = 30

  validation {
    condition     = contains([7, 14, 30, 60, 90], var.log_retention_days)
    error_message = "log_retention_days must be 7, 14, 30, 60, or 90."
  }
}

variable "additional_tags" {
  description = "Optional tags; required trace tags take precedence."
  type        = map(string)
  default     = {}
}
