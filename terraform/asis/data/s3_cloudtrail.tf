# terraform/asis/data — S3 ③ CloudTrail 로그 목적지 버킷
#
# AS-IS 사실 (SCENARIO_CONFIRMED)
#   context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2
#     「CloudTrail | 관리 이벤트만 기록. S3 데이터 이벤트 미기록」
#   context/raw/인프라컨텍스트-외부협업용.md#2.2
#     계정 공통 서비스 — S3(버저닝) · KMS(관리형 키) · CloudTrail(관리이벤트만)
#
# 소유 경계 — aws_cloudtrail 리소스와 selector 미선언은 observability 모듈
# (TASK-105) 소유다. GAP-TRAIL-01(데이터 이벤트 미기록) 재현도 그쪽 책임이다.
# 이 모듈은 목적지 버킷과 버킷 정책만 소유하고, 아래 입력 contract 로 연결한다.

resource "aws_s3_bucket" "cloudtrail" {
  bucket = local.bucket_cloudtrail

  tags = merge(local.tags_base, {
    Name      = local.bucket_cloudtrail
    jk_source = "context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2"
  })
}

# SSE-S3 (AES256). GAP-KMS-01 근거 — CMK 미사용, 회전 정책 없음.
# 근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2
resource "aws_s3_bucket_server_side_encryption_configuration" "cloudtrail" {
  bucket = aws_s3_bucket.cloudtrail.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# [OBSERVATION] aws_s3_bucket_public_access_block.cloudtrail — 미선언.
# [OBSERVATION] aws_s3_bucket_lifecycle_configuration.cloudtrail — 미선언.
# [OBSERVATION] aws_s3_bucket_versioning.cloudtrail — 미선언.
# 세 항목 모두 원문에 이 버킷 기준 서술이 없다. 없는 통제를 채우지 않는다.
# 스캐너가 잡으면 명세 밖 발견으로 사람에게 올라간다.
# 근거: terraform/asis/README.md 「왜 자르지 않는가」 · AGENTS.md §0

# ---------------------------------------------------------------------------
# CloudTrail 정책 입력 contract
# ---------------------------------------------------------------------------
#
# 아래 정책은 이 모듈 밖의 값 세 개에 의존한다. observability 모듈이 만드는 trail 과
# 반드시 일치해야 하며, 어긋나면 aws:SourceArn 조건이 실제 trail 을 가리키지 않는다.
#
#   var.cloudtrail_name              = aws_cloudtrail.<x>.name
#   var.cloudtrail_s3_key_prefix     = aws_cloudtrail.<x>.s3_key_prefix
#   var.cloudtrail_source_account_ids= trail 소유 계정 (단일 계정이면 [var.account_id])
#
# 반대 방향으로는 outputs.tf 의 cloudtrail_bucket_id 를
# aws_cloudtrail.<x>.s3_bucket_name 에 넣는다. README.md 「모듈 간 계약」 참조.
#
# data "aws_iam_policy_document" 는 계약상 유일하게 허용된 data source 다.
# 근거: terraform/asis/README.md

data "aws_iam_policy_document" "cloudtrail" {
  statement {
    sid    = "AWSCloudTrailAclCheck"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.cloudtrail.arn]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceArn"
      values   = ["arn:aws:cloudtrail:${var.region}:${local.mock_account_id}:trail/${var.cloudtrail_name}"]
    }
  }

  statement {
    sid    = "AWSCloudTrailWrite"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    actions = ["s3:PutObject"]
    resources = [
      for acct in local.cloudtrail_source_account_ids :
      "${aws_s3_bucket.cloudtrail.arn}/${local.cloudtrail_key_prefix}AWSLogs/${acct}/*"
    ]

    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceArn"
      values   = ["arn:aws:cloudtrail:${var.region}:${local.mock_account_id}:trail/${var.cloudtrail_name}"]
    }
  }
}

resource "aws_s3_bucket_policy" "cloudtrail" {
  bucket = aws_s3_bucket.cloudtrail.id
  policy = data.aws_iam_policy_document.cloudtrail.json
}
