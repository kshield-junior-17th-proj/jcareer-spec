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

variable "name_prefix" {
  description = "Resource name prefix."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,23}$", var.name_prefix))
    error_message = "name_prefix must be 3..24 lowercase letters, digits, or hyphens and start with a letter."
  }
}

variable "log_retention_days" {
  description = "Retention for application metadata log groups."
  type        = number
  default     = 30

  validation {
    condition     = contains([7, 14, 30, 60, 90], var.log_retention_days)
    error_message = "log_retention_days must be 7, 14, 30, 60, or 90."
  }
}

variable "evidence_lock_days" {
  description = "Default Object Lock compliance retention."
  type        = number
  default     = 90

  validation {
    condition     = var.evidence_lock_days >= 30 && var.evidence_lock_days <= 365
    error_message = "evidence_lock_days must be between 30 and 365."
  }
}

variable "evidence_expiration_days" {
  description = "Lifecycle expiration after Object Lock retention."
  type        = number
  default     = 365

  validation {
    condition     = var.evidence_expiration_days >= 90 && var.evidence_expiration_days <= 2555
    error_message = "evidence_expiration_days must be between 90 and 2555."
  }
}

variable "additional_tags" {
  description = "Optional tags; required trace tags take precedence."
  type        = map(string)
  default     = {}
}
