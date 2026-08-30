# terraform/asis/security — 입력 변수
#
# data source 를 쓰지 않는다. AZ 이름·계정 ID·리전·VPC/서브넷 식별자는
# 전부 variable 상수 기본값 또는 루트에서 주입되는 값으로 받는다.
# 근거: terraform/asis/README.md "작성 규칙 — 무자격증명 plan (필수)"
#
# 기본값이 없는 변수는 terraform/asis/main.tf (공유 파일 · 사람 관리) 에서
# network / compute / data 모듈 출력으로 배선한다. 이 모듈은 그 배선을 직접 만들지 않는다.

variable "region" {
  description = "AS-IS 서비스망 리전. 서울 단일. context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2"
  type        = string
  default     = "ap-northeast-2"
}

variable "name_prefix" {
  description = "리소스 이름 접두사."
  type        = string
  default     = "jcareer-asis"
}

# ── network 모듈에서 배선되는 값 ────────────────────────────────────────────────
variable "vpc_id" {
  description = "서비스망 VPC (10.0.0.0/16). network 모듈 출력."
  type        = string
}

variable "app_subnet_ids" {
  description = <<-EOT
    Private App 서브넷 ID 목록 (10.0.10.0/24 · 10.0.11.0/24 · 2-AZ).
    SSM 계열 interface endpoint 의 ENI 가 놓이는 곳이다.
    근거: context/raw/D02-진단대상-아키텍처-정의.md#3.1
  EOT
  type        = list(string)
}

variable "vpc_endpoint_security_group_ids" {
  description = <<-EOT
    interface endpoint ENI 에 붙는 보안그룹 ID 목록. network 모듈 소유.
    이 모듈은 보안그룹을 만들지 않는다 — SG 는 network 모듈 범위다.
  EOT
  type        = list(string)
}

# ── data 모듈에서 배선되는 값 ─────────────────────────────────────────────────
variable "resume_bucket_name" {
  description = <<-EOT
    이력서 첨부 원본이 저장되는 S3 버킷 이름. data 모듈 소유.
    ECS task role 의 객체 접근 범위를 이 버킷으로 한정하기 위해서만 쓴다.
  EOT
  type        = string
  default     = "jcareer-asis-resume"
}

# ── 태그 ──────────────────────────────────────────────────────────────────────
variable "common_tags" {
  description = <<-EOT
    terraform/asis 공통 필수 태그. jk_source 는 리소스별로 merge 해서 덧붙인다.
    근거: terraform/asis/README.md "필수 태그"
  EOT
  type        = map(string)
  default = {
    jk_layer = "asis-model"
    jk_apply = "forbidden"
  }
}
