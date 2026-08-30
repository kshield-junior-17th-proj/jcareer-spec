###############################################################################
# terraform/asis/edge — 엣지 계층 AS-IS 재현 명세
#
#   구직자 / 기업 채용담당자
#        │
#     Route 53 ──▶ CloudFront ──▶ AWS WAF ──▶ ALB (terraform/asis/compute 소관)
#                                  관리형 규칙셋 Common + SQLi
#
# 근거
#   context/raw/인프라컨텍스트-외부협업용.md#2.2
#   context/raw/D02-진단대상-아키텍처-정의.md#3.1
#   context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2
#
# 이 코드는 J사가 보유한 IaC 가 아니다. J사 인프라는 콘솔 수동 구성이며
# (context/raw/SCENARIO_FACTS-가상고객사J사.md#9.5) 이 파일은 컨설팅팀이 도면과
# 시나리오 문서를 근거로 역으로 작성한 재현 명세다. 역으로 작성해야 했다는 사실
# 자체가 GAP-IAC-01 의 증적이다.  terraform/asis/README.md
#
# apply 하지 않는다. AWS 자격증명을 요구하지 않는다. CD 워크플로를 만들지 않는다.
#
# 결함 보존 원칙 — 이 파일의 미선언은 전부 의도적이다. 「보안 모범사례」로 채우면
# AS-IS 가 사라지고 진단 대상이 없어진다.  AGENTS.md
#
# 블록 순서는 위 도면의 트래픽 순서를 따른다. terraform 의 참조 순서와는 반대다.
###############################################################################

locals {
  service_fqdn = var.service_hostname == "" ? var.domain_name : "${var.service_hostname}.${var.domain_name}"

  # 엣지 계층 전반의 근거 앵커. 리소스별로 더 좁은 앵커가 있으면 거기서 덮어쓴다.
  source_infra_2_2 = "context/raw/인프라컨텍스트-외부협업용.md#2.2"
  source_facts_9_2 = "context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2"
}

###############################################################################
# 1. Route 53 — 퍼블릭 호스팅 영역과 서비스 alias
#
# AS-IS: 「Route 53 → CloudFront」 한 홉이 전부다.
#        context/raw/인프라컨텍스트-외부협업용.md#2.2
#        context/raw/D02-진단대상-아키텍처-정의.md#3.1
###############################################################################

resource "aws_route53_zone" "primary" {
  name    = var.domain_name
  comment = var.hosted_zone_comment

  tags = merge(var.common_tags, {
    jk_source = local.source_infra_2_2
  })
}

# CloudFront 배포로 향하는 alias A 레코드.
# alias 의 zone_id 는 aws_cloudfront_distribution 의 출력 속성에서 온다.
# data "aws_cloudfront_distribution" 이나 상수 Z2FDTNDATAQYW2 를 쓰지 않는 이유는
# 자격증명 없는 plan 계약(terraform/asis/README.md)과 하드코딩 회피 둘 다다.
resource "aws_route53_record" "service_alias" {
  zone_id = aws_route53_zone.primary.zone_id
  name    = local.service_fqdn
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.service.domain_name
    zone_id                = aws_cloudfront_distribution.service.hosted_zone_id
    evaluate_target_health = false
  }
}

# 미선언 — IPv6 AAAA alias
# 출처는 IPv6 제공 여부를 기술하지 않는다. 없는 사실을 만들지 않으려고
# aws_cloudfront_distribution 의 is_ipv6_enabled 를 provider 기본값(false)에 두고
# AAAA 레코드도 만들지 않는다. UNVERIFIED — 구성 인터뷰에서 확인한다.

# GAP-EGRESS-01 [ABSENCE] 도메인 기반 아웃바운드 통제 없음
# 근거: context/raw/인프라컨텍스트-외부협업용.md#2.2
#         「도메인 기반 아웃바운드 통제 | 없음 — SG 목적지에 FQDN 지정 불가」
#       context/proposals/docs-current/CURRENT_DECISIONS_DELTA.md#D-07  (비권위 초안)
#       terraform/asis/ABSENCE_MANIFEST.md
#
# Route 53 Resolver DNS Firewall 이 있었다면 llm-gateway 의 외부 목적지를 FQDN 으로
# 끊을 수 있었다. J사에는 없다. 이 저장소에서 Route 53 을 다루는 모듈이 여기 하나뿐이라
# 근거 주석을 근거에 가장 가까운 이 자리에 둔다. 추가하지 말 것.
#
#   aws_route53_resolver_firewall_rule_group              — 의도적 미선언
#   aws_route53_resolver_firewall_domain_list             — 의도적 미선언
#   aws_route53_resolver_firewall_rule_group_association  — 의도적 미선언
#
# 짝이 되는 aws_networkfirewall_firewall 미선언은 terraform/asis/network 소관이다.

