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
  region = "ap-northeast-2"

  default_tags {
    tags = {
      Project  = "jcareer"
      jk_layer = "lab"
    }
  }
}
