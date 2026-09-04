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

  validation {
    condition = (
      var.approval_ref == "" ||
      can(regex("^APPROVAL-[A-Z0-9_-]{8,64}$", var.approval_ref))
    )
    error_message = "approval_ref must be empty or use APPROVAL-<pseudonymous-ref>."
  }
}

variable "aws_region" {
  description = "Region containing the approved foundation model and guardrail."
  type        = string

  validation {
    condition     = var.aws_region == "ap-northeast-2"
    error_message = "This proposal is intentionally restricted to ap-northeast-2."
  }
}

variable "name_prefix" {
  description = "Resource name prefix."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,23}$", var.name_prefix))
    error_message = "name_prefix must be 3..24 lowercase letters, digits, or hyphens and start with a letter."
  }
}

variable "exact_model_id" {
  description = "Exactly one approved foundation-model ID; no wildcard or inference-profile expansion."
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
  description = "Existing capability-broker workload role that receives model invocation permission."
  type        = string
  default     = ""

  validation {
    condition     = var.broker_role_name == "" || can(regex("^[A-Za-z0-9+=,.@_-]{1,64}$", var.broker_role_name))
    error_message = "broker_role_name must be empty or a valid IAM role name."
  }
}

variable "gateway_role_name" {
  description = "Existing LLM Gateway workload role that receives an explicit direct invocation deny."
  type        = string
  default     = ""

  validation {
    condition     = var.gateway_role_name == "" || can(regex("^[A-Za-z0-9+=,.@_-]{1,64}$", var.gateway_role_name))
    error_message = "gateway_role_name must be empty or a valid IAM role name."
  }
}

variable "additional_tags" {
  description = "Optional tags; required trace tags take precedence."
  type        = map(string)
  default     = {}
}