# 미선언 — Route 53 쿼리 로깅 (aws_route53_query_log)
# 출처의 로깅 목록은 ALB 액세스 로그(S3, 90일) · VPC Flow Logs(CloudWatch, 30일) ·
# CloudTrail(관리 이벤트만) · 접속기록(CloudWatch, 1년)까지다.
# context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2
# DNS 쿼리 로그는 그 목록에 없으므로 선언하지 않는다.
# 명세된 GAP 이 아니다. GAP ID 를 새로 만들지 않는다 — 판정은 사람이 한다.

###############################################################################
# 2. CloudFront — ALB 오리진 배포
#
# AS-IS: CloudFront 가 인터넷 진입점이고 오리진은 퍼블릭 서브넷의 ALB 다.
#        ALB 는 TLS 1.2+ 종단이다.
#        context/raw/인프라컨텍스트-외부협업용.md#2.2
#        context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2
#
# Web ACL 은 CloudFront 에 연결된다. ALB 가 아니다.
#        context/raw/인프라컨텍스트-외부협업용.md#2.2
#          「Route 53 ──▶ CloudFront ──▶ AWS WAF   ← Web ACL은 CloudFront에 연결」
# 그래서 aws_wafv2_web_acl_association 을 쓰지 않고 배포의 web_acl_id 로 건다.
###############################################################################

resource "aws_cloudfront_distribution" "service" {
  enabled     = true
  comment     = "J-Career AS-IS 재현 명세 — 구직자·기업 진입점. apply 금지"
  aliases     = [local.service_fqdn]
  price_class = var.cloudfront_price_class

  # WAFv2 는 ARN 을 받는다. scope = CLOUDFRONT 이므로 us-east-1 의 Web ACL 이다.
  web_acl_id = aws_wafv2_web_acl.edge.arn

  origin {
    domain_name = var.alb_origin_domain_name
    origin_id   = var.alb_origin_id

    custom_origin_config {
      http_port                = 80
      https_port               = 443
      origin_protocol_policy   = "https-only"
      origin_ssl_protocols     = var.origin_ssl_protocols
      origin_read_timeout      = 30
      origin_keepalive_timeout = 5
    }
  }

  # 26화면 중 공개 2화면을 뺀 나머지가 인증 후 동적 응답이다.
  # context/raw/D02-진단대상-아키텍처-정의.md#3.1
  # 엣지 캐시를 끄고 인증 컨텍스트를 오리진으로 그대로 넘기는 상태를 재현한다.
  default_cache_behavior {
    target_origin_id       = var.alb_origin_id
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    cache_policy_id          = var.cloudfront_cache_policy_id
    origin_request_policy_id = var.cloudfront_origin_request_policy_id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate.service.arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = var.cloudfront_minimum_protocol_version
  }

  tags = merge(var.common_tags, {
    jk_source = local.source_infra_2_2
  })
}

# 미선언 — CloudFront 액세스 로그 (logging_config)
# 출처가 확정하는 액세스 로그는 ALB 것 하나다.
# context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2
#   「ALB | Multi-AZ · TLS 1.2+ 종단 · 액세스 로그 S3 적재, 보존 90일 | Q02」
# CloudFront 배포 로그는 어느 출처에도 없다. 없는 것을 만들지 않는다.
# 대상 S3 버킷도 terraform/asis/data 소관이라 이 모듈에서 참조할 수 없다.
# 명세된 GAP 이 아니다. 구성 인터뷰 Q02 의 확인 범위로 올린다.
# context/raw/D02-진단대상-아키텍처-정의.md#3.4

# 미선언 — CloudFront 함수 · Lambda@Edge · 오리진 접근 제어(OAC)
# 오리진이 S3 가 아니라 ALB 이므로 OAC 는 성립하지 않는다.
# 엣지 함수는 도면에 없다. terraform/asis/README.md 「도면에 없는 리소스를 추가하지 않는다」

###############################################################################
# 3. 뷰어 인증서 — ACM (us-east-1)
#
# CloudFront 뷰어 인증서는 us-east-1 에만 둘 수 있다. AWS API 제약이며
# 「리전 ap-northeast-2 단일」(context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2)
# 진술과 모순되지 않는다. 자세한 계약은 terraform/asis/edge/versions.tf 참조.
###############################################################################

resource "aws_acm_certificate" "service" {
  provider = aws.us_east_1

  domain_name       = local.service_fqdn
  validation_method = "DNS"

  tags = merge(var.common_tags, {
    jk_source = local.source_infra_2_2
  })

  lifecycle {
    create_before_destroy = true
  }
}

# 미선언 — DNS 검증 레코드와 aws_acm_certificate_validation
# 재현 명세의 한계이지 AS-IS 결함이 아니다.
# domain_validation_options 는 apply 전까지 값이 정해지지 않는다. 그 위에서
# for_each 를 돌리면 apply 전 결정 불가로 plan 이 깨지고, 자격증명 없는 plan 계약
# (terraform/asis/README.md)이 성립하지 않는다.
# 이 디렉토리는 apply 대상이 아니므로 검증 레코드를 만들 실익도 없다.

