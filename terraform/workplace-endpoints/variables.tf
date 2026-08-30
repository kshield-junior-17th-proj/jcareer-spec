variable "deployment_stage" {
  description = "disabled=0 resources; windows_three launches three approved-image endpoints."
  type        = string
  default     = "disabled"

  validation {
    condition     = contains(["disabled", "windows_three"], var.deployment_stage)
    error_message = "deployment_stage must be disabled or windows_three."
  }
}

variable "activation_acknowledgement" {
  type      = string
  default   = "disabled"
  sensitive = true

  validation {
    condition = contains([
      "disabled",
      "JCAREER_THREE_WINDOWS_ENDPOINTS_APPROVED",
    ], var.activation_acknowledgement)
    error_message = "activation acknowledgement is invalid."
  }
}

variable "approval_ref" {
  type    = string
  default = ""

  validation {
    condition = (
      var.approval_ref == "" ||
      can(regex("^APPROVAL-[A-Z0-9_-]{8,64}$", var.approval_ref))
    )
    error_message = "approval_ref must use the APPROVAL-<pseudonymous-ref> shape."
  }
}

variable "image_build_ref" {
  description = "Pseudonymous reference to the approved Image Builder receipt."
  type        = string
  default     = ""

  validation {
    condition = (
      var.image_build_ref == "" ||
      can(regex("^IMAGE-[A-Z0-9_-]{8,64}$", var.image_build_ref))
    )
    error_message = "image_build_ref must use the IMAGE-<pseudonymous-ref> shape."
  }
}

variable "aws_region" {
  type    = string
  default = "ap-northeast-2"

  validation {
    condition     = var.aws_region == "ap-northeast-2"
    error_message = "This endpoint demonstration is restricted to ap-northeast-2."
  }
}

variable "name_prefix" {
  type    = string
  default = "jcareer-workplace"

  validation {
    condition     = can(regex("^[a-z0-9-]{3,24}$", var.name_prefix))
    error_message = "name_prefix must contain 3..24 lowercase letters, digits, or hyphens."
  }
}

variable "vpc_id" {
  type      = string
  default   = ""
  sensitive = true
}

variable "subnet_id" {
  type      = string
  default   = ""
  sensitive = true
}

variable "windows_ami_id" {
  description = "Exact AMI from the separately approved Image Builder receipt."
  type        = string
  default     = ""
  sensitive   = true
}

variable "key_pair_name" {
  description = "Existing key pair used only for AWS-encrypted initial Windows password retrieval."
  type        = string
  default     = ""
  sensitive   = true
}

variable "auto_stop_minutes" {
  type    = number
  default = 120

  validation {
    condition     = var.auto_stop_minutes >= 30 && var.auto_stop_minutes <= 240
    error_message = "auto_stop_minutes must be between 30 and 240."
  }
}

variable "budget_limit_usd" {
  type    = number
  default = 25

  validation {
    condition     = var.budget_limit_usd >= 5 && var.budget_limit_usd <= 100
    error_message = "budget_limit_usd must be between 5 and 100."
  }
}
