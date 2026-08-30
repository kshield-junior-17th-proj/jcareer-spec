# terraform/asis/data — 버전 제약
#
# 이 디렉터리는 자식 모듈이다. provider 블록을 선언하지 않는다.
# provider "aws" (mock 자격증명 · skip_* 플래그) 는 공유 루트
# terraform/asis/main.tf 가 소유한다. 근거: terraform/asis/README.md
#
# 이 모듈은 apply 대상이 아니다. fmt · init -backend=false · validate · plan 만 돈다.

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}
