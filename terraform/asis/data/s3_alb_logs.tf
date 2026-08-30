# terraform/asis/data — S3 ② ALB 액세스 로그 버킷
#
# AS-IS 사실 (SCENARIO_CONFIRMED)
#   context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2
#     「ALB | Multi-AZ · TLS 1.2+ 종단 · 액세스 로그 S3 적재, 보존 90일」
#   context/raw/Jcareer-흐름과-기술취약점.md#4.1
#     갖춰진 것 — ... ALB Multi-AZ(로그 90일) ...
#
# ALB 리소스 자체는 compute 모듈(TASK-103) 소유다. 이 모듈은 목적지 버킷만 만든다.
# 연결 계약은 README.md 「모듈 간 계약」 참조.

resource "aws_s3_bucket" "alb_logs" {
  bucket = local.bucket_alb_logs

  tags = merge(local.tags_base, {
    Name      = local.bucket_alb_logs
    jk_source = "context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2"
  })
}

# 보존 90일. 이력서 버킷과 달리 이 버킷에는 원문이 보존기간을 확정해 두었다.
# 근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2
#
# 권위 상충 주의 — context/proposals/docs-current/EXPECTED_FINDINGS.yaml 의
# GAP-S3-01 은 companion_absent 로 aws_s3_bucket_lifecycle_configuration 을
# layer 전체에서 금지한다. 그 초안 명세대로면 여기 90일 규칙이 GAP-S3-01 을 깬다.
# 초안은 승인 전 비권위 문서이므로 임의로 해소하지 않았다.
# 상충 원문 쌍과 판단 요청은 README.md 「권위 상충」 절에 기록했다 (AGENTS.md §1).
resource "aws_s3_bucket_lifecycle_configuration" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id

  rule {
    id     = "expire-alb-access-logs"
    status = "Enabled"

    filter {
      prefix = "${var.alb_log_prefix}/"
    }

    expiration {
      days = var.alb_log_retention_days
    }
  }
}

# SSE-S3 (AES256). GAP-KMS-01 근거 — CMK 미사용.
# 근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2
resource "aws_s3_bucket_server_side_encryption_configuration" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# [OBSERVATION] aws_s3_bucket_public_access_block.alb_logs — 미선언.
# 원문이 퍼블릭 차단을 명시한 버킷은 이력서 원본 하나뿐이다
# (context/raw/SCENARIO_FACTS-가상고객사J사.md#10). 로그 버킷 2개에는 서술이 없다.
# 없는 통제를 임의로 채우면 AS-IS 가 아니라 우리가 만든 상태가 된다.
# 스캐너가 이 지점을 잡으면 명세 밖 발견으로 사람에게 올라간다
# (terraform/asis/README.md 「왜 자르지 않는가」). 우리는 판정하지 않는다.

# [OBSERVATION] aws_s3_bucket_versioning.alb_logs — 미선언.
# 원문이 버저닝을 확정한 대상도 이력서 원본 버킷 하나뿐이다.
# context/raw/인프라컨텍스트-외부협업용.md#2.2 의 「S3(버저닝)」는 계정 공통 서비스
# 나열이라 어느 버킷까지인지 확정되지 않는다. 확대 해석하지 않았다.

# ALB 로그 전달 버킷 정책.
# data "aws_iam_policy_document" 는 로컬 계산이라 계약상 유일하게 허용된 data source다.
# 근거: terraform/asis/README.md
data "aws_iam_policy_document" "alb_logs" {
  statement {
    sid    = "AWSLogDeliveryWrite"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${local.effective_elb_log_delivery_account_id}:root"]
    }

    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.alb_logs.arn}/${var.alb_log_prefix}/AWSLogs/${local.mock_account_id}/*"]

    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }
  }

  statement {
    sid    = "AWSLogDeliveryAclCheck"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${local.effective_elb_log_delivery_account_id}:root"]
    }

    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.alb_logs.arn]
  }
}

resource "aws_s3_bucket_policy" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id
  policy = data.aws_iam_policy_document.alb_logs.json
}
