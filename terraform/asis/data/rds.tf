# terraform/asis/data — RDS PostgreSQL
#
# AS-IS 사실 (SCENARIO_CONFIRMED)
#   context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2
#     「RDS | PostgreSQL Multi-AZ · 자동 백업 보존 7일 · PITR 활성 · 장애조치 시험 이력 없음」
#     「암호화 | RDS·S3·EBS 저장 암호화 (AWS 관리형 키). CMK 미사용, 회전 정책 없음」
#   context/raw/인프라컨텍스트-외부협업용.md#2.2
#     Private Subnet · Data 10.0.20.0/24 · 10.0.21.0/24
#     RDS PostgreSQL Primary / Standby (Multi-AZ, 백업 7일, PITR) · RDS 읽기 복제본
#   context/raw/D02-진단대상-아키텍처-정의.md#3.1
#     AZ-2a Private Data → RDS PostgreSQL (Primary) / AZ-2c → RDS Standby

# ---------------------------------------------------------------------------
# 서브넷 그룹
# ---------------------------------------------------------------------------

resource "aws_db_subnet_group" "data" {
  name       = "${var.name_prefix}-data"
  subnet_ids = var.data_subnet_ids

  description = "Private Data 서브넷 2-AZ. context/raw/인프라컨텍스트-외부협업용.md#2.2"

  tags = merge(local.tags_base, {
    Name      = "${var.name_prefix}-data"
    jk_source = "context/raw/인프라컨텍스트-외부협업용.md#2.2"
  })
}

# ---------------------------------------------------------------------------
# Primary (Multi-AZ)
# ---------------------------------------------------------------------------

resource "aws_db_instance" "primary" {
  identifier     = "${var.name_prefix}-postgres-primary"
  engine         = "postgres"
  engine_version = var.db_engine_version
  instance_class = var.db_instance_class

  allocated_storage = var.db_allocated_storage
  db_name           = var.db_name
  username          = var.db_master_username

  # GAP-SEC-01 근거 — Secrets Manager 를 경유하지 않는다.
  # J사는 API 키·자격증명을 환경변수로 다루고 실제 주입원은 GitHub Actions Secrets 다.
  # 근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#5.2
  # manage_master_user_password 를 켜면 aws_secretsmanager_secret 이 생겨 AS-IS 가 사라진다.
  # 근거: terraform/asis/ABSENCE_MANIFEST.md
  password = var.db_master_password

  port                   = 5432
  db_subnet_group_name   = aws_db_subnet_group.data.name
  vpc_security_group_ids = var.db_security_group_ids
  publicly_accessible    = false

  # SCENARIO_CONFIRMED — Multi-AZ. context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2
  multi_az = true

  # GAP-RDS-01 재현 지점 — 자동 백업 보존 7일.
  # 근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2
  # 백업 창이 열려 있으므로 PITR 이 활성이라는 원문 서술과 일치한다.
  # 이 값을 늘리면 기대한 GAP 이 재현되지 않는다. 늘리지 말 것.
  backup_retention_period = 7

  # GAP-KMS-01 근거 — 저장 암호화는 켜져 있으나 AWS 관리형 키다.
  # kms_key_id 를 지정하지 않는 것이 AS-IS 다. aws_kms_key 를 만들지 말 것.
  # 근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2 · terraform/asis/ABSENCE_MANIFEST.md
  storage_encrypted = true

  # [OBSERVATION] 원문은 「장애조치 시험 이력 없음」이라고만 적는다. 시험 이력은
  # Terraform 속성으로 표현되지 않는다. 판정은 사람이 한다 (AGENTS.md §0).
  # 근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2

  tags = merge(local.tags_base, {
    Name      = "${var.name_prefix}-postgres-primary"
    jk_source = "context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2"
  })
}

# ---------------------------------------------------------------------------
# 읽기 복제본
# ---------------------------------------------------------------------------

resource "aws_db_instance" "replica" {
  identifier          = "${var.name_prefix}-postgres-replica"
  replicate_source_db = aws_db_instance.primary.identifier
  instance_class      = var.db_replica_instance_class

  vpc_security_group_ids = var.db_security_group_ids
  publicly_accessible    = false
  multi_az               = false

  # 동일 리전 복제본은 Primary 의 서브넷 그룹을 승계한다.
  # 저장 암호화도 Primary 에서 승계되며 CMK 는 여전히 쓰지 않는다 (GAP-KMS-01).
  # 근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2
  # storage_encrypted 를 여기 다시 적으면 replicate_source_db 와 조합이 어긋난다.
  # 그래서 비워 두었고, 스캐너가 이 복제본을 「미암호화」로 잡을 수 있다.
  # 그 결과는 명세 밖 발견으로 사람에게 올라간다. 우리는 판정하지 않는다.

  # [OBSERVATION] 관리자 접근 경로 C — BI 분석 담당 2명이 이 복제본을
  # 가명처리 없이 원본 컬럼으로 조회한다. 접근 통제는 이 모듈 밖(IAM·BI 도구)이며
  # Terraform 속성으로 재현되지 않는다. 판정은 사람이 한다.
  # 근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#9.4
  #       context/raw/Jcareer-흐름과-기술취약점.md#3

  tags = merge(local.tags_base, {
    Name      = "${var.name_prefix}-postgres-replica"
    jk_source = "context/raw/인프라컨텍스트-외부협업용.md#2.2"
  })
}
