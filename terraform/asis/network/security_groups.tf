locals {
  service_ports = {
    web         = 3000
    api         = 8000
    agent       = 8100
    llm-gateway = 8200
  }
}

resource "aws_security_group" "alb" {
  name                   = "${var.name_prefix}-alb-sg"
  description            = "Public HTTPS ingress for the J-Career ALB"
  vpc_id                 = aws_vpc.this.id
  revoke_rules_on_delete = true

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-alb-sg"
  })
}

resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  security_group_id = aws_security_group.alb.id
  description       = "HTTPS from the public CloudFront origin path"
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-alb-https-ingress"
  })
}

resource "aws_vpc_security_group_egress_rule" "alb_to_ecs" {
  for_each = local.service_ports

  security_group_id            = aws_security_group.alb.id
  description                  = "ALB traffic and health checks to the ${each.key} task"
  referenced_security_group_id = aws_security_group.ecs.id
  from_port                    = each.value
  to_port                      = each.value
  ip_protocol                  = "tcp"

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-alb-to-ecs-${each.key}"
  })
}

resource "aws_security_group" "ecs" {
  name                   = "${var.name_prefix}-ecs-sg"
  description            = "Shared AS-IS ECS task security group"
  vpc_id                 = aws_vpc.this.id
  revoke_rules_on_delete = true

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-ecs-sg"
  })
}

resource "aws_vpc_security_group_ingress_rule" "ecs_from_alb" {
  for_each = local.service_ports

  security_group_id            = aws_security_group.ecs.id
  description                  = "${each.key} task traffic from the ALB"
  referenced_security_group_id = aws_security_group.alb.id
  from_port                    = each.value
  to_port                      = each.value
  ip_protocol                  = "tcp"

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-ecs-${each.key}-from-alb"
  })
}

resource "aws_vpc_security_group_ingress_rule" "ecs_api_from_ecs" {
  security_group_id            = aws_security_group.ecs.id
  description                  = "Internal web-to-api traffic"
  referenced_security_group_id = aws_security_group.ecs.id
  from_port                    = 8000
  to_port                      = 8000
  ip_protocol                  = "tcp"

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-ecs-api-internal"
  })
}

resource "aws_vpc_security_group_ingress_rule" "ecs_agent_from_ecs" {
  security_group_id            = aws_security_group.ecs.id
  description                  = "Internal api-to-agent traffic"
  referenced_security_group_id = aws_security_group.ecs.id
  from_port                    = 8100
  to_port                      = 8100
  ip_protocol                  = "tcp"

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-ecs-agent-internal"
  })
}

resource "aws_vpc_security_group_ingress_rule" "ecs_llm_gateway_from_ecs" {
  security_group_id            = aws_security_group.ecs.id
  description                  = "Internal agent-to-llm-gateway traffic"
  referenced_security_group_id = aws_security_group.ecs.id
  from_port                    = 8200
  to_port                      = 8200
  ip_protocol                  = "tcp"

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-ecs-llm-gateway-internal"
  })
}

# GAP-EGRESS-01 [ABSENCE] 도메인 기반 아웃바운드 통제 없음.
# 근거: context/raw/인프라컨텍스트-외부협업용.md#2.2
# AS-IS 보존: Network Firewall/Route 53 Resolver Firewall을 추가하지 않는다.
resource "aws_vpc_security_group_egress_rule" "ecs_unrestricted" {
  security_group_id = aws_security_group.ecs.id
  description       = "AS-IS task egress without domain-based filtering"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-ecs-unrestricted-egress"
  })
}

resource "aws_security_group" "rds" {
  name                   = "${var.name_prefix}-rds-sg"
  description            = "PostgreSQL access from ECS tasks"
  vpc_id                 = aws_vpc.this.id
  revoke_rules_on_delete = true

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-rds-sg"
  })
}

resource "aws_vpc_security_group_ingress_rule" "rds_postgresql_from_ecs" {
  security_group_id            = aws_security_group.rds.id
  description                  = "PostgreSQL from ECS tasks"
  referenced_security_group_id = aws_security_group.ecs.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-rds-from-ecs"
  })
}

resource "aws_security_group" "cache" {
  name                   = "${var.name_prefix}-cache-sg"
  description            = "ElastiCache access from ECS tasks"
  vpc_id                 = aws_vpc.this.id
  revoke_rules_on_delete = true

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-cache-sg"
  })
}

resource "aws_vpc_security_group_ingress_rule" "cache_redis_from_ecs" {
  security_group_id            = aws_security_group.cache.id
  description                  = "Redis from ECS tasks"
  referenced_security_group_id = aws_security_group.ecs.id
  from_port                    = 6379
  to_port                      = 6379
  ip_protocol                  = "tcp"

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-cache-from-ecs"
  })
}

resource "aws_security_group" "endpoint" {
  name                   = "${var.name_prefix}-endpoint-sg"
  description            = "Interface endpoint HTTPS access from ECS tasks"
  vpc_id                 = aws_vpc.this.id
  revoke_rules_on_delete = true

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-endpoint-sg"
  })
}

resource "aws_vpc_security_group_ingress_rule" "endpoint_https_from_ecs" {
  security_group_id            = aws_security_group.endpoint.id
  description                  = "HTTPS from ECS tasks to interface endpoints"
  referenced_security_group_id = aws_security_group.ecs.id
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-endpoint-from-ecs"
  })
}
