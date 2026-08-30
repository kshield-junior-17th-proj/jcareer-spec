terraform {
  required_version = "= 1.15.9"

  backend "s3" {
    encrypt      = true
    use_lockfile = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.59.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  skip_credentials_validation = var.deployment_stage == "disabled"
  skip_requesting_account_id  = var.deployment_stage == "disabled"
  skip_region_validation      = var.deployment_stage == "disabled"
  skip_metadata_api_check     = true

  default_tags {
    tags = {
      Project    = "jcareer"
      jk_layer   = "asis-serverless-opendart-demo"
      jk_purpose = "on-demand-public-company-facts"
    }
  }
}
