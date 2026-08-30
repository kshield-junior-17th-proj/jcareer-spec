terraform {
  required_version = "= 1.15.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.59.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  # `disabled` is an AWS-free zero-resource plan. Bootstrap/runtime stages use
  # ordinary credential and account validation.
  skip_credentials_validation = var.deployment_stage == "disabled"
  skip_requesting_account_id  = var.deployment_stage == "disabled"
  skip_region_validation      = var.deployment_stage == "disabled"
  skip_metadata_api_check     = true

  default_tags {
    tags = {
      Project    = "jcareer"
      jk_layer   = "asis-serverless-mlops-demo"
      jk_purpose = "synthetic-runtime-training"
    }
  }
}
