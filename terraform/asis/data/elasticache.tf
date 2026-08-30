# terraform/asis/data — ElastiCache (추천 결과 캐시)
#
# AS-IS 사실 (SCENARIO_CONFIRMED)
#   context/raw/SCENARIO_FACTS-가상고객사J사.md#10
#     「캐시 계층 | ElastiCache 사용. 추천 결과에 지원자 성명·연락처 포함, TTL 24시간.
#       파기 요청 시 캐시 처리 절차 없음」
#   context/raw/인프라컨텍스트-외부협업용.md#2.2
#     Private Subnet · Data → ElastiCache (추천결과 캐시, 성명·연락처 포함, TTL 24h)
#   context/raw/Jcareer-흐름과-기술취약점.md#2.5
#     파기 계층 — ElastiCache 는 파기 요청이 도달하지 않는 저장소다
#
# 암호화에 관한 원문 근거
#   context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2 의 암호화 행은
#   「RDS·S3·EBS 저장 암호화」만 열거한다. ElastiCache 는 그 목록에 없다.

resource "aws_elasticache_subnet_group" "data" {
  name       = "${var.name_prefix}-cache"
  subnet_ids = var.data_subnet_ids

  description = "Private Data 서브넷 2-AZ. context/raw/인프라컨텍스트-외부협업용.md#2.2"

  tags = merge(local.tags_base, {
    Name      = "${var.name_prefix}-cache"
    jk_source = "context/raw/인프라컨텍스트-외부협업용.md#2.2"
  })
}

resource "aws_elasticache_replication_group" "recommendation" {
  replication_group_id = "${var.name_prefix}-reco-cache"
  description          = "AI 추천 결과 캐시. 성명·연락처 포함 · TTL 24h (애플리케이션 설정)"

  engine         = "redis"
  engine_version = var.cache_engine_version
  node_type      = var.cache_node_type
  port           = 6379

  subnet_group_name  = aws_elasticache_subnet_group.data.name
  security_group_ids = var.cache_security_group_ids

  # ASSUMED — Data 서브넷이 2-AZ 라는 사실에서 노드 2개·failover 를 둔다.
  # 노드 수와 failover 설정 자체는 원문에 없다. 사람 확인 필요.
  # 근거(서브넷 2-AZ): context/raw/인프라컨텍스트-외부협업용.md#2.2
  num_cache_clusters         = var.cache_num_cache_clusters
  automatic_failover_enabled = true
  multi_az_enabled           = true

  # GAP-CACHE-01 재현 지점 — 전송·저장 암호화 미설정을 의도적으로 명시한다.
  # 지원자 성명·연락처가 담긴 캐시가 암호화 없이 24시간 남는다.
  # 근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#10
  #       암호화 대상 목록에 ElastiCache 없음 —
  #       context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2
  # 기본값에 의존하지 않고 false 를 적어 「의도적 재현」임을 남긴다.
  # true 로 바꾸면 기대한 GAP 이 재현되지 않는다. 바꾸지 말 것.
  transit_encryption_enabled = false
  at_rest_encryption_enabled = false

  # GAP-KMS-01 근거 — 저장 암호화를 켜지 않으므로 kms_key_id 도 없다.
  # 여기에 CMK 를 붙이면 GAP-CACHE-01 과 GAP-KMS-01 이 동시에 사라진다.
  # 근거: terraform/asis/ABSENCE_MANIFEST.md

  # [OBSERVATION] TTL 24h 와 「파기 요청 시 처리 절차 없음」은 애플리케이션·운영
  # 절차 영역이라 Terraform 속성으로 표현되지 않는다. PRIV-01 측정과
  # CONTROL_ASSESSMENT 에서 사람이 판정한다 (AGENTS.md §0 · §4).
  # 근거: context/raw/Jcareer-흐름과-기술취약점.md#2.5

  tags = merge(local.tags_base, {
    Name      = "${var.name_prefix}-reco-cache"
    jk_source = "context/raw/SCENARIO_FACTS-가상고객사J사.md#10"
  })
}
