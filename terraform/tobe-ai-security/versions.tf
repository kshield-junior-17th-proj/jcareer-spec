terraform {
  required_version = "= 1.15.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.59.0"
    }
  }
}

# PROPOSED / NOT DEPLOYED. When enable=false, provider identity and metadata
# lookups are deliberately skipped so the zero-resource proposal is safe to
# inspect without AWS credentials.
provider "aws" {
  region = var.aws_region

  skip_credentials_validation = !var.enable
  skip_requesting_account_id  = !var.enable
  skip_region_validation      = !var.enable
  skip_metadata_api_check     = true

  default_tags {
    tags = {
      Project     = "jcareer"
      jk_layer    = "tobe"
      control_id  = "TOBE-AI-SECURITY"
      gap_id      = "NF-02,NF-03,NF-04,NF-05,NF-06"
      evidence_id = "EXPECTED-NOT-OBSERVED"
      status      = "PROPOSED_NOT_DEPLOYED"
    }
  }
}

# CloudFront-scope WAF resources must be owned in us-east-1. This alias does
# not imply that a custom domain, certificate, or WAF association exists.
provider "aws" {
  alias  = "cloudfront_control_plane"
  region = "us-east-1"

  skip_credentials_validation = !var.enable
  skip_requesting_account_id  = !var.enable
  skip_region_validation      = !var.enable
  skip_metadata_api_check     = true

  default_tags {
    tags = {
      Project     = "jcareer"
      jk_layer    = "tobe"
      control_id  = "T.6.1,T.6.2"
      gap_id      = "NF-06,NF-05"
      evidence_id = "EXPECTED-EDGE-WAF-RATE"
      status      = "PROPOSED_NOT_DEPLOYED"
    }
  }
}
