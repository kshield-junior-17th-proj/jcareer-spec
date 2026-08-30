# terraform/asis/security — SSM 계열 VPC Interface Endpoint
#
# AS-IS 관찰값: 운영 접근은 SSM Session Manager 이고 SSH 22 는 미개방이며 MFA 가 적용돼 있다.
#   context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2   (운영 접근 · Q11)
#   context/raw/SCENARIO_FACTS-가상고객사J사.md#9.4   (관리자 접근 경로 B)
#   context/raw/인프라컨텍스트-외부협업용.md#2.2      (Private App 서브넷 · SSM Session Manager)
#
# 그래서 이 모듈은 bastion 호스트·키페어·22번 인바운드 규칙을 만들지 않는다.
#   aws_instance (bastion)  — 의도적 미선언
#   aws_key_pair            — 의도적 미선언
#   22/tcp 인바운드 SG 규칙 — 의도적 미선언
# 이것은 GAP 이 아니라 AS-IS 에 이미 존재하는 통제다. 경로 A~F 여섯 중 통제되는 것이
# B 하나라는 서술의 그 B 다. 없앤다면 AS-IS 를 바꾸는 것이 된다.
#
# ASSUMED — 시나리오 원문은 "SSM Session Manager 사용"까지만 확정한다. 그 접근이
# interface endpoint 경유인지 NAT 경유인지는 원문에 없다. 이 재현 명세는 D02 §3.1 의
# "개인정보가 AWS 경계를 넘는 지점은 NAT → 외부 LLM API 한 구간뿐" 이라는 문장에 맞춰
# 관리 트래픽을 VPC 내부 endpoint 로 모델링했다. 확정 사실이 아니다.
#   context/raw/D02-진단대상-아키텍처-정의.md#3.1

locals {
  # SSM Session Manager 가 프라이빗 서브넷에서 동작하려면 세 서비스가 함께 필요하다.
  # 하나라도 빠지면 세션이 붙지 않는다. 그래서 세 개를 한 묶음으로 선언한다.
  ssm_interface_endpoints = {
    ssm = {
      service = "ssm"
      purpose = "Session Manager 제어 평면 API"
    }
    ssmmessages = {
      service = "ssmmessages"
      purpose = "세션 데이터 채널. SSM Agent 와 ECS Exec 이 공통으로 쓴다"
    }
    ec2messages = {
      service = "ec2messages"
      purpose = "SSM Agent 메시지 수신 경로"
    }
  }
}

resource "aws_vpc_endpoint" "ssm" {
  for_each = local.ssm_interface_endpoints

  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.region}.${each.value.service}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.app_subnet_ids
  security_group_ids  = var.vpc_endpoint_security_group_ids
  private_dns_enabled = true

  tags = merge(var.common_tags, {
    Name       = "${var.name_prefix}-vpce-${each.value.service}"
    jk_source  = "context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2"
    jk_purpose = each.value.purpose
  })
}

# GAP-EGRESS-01 [ABSENCE] 도메인 기반 아웃바운드 통제 없음
# 근거: context/proposals/docs-current/CURRENT_DECISIONS_DELTA.md#D-07
#       context/raw/인프라컨텍스트-외부협업용.md#2.2  (SG 목적지에 FQDN 지정 불가)
#
# 위 endpoint 세 개는 관리 트래픽을 VPC 안으로 끌어들이지만, 애플리케이션의 아웃바운드는
# 여전히 NAT Gateway 단일 경로다. 그 경로에 목적지를 판별하는 장치가 없다.
#   aws_networkfirewall_firewall                 — 의도적 미선언
#   aws_networkfirewall_firewall_policy          — 의도적 미선언
#   aws_networkfirewall_rule_group               — 의도적 미선언
#   aws_route53_resolver_firewall_rule_group     — 의도적 미선언
#   aws_route53_resolver_firewall_rule_group_association — 의도적 미선언
#   aws_route53_resolver_firewall_domain_list    — 의도적 미선언
# 이 리소스들을 선언하지 않는 것이 AS-IS 다. 추가하지 말 것.
