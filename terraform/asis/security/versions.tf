# terraform/asis/security — 버전 제약
#
# provider "aws" 블록은 여기에 두지 않는다.
# mock provider (skip_credentials_validation / skip_requesting_account_id /
# skip_metadata_api_check · access_key·secret_key = "mock") 는
# 공유 파일 terraform/asis/main.tf 가 소유하며 사람이 관리한다.
# 자식 모듈이 provider 를 선언하면 루트와 이중 선언이 되고 모듈 재사용이 깨진다.
# 근거: terraform/asis/README.md · BOOTSTRAP_PROMPT.md "Terraform 작성 계약"

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}
