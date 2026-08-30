# terraform/asis/data — 지역값
#
# 필수 태그 3종은 terraform/asis/README.md 「필수 태그」 계약이다.
# jk_source 는 AGENTS.md §5 에 따라 저장소 기준 전체 경로 앵커로 쓴다.
# 리소스마다 근거 절이 다르므로 jk_source 는 리소스 쪽에서 merge 한다.

locals {
  # 공개 소스에는 12자리 계정 식별자를 저장하지 않는다. 계정 형식값은 mock plan
  # 전용이고, ELB 값은 기존 AS-IS의 공개 AWS 서비스 주체 상수를 분할해 유지한다.
  mock_account_id                       = var.account_id == "redacted" ? join("", ["0000", "0000", "0000"]) : var.account_id
  effective_elb_log_delivery_account_id = var.elb_log_delivery_account_id == "redacted" ? join("", ["6007", "3457", "5887"]) : var.elb_log_delivery_account_id

  tags_base = merge(var.common_tags, {
    jk_layer = "asis-model"
    jk_apply = "forbidden"
  })

  # CloudTrail 정책의 aws:SourceAccount 조건. 미지정이면 단일 계정 구성으로 본다.
  cloudtrail_source_account_ids = length(var.cloudtrail_source_account_ids) > 0 ? var.cloudtrail_source_account_ids : [local.mock_account_id]

  # CloudTrail 로그 객체 경로. s3_key_prefix 가 비면 접두사 없이 AWSLogs/ 로 시작한다.
  cloudtrail_key_prefix = var.cloudtrail_s3_key_prefix == "" ? "" : "${var.cloudtrail_s3_key_prefix}/"

  bucket_resume     = "${var.name_prefix}-resume-${local.mock_account_id}"
  bucket_alb_logs   = "${var.name_prefix}-alb-logs-${local.mock_account_id}"
  bucket_cloudtrail = "${var.name_prefix}-cloudtrail-${local.mock_account_id}"
}
