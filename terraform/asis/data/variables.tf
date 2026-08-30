# terraform/asis/data — 입력 변수
#
# data source 금지 계약(terraform/asis/README.md)에 따라 AZ 이름 · 계정 ID ·
# 리전처럼 런타임 조회가 필요한 값은 전부 상수 기본값 variable 로 받는다.
# 네트워크 식별자(서브넷 · 보안그룹)는 기본값이 없다. 공유 루트가 network 모듈
# 출력으로 주입해야 하며, 누락되면 plan 이 조용히 통과하지 않고 즉시 실패한다.

# ---------------------------------------------------------------------------
# 공통
# ---------------------------------------------------------------------------

variable "name_prefix" {
  description = "리소스 이름 접두사."
  type        = string
  default     = "jcareer"
}

variable "region" {
  description = <<-EOT
    리전 상수. IAM 정책 문서의 ARN 조립에만 쓴다.
    data "aws_region" 금지 계약의 대체 입력이다. 근거: terraform/asis/README.md
  EOT
  type        = string
  default     = "ap-northeast-2"
}

variable "account_id" {
  description = <<-EOT
    계정 식별자 상수. 공개 기본값은 마스킹하고 mock plan에서만 형식값으로 바꾼다.
    data "aws_caller_identity" 금지 계약의 대체 입력이다.
  EOT
  type        = string
  default     = "redacted"
}

variable "common_tags" {
  description = "공유 루트가 내려주는 공통 태그. 모듈 필수 태그와 merge 된다."
  type        = map(string)
  default     = {}
}

# ---------------------------------------------------------------------------
# 네트워크 연결점 — 기본값 없음 (공유 루트가 network 모듈에서 주입)
# ---------------------------------------------------------------------------

variable "data_subnet_ids" {
  description = <<-EOT
    Private Data 서브넷 ID 2개. 10.0.20.0/24 (AZ 2a) · 10.0.21.0/24 (AZ 2c).
    근거: context/raw/인프라컨텍스트-외부협업용.md#2.2
  EOT
  type        = list(string)
}

variable "db_security_group_ids" {
  description = "RDS 에 붙는 보안그룹 ID 목록. network 모듈 출력."
  type        = list(string)
}

variable "cache_security_group_ids" {
  description = "ElastiCache 에 붙는 보안그룹 ID 목록. network 모듈 출력."
  type        = list(string)
}

# ---------------------------------------------------------------------------
# RDS PostgreSQL
# ---------------------------------------------------------------------------

variable "db_engine_version" {
  description = "PostgreSQL 엔진 버전. 원문에 명시 없음 — ASSUMED."
  type        = string
  default     = "15.7"
}

variable "db_instance_class" {
  description = "Primary 인스턴스 클래스. 원문에 명시 없음 — ASSUMED."
  type        = string
  default     = "db.m6i.large"
}

variable "db_replica_instance_class" {
  description = "읽기 복제본 인스턴스 클래스. 원문에 명시 없음 — ASSUMED."
  type        = string
  default     = "db.m6i.large"
}

variable "db_allocated_storage" {
  description = "할당 스토리지(GiB). 원문에 명시 없음 — ASSUMED."
  type        = number
  default     = 200
}

variable "db_name" {
  description = "초기 데이터베이스 이름."
  type        = string
  default     = "jcareer"
}

variable "db_master_username" {
  description = "마스터 사용자 이름."
  type        = string
  default     = "jcareer_admin"
}

variable "db_master_password" {
  description = <<-EOT
    마스터 비밀번호. 값을 저장소에 커밋하지 않는다.

    GAP-SEC-01 재현 지점 — J사는 Secrets Manager 를 쓰지 않고 자격증명을
    애플리케이션 환경변수(실제 주입원은 GitHub Actions Secrets)로 다룬다.
    근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#5.2

    이 모듈은 aws_secretsmanager_secret 을 선언하지 않는다. 선언하면 AS-IS 가
    사라진다. 근거: terraform/asis/ABSENCE_MANIFEST.md
  EOT
  type        = string
  default     = null
  sensitive   = true
}

# ---------------------------------------------------------------------------
# ElastiCache
# ---------------------------------------------------------------------------

variable "cache_engine_version" {
  description = "Redis 엔진 버전. 원문에 명시 없음 — ASSUMED."
  type        = string
  default     = "7.0"
}

variable "cache_node_type" {
  description = "캐시 노드 타입. 원문에 명시 없음 — ASSUMED."
  type        = string
  default     = "cache.m6g.large"
}

variable "cache_num_cache_clusters" {
  description = <<-EOT
    캐시 노드 수. Data 서브넷이 2-AZ 이므로 2 로 둔다.
    노드 수 자체는 원문에 없다 — ASSUMED.
    근거(서브넷 2-AZ): context/raw/인프라컨텍스트-외부협업용.md#2.2
  EOT
  type        = number
  default     = 2
}

# ---------------------------------------------------------------------------
# S3 — ALB 액세스 로그 버킷
# ---------------------------------------------------------------------------

variable "alb_log_prefix" {
  description = "ALB 액세스 로그 S3 키 접두사. compute 모듈의 ALB 설정과 일치해야 한다."
  type        = string
  default     = "alb"
}

variable "alb_log_retention_days" {
  description = <<-EOT
    ALB 액세스 로그 보존 일수.
    근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2 「액세스 로그 S3 적재, 보존 90일」
  EOT
  type        = number
  default     = 90
}

variable "elb_log_delivery_account_id" {
  description = <<-EOT
    ALB 액세스 로그를 쓰는 AWS ELB 서비스 계정 식별자. 공개 기본값은 마스킹한다.
    data source 금지 계약(terraform/asis/README.md)의 대체 입력이다.
    리전을 바꾸면 이 값도 함께 바꿔야 한다.
  EOT
  type        = string
  default     = "redacted"
}

# ---------------------------------------------------------------------------
# S3 — CloudTrail 버킷 정책 입력 contract
# ---------------------------------------------------------------------------
#
# CloudTrail 리소스(aws_cloudtrail) 자체는 observability 모듈 소유다.
# 이 모듈은 로그 목적지 버킷과 그 버킷 정책만 소유한다.
# 아래 세 변수가 두 모듈 사이의 계약이다. 값이 어긋나면 정책의 aws:SourceArn
# 조건이 실제 trail 과 맞지 않는다.

variable "cloudtrail_name" {
  description = <<-EOT
    CloudTrail trail 이름. 버킷 정책의 aws:SourceArn 조건 조립에 쓴다.
    observability 모듈의 aws_cloudtrail.name 과 동일해야 한다.
  EOT
  type        = string
  default     = "jcareer-management-events"
}

variable "cloudtrail_s3_key_prefix" {
  description = <<-EOT
    CloudTrail 로그 키 접두사. observability 모듈의 aws_cloudtrail.s3_key_prefix 와
    동일해야 한다. 빈 문자열이면 접두사 없이 AWSLogs/ 아래에 쌓인다.
  EOT
  type        = string
  default     = ""
}

variable "cloudtrail_source_account_ids" {
  description = <<-EOT
    로그를 쓰는 CloudTrail 소유 계정 ID 목록. 단일 계정 구성이면 [var.account_id] 다.
    근거(단일 계정·단일 리전): context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2
  EOT
  type        = list(string)
  default     = []
}
