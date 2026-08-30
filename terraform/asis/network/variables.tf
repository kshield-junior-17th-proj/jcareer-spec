variable "region" {
  description = "AWS region represented by this AS-IS model."
  type        = string
  default     = "ap-northeast-2"

  validation {
    condition     = var.region == "ap-northeast-2"
    error_message = "The approved Phase 1 network scope is fixed to ap-northeast-2."
  }
}

variable "name_prefix" {
  description = "Prefix applied to named network resources."
  type        = string
  default     = "jcareer-asis"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$", var.name_prefix))
    error_message = "name_prefix must be 3-32 lowercase alphanumeric or hyphen characters."
  }
}

variable "vpc_cidr" {
  description = "CIDR block of the J-Career service VPC."
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = var.vpc_cidr == "10.0.0.0/16"
    error_message = "The approved AS-IS VPC CIDR is 10.0.0.0/16."
  }
}

variable "az_names" {
  description = "Ordered availability zones for the 2a and 2c network copies."
  type        = list(string)
  default     = ["ap-northeast-2a", "ap-northeast-2c"]

  validation {
    condition = (
      length(var.az_names) == 2 &&
      var.az_names[0] == "ap-northeast-2a" &&
      var.az_names[1] == "ap-northeast-2c"
    )
    error_message = "az_names must preserve ap-northeast-2a and ap-northeast-2c in that order."
  }
}

variable "public_subnet_cidrs" {
  description = "Ordered public subnet CIDRs for availability zones 2a and 2c."
  type        = list(string)
  default     = ["10.0.0.0/24", "10.0.1.0/24"]

  validation {
    condition = (
      length(var.public_subnet_cidrs) == 2 &&
      var.public_subnet_cidrs[0] == "10.0.0.0/24" &&
      var.public_subnet_cidrs[1] == "10.0.1.0/24"
    )
    error_message = "public_subnet_cidrs must preserve the approved 2a/2c CIDRs."
  }
}

variable "app_subnet_cidrs" {
  description = "Ordered private application subnet CIDRs for availability zones 2a and 2c."
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]

  validation {
    condition = (
      length(var.app_subnet_cidrs) == 2 &&
      var.app_subnet_cidrs[0] == "10.0.10.0/24" &&
      var.app_subnet_cidrs[1] == "10.0.11.0/24"
    )
    error_message = "app_subnet_cidrs must preserve the approved 2a/2c CIDRs."
  }
}

variable "data_subnet_cidrs" {
  description = "Ordered private data subnet CIDRs for availability zones 2a and 2c."
  type        = list(string)
  default     = ["10.0.20.0/24", "10.0.21.0/24"]

  validation {
    condition = (
      length(var.data_subnet_cidrs) == 2 &&
      var.data_subnet_cidrs[0] == "10.0.20.0/24" &&
      var.data_subnet_cidrs[1] == "10.0.21.0/24"
    )
    error_message = "data_subnet_cidrs must preserve the approved 2a/2c CIDRs."
  }
}

variable "additional_tags" {
  description = "Additional tags. Required AS-IS evidence tags cannot be overridden."
  type        = map(string)
  default     = {}
}
