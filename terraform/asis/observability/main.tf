locals {
  required_tags = {
    jk_layer  = "asis-model"
    jk_source = "context/raw/인프라컨텍스트-외부협업용.md#2.2"
    jk_apply  = "forbidden"
  }

  resource_tags = merge(var.tags, local.required_tags)
}

# GAP [PRESERVED]: 접속기록 보존기간은 365일로 재현하며 여기서 연장하지 않는다.
# 근거: context/raw/인프라컨텍스트-외부협업용.md#2.2
resource "aws_cloudwatch_log_group" "access" {
  name              = "/${var.name_prefix}/access"
  retention_in_days = 365
  tags              = local.resource_tags
}

# GAP [PRESERVED]: VPC Flow Log 보존기간은 승인 범위의 30일로 고정한다.
resource "aws_cloudwatch_log_group" "flow" {
  name              = "/${var.name_prefix}/vpc-flow"
  retention_in_days = 30
  tags              = local.resource_tags
}

# GAP [PRESERVED]: prompt raw 로그는 retention_in_days를 의도적으로 설정하지 않는다.
resource "aws_cloudwatch_log_group" "prompt_raw" {
  name = "/${var.name_prefix}/prompt-raw"
  tags = local.resource_tags
}

resource "aws_cloudtrail" "this" {
  name                          = "${var.name_prefix}-management"
  s3_bucket_name                = var.cloudtrail_s3_bucket_id
  enable_logging                = true
  include_global_service_events = true

  # GAP-TRAIL-01 [PRESERVED]: 별도 selector를 선언하지 않아 CloudTrail 기본값인
  # 관리 이벤트만 기록한다. event_selector/advanced_event_selector와 S3 data_resource를
  # 추가하지 않는다.
  # 근거: context/raw/인프라컨텍스트-외부협업용.md#2.2

  tags = local.resource_tags
}

resource "aws_flow_log" "vpc" {
  iam_role_arn         = var.flow_log_iam_role_arn
  log_destination      = aws_cloudwatch_log_group.flow.arn
  log_destination_type = "cloud-watch-logs"
  traffic_type         = "ALL"
  vpc_id               = var.vpc_id

  tags = local.resource_tags
}

resource "aws_guardduty_detector" "this" {
  enable = true
  tags   = local.resource_tags
}

# GAP-CFG-01 [ABSENCE]: AWS Config 리소스는 AS-IS 재현을 위해 선언하지 않는다.
# 근거: context/raw/인프라컨텍스트-외부협업용.md#2.2
