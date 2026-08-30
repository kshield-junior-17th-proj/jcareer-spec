# terraform/asis/data — S3 ① 첨부 이력서 원본 버킷
#
# AS-IS 사실 (SCENARIO_CONFIRMED)
#   context/raw/SCENARIO_FACTS-가상고객사J사.md#10
#     「첨부 이력서 원본 | S3 저장. 버저닝 활성. 퍼블릭 차단 적용. SSE-S3.
#       파기 시 이전 버전·수명주기 규칙 미처리」
#   context/raw/Jcareer-흐름과-기술취약점.md#2.5
#     「S3 (이력서 원본) | 버저닝 활성. 삭제해도 이전 버전이 남는다. 수명주기 규칙 미처리」

resource "aws_s3_bucket" "resume" {
  bucket = local.bucket_resume

  tags = merge(local.tags_base, {
    Name      = local.bucket_resume
    jk_source = "context/raw/SCENARIO_FACTS-가상고객사J사.md#10"
  })
}

# GAP-S3-01 재현 지점 ① — 버저닝 활성.
# 삭제해도 이전 버전이 남아 파기 요청이 저장소에 도달하지 않는다.
# 근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#10
#       context/raw/Jcareer-흐름과-기술취약점.md#2.5
# Suspended 로 바꾸면 기대한 GAP 이 재현되지 않는다. 바꾸지 말 것.
resource "aws_s3_bucket_versioning" "resume" {
  bucket = aws_s3_bucket.resume.id

  versioning_configuration {
    status = "Enabled"
  }
}

# GAP-S3-01 재현 지점 ② [ABSENCE-in-place]
# aws_s3_bucket_lifecycle_configuration.resume — 의도적 미선언.
# 원문이 「파기 시 이전 버전·수명주기 규칙 미처리」라고 확정한 지점이다.
# 이 버킷에 noncurrent_version_expiration 을 붙이면 GAP-S3-01 이 사라진다. 붙이지 말 것.
# 근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#10
#       context/raw/Jcareer-흐름과-기술취약점.md#2.5

# SSE-S3 (AES256). GAP-KMS-01 근거 — CMK 를 쓰지 않으므로 aws:kms 가 아니다.
# 근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#10 「SSE-S3」
#       context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2 「CMK 미사용, 회전 정책 없음」
resource "aws_s3_bucket_server_side_encryption_configuration" "resume" {
  bucket = aws_s3_bucket.resume.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# 퍼블릭 차단 적용. 원문이 이 버킷에 한해 명시한 통제다.
# 근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#10 「퍼블릭 차단 적용」
resource "aws_s3_bucket_public_access_block" "resume" {
  bucket = aws_s3_bucket.resume.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
