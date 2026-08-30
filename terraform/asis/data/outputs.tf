# terraform/asis/data — 출력
#
# 다른 모듈이 이 계층을 참조하는 지점이다. plan 산출물은 sanitize 를 거친다
# (scripts/sanitize_plan.py). 비밀값은 출력하지 않는다.

# ---------------------------------------------------------------------------
# RDS
# ---------------------------------------------------------------------------

output "db_subnet_group_name" {
  description = "RDS 서브넷 그룹 이름."
  value       = aws_db_subnet_group.data.name
}

output "db_primary_identifier" {
  description = "RDS Primary 식별자."
  value       = aws_db_instance.primary.identifier
}

output "db_primary_arn" {
  description = "RDS Primary ARN."
  value       = aws_db_instance.primary.arn
}

output "db_primary_endpoint" {
  description = "RDS Primary 엔드포인트. api·agent 태스크의 접속 대상."
  value       = aws_db_instance.primary.endpoint
}

output "db_replica_identifier" {
  description = "RDS 읽기 복제본 식별자."
  value       = aws_db_instance.replica.identifier
}

output "db_replica_endpoint" {
  description = <<-EOT
    RDS 읽기 복제본 엔드포인트. 관리자 접근 경로 C(BI 분석)의 대상이다.
    근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#9.4
  EOT
  value       = aws_db_instance.replica.endpoint
}

# ---------------------------------------------------------------------------
# ElastiCache
# ---------------------------------------------------------------------------

output "cache_subnet_group_name" {
  description = "ElastiCache 서브넷 그룹 이름."
  value       = aws_elasticache_subnet_group.data.name
}

output "cache_replication_group_id" {
  description = "추천 결과 캐시 복제 그룹 ID."
  value       = aws_elasticache_replication_group.recommendation.id
}

output "cache_primary_endpoint_address" {
  description = "추천 결과 캐시 primary 엔드포인트. agent 태스크의 접속 대상."
  value       = aws_elasticache_replication_group.recommendation.primary_endpoint_address
}

# ---------------------------------------------------------------------------
# S3
# ---------------------------------------------------------------------------

output "resume_bucket_id" {
  description = "첨부 이력서 원본 버킷 이름."
  value       = aws_s3_bucket.resume.id
}

output "resume_bucket_arn" {
  description = "첨부 이력서 원본 버킷 ARN. api 태스크 IAM 정책의 대상 리소스."
  value       = aws_s3_bucket.resume.arn
}

output "alb_logs_bucket_id" {
  description = <<-EOT
    ALB 액세스 로그 버킷 이름.
    compute 모듈의 aws_lb.access_logs.bucket 에 넣는다.
  EOT
  value       = aws_s3_bucket.alb_logs.id
}

output "alb_logs_bucket_arn" {
  description = "ALB 액세스 로그 버킷 ARN."
  value       = aws_s3_bucket.alb_logs.arn
}

output "alb_logs_prefix" {
  description = <<-EOT
    ALB 액세스 로그 키 접두사.
    compute 모듈의 aws_lb.access_logs.prefix 에 넣는다. 버킷 정책·수명주기
    규칙이 이 접두사를 기준으로 걸려 있어 값이 어긋나면 둘 다 적용되지 않는다.
  EOT
  value       = var.alb_log_prefix
}

output "cloudtrail_bucket_id" {
  description = <<-EOT
    CloudTrail 로그 목적지 버킷 이름.
    observability 모듈의 aws_cloudtrail.s3_bucket_name 에 넣는다.
  EOT
  value       = aws_s3_bucket.cloudtrail.id
}

output "cloudtrail_bucket_arn" {
  description = "CloudTrail 로그 목적지 버킷 ARN."
  value       = aws_s3_bucket.cloudtrail.arn
}

output "cloudtrail_policy_contract" {
  description = <<-EOT
    CloudTrail 버킷 정책이 전제한 입력값. observability 모듈이 만드는 trail 과
    이 값들이 일치해야 aws:SourceArn 조건이 실제 trail 을 가리킨다.
    불일치를 눈으로 대조할 수 있게 출력으로 노출한다.
  EOT
  value = {
    trail_name          = var.cloudtrail_name
    trail_arn           = "arn:aws:cloudtrail:${var.region}:${local.mock_account_id}:trail/${var.cloudtrail_name}"
    s3_key_prefix       = var.cloudtrail_s3_key_prefix
    source_account_ids  = local.cloudtrail_source_account_ids
    expected_log_prefix = "${local.cloudtrail_key_prefix}AWSLogs/"
  }
}
