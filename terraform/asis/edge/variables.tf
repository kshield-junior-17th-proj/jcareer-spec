###############################################################################
# terraform/asis/edge — 입력 변수
#
# data source 를 쓰지 않는다 (terraform/asis/README.md 「작성 규칙」).
# 자격증명 없는 plan 을 유지하려고, 평소 data source 로 조회할 값은 전부
# variable + 상수 기본값으로 받는다. 기본값은 전량 가상값이다.
###############################################################################

# --- 서비스 도메인 -------------------------------------------------------------

variable "domain_name" {
  description = <<-EOT
    Route 53 퍼블릭 호스팅 영역의 이름. 가상 고객사 J사의 합성 도메인이다.
    .example 은 RFC 2606 예약 TLD 이므로 실존 조직과 충돌하지 않는다.
  EOT
  type        = string
  default     = "jcareer.example"

  validation {
    condition     = length(trimspace(var.domain_name)) > 0
    error_message = "domain_name 은 비워 둘 수 없다."
  }
}

variable "service_hostname" {
  description = <<-EOT
    서비스 FQDN 의 호스트 부분. 빈 문자열이면 apex(domain_name 자체)를 쓴다.
    AS-IS 출처는 진입 도메인을 「Route 53 → CloudFront」로만 적고 호스트명을
    특정하지 않는다. 그래서 apex 기본값으로 두고 호출 측이 덮어쓰게 한다. ASSUMED.
  EOT
  type        = string
  default     = ""
}

variable "hosted_zone_comment" {
  description = "aws_route53_zone 의 comment. AS-IS 모델임을 콘솔에서도 드러낸다."
  type        = string
  default     = "J-Career AS-IS 재현 명세 — apply 금지"
}

# --- CloudFront 오리진 (ALB) ----------------------------------------------------
#
# ALB 는 terraform/asis/compute 모듈 소관이다. 이 모듈은 ALB 를 만들지 않고
# 오리진 좌표만 입력으로 받는다. 공유 terraform/asis/main.tf 가
# module.compute 의 출력을 여기에 연결한다.

variable "alb_origin_domain_name" {
  description = <<-EOT
    CloudFront 오리진이 되는 ALB 의 DNS 이름.
    기본값은 가상값이며 실제 배포된 ALB 가 아니다.
    근거: context/raw/인프라컨텍스트-외부협업용.md#2.2
          「ALB (Multi-AZ, TLS 1.2+ 종단)」
  EOT
  type        = string
  default     = "asis-jcareer-alb-000000000.ap-northeast-2.elb.amazonaws.com"

  validation {
    condition     = length(trimspace(var.alb_origin_domain_name)) > 0
    error_message = "alb_origin_domain_name 은 비워 둘 수 없다."
  }
}

variable "alb_origin_id" {
  description = "CloudFront 오리진 식별자. 캐시 동작이 참조한다."
  type        = string
  default     = "asis-jcareer-alb-origin"
}

variable "origin_ssl_protocols" {
  description = <<-EOT
    CloudFront → ALB 구간에서 허용하는 TLS 버전.
    근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2 「ALB … TLS 1.2+ 종단」
  EOT
  type        = list(string)
  default     = ["TLSv1.2"]
}

# --- CloudFront 배포 -----------------------------------------------------------

variable "cloudfront_minimum_protocol_version" {
  description = <<-EOT
    뷰어 ↔ CloudFront 구간의 최소 TLS 버전.
    출처는 ALB 종단의 TLS 1.2+ 만 확정하고 뷰어 구간은 기술하지 않는다. ASSUMED.
    AS-IS 결함으로 명세된 항목이 아니므로 docs/current/EXPECTED_FINDINGS.yaml
    승인 시 이 값이 GAP 을 지우거나 만들지 않는지 사람이 확인한다.
  EOT
  type        = string
  default     = "TLSv1.2_2021"
}

variable "cloudfront_price_class" {
  description = <<-EOT
    CloudFront 엣지 로케이션 범위. 출처에 기술이 없다. ASSUMED.
    서비스 이용자는 국내 구직자·기업 채용담당자다.
    근거: context/raw/인프라컨텍스트-외부협업용.md#2.2
  EOT
  type        = string
  default     = "PriceClass_200"
}

variable "cloudfront_cache_policy_id" {
  description = <<-EOT
    기본 캐시 동작의 관리형 캐시 정책 ID.
    기본값은 AWS 관리형 Managed-CachingDisabled 이다. 26화면 대부분이 인증 후
    동적 응답이므로 엣지 캐시를 끈 상태를 재현한다.
    상수로 받는 이유: data "aws_cloudfront_cache_policy" 는 plan 시점에 실제 API 를
    호출하므로 자격증명 없는 plan 계약(terraform/asis/README.md)에 걸린다.
  EOT
  type        = string
  default     = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
}

variable "cloudfront_origin_request_policy_id" {
  description = <<-EOT
    기본 캐시 동작의 관리형 오리진 요청 정책 ID.
    기본값은 AWS 관리형 Managed-AllViewer 이다. 인증 쿠키·헤더·쿼리스트링을
    ALB 로 그대로 전달해야 로그인 이후 화면이 성립한다.
    상수로 받는 이유는 cloudfront_cache_policy_id 와 같다.
  EOT
  type        = string
  default     = "216adef6-5c7f-47e4-b989-5492eafa07d3"
}

# --- WAFv2 ---------------------------------------------------------------------

variable "web_acl_name" {
  description = "CLOUDFRONT scope WAFv2 Web ACL 이름."
  type        = string
  default     = "asis-jcareer-edge"
}

variable "web_acl_metric_prefix" {
  description = "CloudWatch 지표 이름 접두. 영숫자와 하이픈·언더스코어만 허용된다."
  type        = string
  default     = "asisJcareerEdge"
}

# --- 태그 ----------------------------------------------------------------------

variable "common_tags" {
  description = <<-EOT
    terraform/asis/README.md 「필수 태그」가 요구하는 값.
    jk_source 는 리소스마다 근거가 다르므로 각 리소스에서 merge 로 덧붙인다.
  EOT
  type        = map(string)

  default = {
    jk_layer = "asis-model"
    jk_apply = "forbidden"
  }
}
