variable "deployment_stage" {
  description = "disabled=0 resources, bootstrap=artifact foundation, runtime=one-shot Lambda."
  type        = string
  default     = "disabled"

  validation {
    condition     = contains(["disabled", "bootstrap", "runtime"], var.deployment_stage)
    error_message = "deployment_stage must be disabled, bootstrap, or runtime."
  }
}

variable "activation_acknowledgement" {
  description = "Explicit human acknowledgement for the synthetic AS-IS serverless MLOps demo."
  type        = string
  default     = "disabled"
  sensitive   = true

  validation {
    condition = contains([
      "disabled",
      "JCAREER_SYNTHETIC_SERVERLESS_MLOPS_APPROVED",
    ], var.activation_acknowledgement)
    error_message = "activation acknowledgement is invalid."
  }
}

variable "aws_region" {
  description = "Reviewed demo Region."
  type        = string
  default     = "ap-northeast-2"

  validation {
    condition     = var.aws_region == "ap-northeast-2"
    error_message = "This demo root is restricted to ap-northeast-2."
  }
}

variable "name_prefix" {
  description = "Resource name prefix."
  type        = string
  default     = "jcareer-asis-mlops"

  validation {
    condition     = can(regex("^[a-z0-9-]{3,28}$", var.name_prefix))
    error_message = "name_prefix must contain 3..28 lowercase letters, digits, or hyphens."
  }
}

variable "artifact_bucket_name" {
  description = "Globally unique S3 bucket name supplied by the operator; empty only while disabled."
  type        = string
  default     = ""

  validation {
    condition = (
      var.artifact_bucket_name == "" ||
      can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.artifact_bucket_name))
    )
    error_message = "artifact_bucket_name must be an S3-compatible name."
  }
}

variable "lambda_image_uri" {
  description = "Image URI from this root's ECR repository, pinned with @sha256; runtime stage only."
  type        = string
  default     = ""
  sensitive   = true
}

variable "mlops_epochs" {
  description = "Bounded logistic challenger training epochs."
  type        = number
  default     = 320

  validation {
    condition     = var.mlops_epochs >= 50 && var.mlops_epochs <= 2000
    error_message = "mlops_epochs must be between 50 and 2000."
  }
}

variable "lambda_memory_mb" {
  description = "Lambda memory for the small synthetic feature snapshot."
  type        = number
  default     = 1024

  validation {
    condition     = var.lambda_memory_mb >= 512 && var.lambda_memory_mb <= 2048
    error_message = "lambda_memory_mb must be between 512 and 2048."
  }
}

variable "artifact_retention_days" {
  description = "Synthetic source and result expiry. A production retention decision is separate."
  type        = number
  default     = 7

  validation {
    condition     = var.artifact_retention_days >= 1 && var.artifact_retention_days <= 30
    error_message = "artifact_retention_days must be between 1 and 30."
  }
}

variable "log_retention_days" {
  description = "CloudWatch log retention for run-state metadata only."
  type        = number
  default     = 7

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30], var.log_retention_days)
    error_message = "log_retention_days must be 1, 3, 5, 7, 14, or 30."
  }
}
