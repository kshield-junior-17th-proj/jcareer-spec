###############################################################################
# terraform/asis/edge — 모듈 provider 계약
#
# 이 모듈은 aws provider 를 두 개 요구한다.
#
#   aws            기본 · ap-northeast-2 (서울)
#                  Route 53 퍼블릭 호스팅 영역 · alias 레코드 · CloudFront 배포
#   aws.us_east_1  us-east-1
#                  CLOUDFRONT scope WAFv2 Web ACL · CloudFront 뷰어 ACM 인증서
#
# us-east-1 이 필요한 이유는 리전 선택이 아니라 AWS API 제약이다.
#   - scope = "CLOUDFRONT" 인 aws_wafv2_web_acl 은 us-east-1 에만 만들 수 있다
#   - CloudFront 뷰어 인증서(ACM)는 us-east-1 에만 둘 수 있다
#
# AS-IS 사실은 「리전 ap-northeast-2 (서울) 단일」이며
# (context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2)
# us-east-1 은 서비스 리전이 아니라 엣지 통제의 저장 위치다.
# 이 구분이 무너지면 「국내 리전 다중 AZ 구성」
# (context/raw/D02-진단대상-아키텍처-정의.md#3.1) 진술과 충돌하는 것처럼 읽힌다.
#
# 호출 측(공유 terraform/asis/main.tf · 사람이 관리한다)이 넣어야 하는 provider 정의와
# providers 매핑의 실제 HCL 은 terraform/asis/edge/README.md §1 에 있다.
#
# 여기에 그 HCL 을 주석으로 옮겨 적지 않는다.
# scripts/check_asis_contract.py 는 주석을 걷어내지 않고 terraform/asis 전체에서
# provider "aws" 블록과 skip_* 플래그를 정규식으로 찾는다. 예시를 주석으로 두면
# 그 주석이 mock provider 요건을 대신 충족시켜, 정작 공유 루트에 플래그가 빠져도
# 검사가 초록으로 통과한다. 가드레일이 죽는다.
#
# configuration_aliases 는 provider 요구를 코드로 선언한다. 매핑이 빠지면 terraform 이
# 호출 시점에 실패하므로, 이 계약은 README 문장이 아니라 검증되는 계약이다.
###############################################################################

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source                = "hashicorp/aws"
      version               = ">= 5.0"
      configuration_aliases = [aws.us_east_1]
    }
  }
}
