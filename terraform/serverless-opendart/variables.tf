variable "deployment_stage" {
  description = "disabled=0 resources, bootstrap=durable foundation, runtime=Lambda and API-role wiring."
  type        = string
  default     = "disabled"

  validation {
    condition     = contains(["disabled", "bootstrap", "runtime"], var.deployment_stage)
    error_message = "deployment_stage must be disabled, bootstrap, or runtime."
  }
}

variable "activation_acknowledgement" {
  description = "Explicit human acknowledgement; it is not proof of approval by itself."
  type        = string
  default     = "disabled"
  sensitive   = true

  validation {
    condition = contains([
      "disabled",
      "JCAREER_OPENDART_SERVERLESS_APPROVED",
    ], var.activation_acknowledgement)
    error_message = "activation acknowledgement is invalid."
  }
}

variable "approval_ref" {
  description = "Pseudonymous reference to the separately reviewed, plan-bound approval record."
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

variable "aws_region" {
  description = "Reviewed demonstration Region."
  type        = string
  default     = "ap-northeast-2"

  validation {
    condition     = var.aws_region == "ap-northeast-2"
    error_message = "This demonstration root is restricted to ap-northeast-2."
  }
}

variable "name_prefix" {
  description = "Resource name prefix."
  type        = string
  default     = "jcareer-asis-opendart"

  validation {
    condition     = can(regex("^[a-z0-9-]{3,28}$", var.name_prefix))
    error_message = "name_prefix must contain 3..28 lowercase letters, digits, or hyphens."
  }
}

variable "lambda_image_uri" {
  description = "Digest-pinned image URI from this root's ECR repository; runtime only."
  type        = string
  default     = ""
  sensitive   = true
}

variable "opendart_api_key_parameter_name" {
  description = "Existing SecureString parameter name; the value is never managed by this root."
  type        = string
  default     = ""
  sensitive   = true
}

variable "opendart_api_key_parameter_arn" {
  description = "Exact ARN of the existing SecureString parameter for least-privilege IAM."
  type        = string
  default     = ""
  sensitive   = true
}

variable "opendart_api_key_kms_key_arn" {
  description = "Optional exact customer-managed KMS key ARN for the SecureString; leave empty for the AWS-managed SSM key."
  type        = string
  default     = ""
  sensitive   = true

  validation {
    condition = (
      var.opendart_api_key_kms_key_arn == "" ||
      can(regex("^arn:aws:kms:ap-northeast-2:[0-9]{12}:key/[0-9a-f-]{36}$", var.opendart_api_key_kms_key_arn))
    )
    error_message = "opendart_api_key_kms_key_arn must be empty or an exact ap-northeast-2 customer key ARN."
  }
}

variable "api_sender_role_name" {
  description = "Existing runtime API EC2 role that may send requests and collect bound results."
  type        = string
  default     = ""
}

variable "result_ttl_seconds" {
  description = "Bounded durable-result lifetime. Application results are copied to company DB."
  type        = number
  default     = 3600

  validation {
    condition     = var.result_ttl_seconds >= 900 && var.result_ttl_seconds <= 86400
    error_message = "result_ttl_seconds must be between 900 and 86400."
  }
}

variable "pending_timeout_seconds" {
  description = "Maximum API pending interval before a missing worker result is released for an explicit retry."
  type        = number
  default     = 1800

  validation {
    condition     = var.pending_timeout_seconds >= 900 && var.pending_timeout_seconds <= var.result_ttl_seconds
    error_message = "pending_timeout_seconds must be 900..result_ttl_seconds."
  }
}

variable "log_retention_days" {
  description = "CloudWatch worker metadata-log retention."
  type        = number
  default     = 7

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30], var.log_retention_days)
    error_message = "log_retention_days must be 1, 3, 5, 7, 14, or 30."
  }
}
