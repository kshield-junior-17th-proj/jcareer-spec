variable "deployment_stage" {
  description = "disabled=0 resources; definition creates a manual Windows image pipeline definition."
  type        = string
  default     = "disabled"

  validation {
    condition     = contains(["disabled", "definition"], var.deployment_stage)
    error_message = "deployment_stage must be disabled or definition."
  }
}

variable "activation_acknowledgement" {
  description = "Explicit human acknowledgement; it is not approval evidence by itself."
  type        = string
  default     = "disabled"
  sensitive   = true

  validation {
    condition = contains([
      "disabled",
      "JCAREER_WINDOWS_IMAGE_DEFINITION_APPROVED",
    ], var.activation_acknowledgement)
    error_message = "activation acknowledgement is invalid."
  }
}

variable "approval_ref" {
  description = "Pseudonymous reference to a separately reviewed exact-plan approval."
  type        = string
  default     = ""

  validation {
    condition = (
      var.approval_ref == "" ||
      can(regex("^APPROVAL-[A-Z0-9_-]{8,64}$", var.approval_ref))
    )
    error_message = "approval_ref must use the APPROVAL-<pseudonymous-ref> shape."
  }
}

variable "image_build_ref" {
  description = "Pseudonymous build reference propagated to Image Builder and output AMI tags."
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
    error_message = "This image definition is restricted to ap-northeast-2."
  }
}

variable "name_prefix" {
  type    = string
  default = "jcareer-workplace-windows"

  validation {
    condition     = can(regex("^[a-z0-9-]{3,28}$", var.name_prefix))
    error_message = "name_prefix must contain 3..28 lowercase letters, digits, or hyphens."
  }
}

variable "windows_parent_image" {
  description = "Human-reviewed, version-pinned AWS Image Builder ARN for a Windows Server 2022 Desktop parent."
  type        = string
  default     = ""
  sensitive   = true

  validation {
    condition = (
      var.windows_parent_image == "" ||
      can(regex("^arn:aws:imagebuilder:ap-northeast-2:aws:image/[a-z0-9_-]+/[0-9]+\\.[0-9]+\\.[0-9]+$", var.windows_parent_image))
    )
    error_message = "windows_parent_image must be a version-pinned AWS-owned Image Builder ARN."
  }
}

variable "build_subnet_id" {
  description = "Reviewed build subnet. No identifier is committed to source."
  type        = string
  default     = ""
  sensitive   = true
}

variable "build_security_group_id" {
  description = "Reviewed no-public-inbound build security group."
  type        = string
  default     = ""
  sensitive   = true
}