###############################################################################
# 4. AWS WAF — CLOUDFRONT scope Web ACL (us-east-1)
#
# AS-IS: 관리형 규칙셋 두 개뿐이다.
#        context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2
#          「엣지 | Route 53 → CloudFront → AWS WAF 적용
#            (관리형 규칙셋 AWSManagedRulesCommonRuleSet + SQLi) | Q01」
#        context/raw/인프라컨텍스트-외부협업용.md#2.2
#          「(관리형 규칙셋 Common + SQLi)」
###############################################################################

resource "aws_wafv2_web_acl" "edge" {
  provider = aws.us_east_1

  name        = var.web_acl_name
  description = "J-Career AS-IS 엣지 Web ACL — 관리형 규칙셋만. apply 금지"
  scope       = "CLOUDFRONT"

  default_action {
    allow {}
  }

  # 규칙 1 — AWSManagedRulesCommonRuleSet
  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 1

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.web_acl_metric_prefix}CommonRuleSet"
      sampled_requests_enabled   = true
    }
  }

  # 규칙 2 — AWSManagedRulesSQLiRuleSet
  rule {
    name     = "AWSManagedRulesSQLiRuleSet"
    priority = 2

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesSQLiRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.web_acl_metric_prefix}SQLiRuleSet"
      sampled_requests_enabled   = true
    }
  }

  # GAP-WAF-01 [ABSENCE] WAF 자유서술 입력 커스텀 규칙 없음 — 관리형 규칙셋만
  # 근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2
  #         「WAF 자유서술 입력 규칙 | 없음. 이력서 본문·자기소개서에 적용되는
  #           커스텀 규칙 미수립 | Q01」
  #       context/raw/인프라컨텍스트-외부협업용.md#2.2
  #         「WAF 자유서술 입력 커스텀 규칙 | 없음 — 이력서 본문에 적용되는 규칙 미수립」
  #       terraform/asis/ABSENCE_MANIFEST.md
  #
  # 위 규칙 두 개 다음에 아무것도 오지 않는 것이 AS-IS 다. 특히 아래를 만들지 말 것.
  #
  #   aws_wafv2_regex_pattern_set                          — 의도적 미선언
  #   rule.statement.regex_pattern_set_reference_statement — 의도적 미선언
  #   rule.statement.byte_match_statement (커스텀)          — 의도적 미선언
  #   rule.statement.rate_based_statement                  — 의도적 미선언
  #
  # 승인된 EXPECTED_FINDINGS 명세로 검사기가 이 Web ACL 에
  # rule.statement.regex_pattern_set_reference_statement 가 없는지 확인한다.
  # 하나라도 선언되면 재현 실패다. scripts/check_expected_findings.py
  #
  # 왜 이게 이 프로젝트에서 중요한가 — 관리형 Common + SQLi 는 SQL 구문과 알려진
  # 공격 시그니처를 본다. 프롬프트 인젝션은 문법상 정상적인 한국어 문장이고
  # 이력서 본문·자기소개서·GitHub description·README 로 들어온다.
  # context/raw/D02-진단대상-아키텍처-정의.md#3.1 (신뢰경계 TB③ · TB⑥)
  # 관리형 규칙셋이 있다는 사실을 「엣지에서 막힌다」로 읽지 않는다.
  # 다만 충족/미충족 판정은 사람이 한다. 이 주석은 근거 표시이지 판정이 아니다.

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.web_acl_metric_prefix}WebAcl"
    sampled_requests_enabled   = true
  }

  tags = merge(var.common_tags, {
    jk_source = local.source_facts_9_2
  })
}

# 미선언 — WAF 로깅 (aws_wafv2_web_acl_logging_configuration)
# 출처가 WAF 로그 적재를 기술하지 않는다.
# context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2 의 로깅 목록에 WAF 는 없다.
# 대상 로그 그룹·버킷도 terraform/asis/observability · terraform/asis/data 소관이다.
# 명세된 GAP 이 아니다. 구성 인터뷰 Q01 의 확인 범위로 올린다.
# context/raw/D02-진단대상-아키텍처-정의.md#3.4

# 미선언 — 엣지 계층의 KMS 고객관리형 키
# GAP-KMS-01 [ABSENCE] CMK 미사용 · 회전 정책 없음
# 근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2
#         「암호화 | RDS·S3·EBS 저장 암호화 (AWS 관리형 키). CMK 미사용, 회전 정책 없음」
#       terraform/asis/ABSENCE_MANIFEST.md
# 이 모듈에서 aws_kms_key 가 나올 자리는 CloudFront/WAF 로그 암호화뿐이고
# 그 로그 자체가 미선언이다. 추가하지 말 것.
#
#   aws_kms_key — 의도적 미선언
