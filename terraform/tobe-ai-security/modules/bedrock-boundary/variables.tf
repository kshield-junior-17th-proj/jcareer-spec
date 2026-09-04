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

variable "bedrock_invocation_resource_arns" {
  description = "Exact Bedrock invocation target and, for cross-region inference, every reviewed destination model ARN. Wildcards are forbidden."
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
  description = "Exact numeric published Capability Broker Lambda version ARN that the LLM Gateway may invoke."
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
  description = "Base64-encoded CodeSha256 expected from the exact published Broker Lambda version."
  type        = string
  default     = ""

  validation {
    condition     = var.broker_code_sha256 == "" || can(regex("^[A-Za-z0-9+/]{43}=$", var.broker_code_sha256))
    error_message = "broker_code_sha256 must be empty or the 44-character base64 Lambda CodeSha256 value."
  }
}

variable "bedrock_approval_binding_sha256" {
  description = "SHA-256 of the reviewed model ID/ARN set, Broker published version/CodeSha256, role identities, and region. Required when enabled."
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
  description = "Existing capability-broker workload role that receives model invocation permission."
  type        = string
  default     = ""

  validation {
    condition     = var.broker_role_name == "" || can(regex("^[A-Za-z0-9+=,.@_-]{1,64}$", var.broker_role_name))
    error_message = "broker_role_name must be empty or a valid IAM role name."
  }
}

variable "broker_role_arn" {
  description = "Exact reviewed Capability Broker role ARN included in the approval digest."
  type        = string
  default     = ""

  validation {
    condition     = var.broker_role_arn == "" || (!strcontains(var.broker_role_arn, "*") && can(regex("^arn:(aws|aws-us-gov|aws-cn):iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_/-]{1,512}$", var.broker_role_arn)))
    error_message = "broker_role_arn must be empty or one exact IAM role ARN without wildcards."
  }
}

variable "broker_role_unique_id" {
  description = "Exact reviewed Capability Broker role unique ID included in the approval digest."
  type        = string
  default     = ""

  validation {
    condition     = var.broker_role_unique_id == "" || can(regex("^AROA[A-Z0-9]{17}$", var.broker_role_unique_id))
    error_message = "broker_role_unique_id must be empty or an AROA-prefixed 21-character IAM role unique ID."
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

variable "gateway_role_arn" {
  description = "Exact reviewed LLM Gateway role ARN included in the approval digest."
  type        = string
  default     = ""

  validation {
    condition     = var.gateway_role_arn == "" || (!strcontains(var.gateway_role_arn, "*") && can(regex("^arn:(aws|aws-us-gov|aws-cn):iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_/-]{1,512}$", var.gateway_role_arn)))
    error_message = "gateway_role_arn must be empty or one exact IAM role ARN without wildcards."
  }
}

variable "gateway_role_unique_id" {
  description = "Exact reviewed LLM Gateway role unique ID included in the approval digest."
  type        = string
  default     = ""

  validation {
    condition     = var.gateway_role_unique_id == "" || can(regex("^AROA[A-Z0-9]{17}$", var.gateway_role_unique_id))
    error_message = "gateway_role_unique_id must be empty or an AROA-prefixed 21-character IAM role unique ID."
  }
}

variable "additional_tags" {
  description = "Optional tags; required trace tags take precedence."
  type        = map(string)
  default     = {}
}
