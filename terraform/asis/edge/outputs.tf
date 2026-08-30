###############################################################################
# terraform/asis/edge — 출력
#
# 다른 모듈이 엣지 계층을 참조할 때 쓰는 좌표다.
# 값 자체는 plan 시점에 대부분 미확정(known after apply)이며,
# 이 디렉토리는 apply 대상이 아니므로 실제 값이 채워지지 않는다.
# terraform/asis/README.md 「apply 하지 않는다」
###############################################################################

output "service_fqdn" {
  description = "구직자·기업 채용담당자가 접속하는 서비스 FQDN."
  value       = local.service_fqdn
}

output "hosted_zone_id" {
  description = "Route 53 퍼블릭 호스팅 영역 ID."
  value       = aws_route53_zone.primary.zone_id
}

output "hosted_zone_name_servers" {
  description = "위임에 쓰이는 네임서버 목록. 도메인 등록기관에 등록하는 값이다."
  value       = aws_route53_zone.primary.name_servers
}

output "cloudfront_distribution_id" {
  description = "CloudFront 배포 ID."
  value       = aws_cloudfront_distribution.service.id
}

output "cloudfront_distribution_arn" {
  description = "CloudFront 배포 ARN."
  value       = aws_cloudfront_distribution.service.arn
}

output "cloudfront_domain_name" {
  description = "CloudFront 배포의 기본 도메인. Route 53 alias 의 대상이다."
  value       = aws_cloudfront_distribution.service.domain_name
}

output "cloudfront_hosted_zone_id" {
  description = "CloudFront alias 대상 호스팅 영역 ID. 상수를 하드코딩하지 않고 여기서 얻는다."
  value       = aws_cloudfront_distribution.service.hosted_zone_id
}

output "cloudfront_origin_id" {
  description = "CloudFront 오리진 식별자. terraform/asis/compute 의 ALB 와 짝이 된다."
  value       = var.alb_origin_id
}

output "acm_certificate_arn" {
  description = "CloudFront 뷰어 인증서 ARN (us-east-1)."
  value       = aws_acm_certificate.service.arn
}

output "web_acl_arn" {
  description = <<-EOT
    CLOUDFRONT scope WAFv2 Web ACL ARN (us-east-1).
    CloudFront 배포의 web_acl_id 가 이 값을 받는다.
  EOT
  value       = aws_wafv2_web_acl.edge.arn
}

output "web_acl_id" {
  description = "CLOUDFRONT scope WAFv2 Web ACL ID."
  value       = aws_wafv2_web_acl.edge.id
}

output "web_acl_managed_rule_groups" {
  description = <<-EOT
    이 Web ACL 이 적용하는 관리형 규칙 그룹. 커스텀 규칙은 없다.
    근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2
    GAP-WAF-01 의 증적으로 사람이 읽는 값이며, 판정값이 아니다.
  EOT
  value       = [for r in aws_wafv2_web_acl.edge.rule : r.name]
}
