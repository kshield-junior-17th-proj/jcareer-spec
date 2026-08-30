# AS-IS observability module

이 모듈은 이번 사용자 승인 범위의 관측 구성을 재현한다. 적합성이나 잔여위험을
판정하지 않으며, `terraform/asis/observability/` 밖의 리소스를 소유하지 않는다.

구성 근거는 다음 텍스트 사양이다.

- `context/raw/인프라컨텍스트-외부협업용.md#2.2`
- `context/raw/D02-진단대상-아키텍처-정의.md#3.1`

## 재현 범위

| 구성 | 재현값 |
|---|---|
| CloudTrail | 관리 이벤트만 기록하며 데이터 이벤트는 선언하지 않음 |
| access CloudWatch Log Group | `retention_in_days = 365` |
| VPC Flow Log CloudWatch Log Group | `retention_in_days = 30` |
| prompt raw CloudWatch Log Group | `retention_in_days` 미설정 |
| VPC Flow Log | `ALL` 트래픽을 CloudWatch Logs로 전달 |
| GuardDuty | detector 활성화 |
| AWS Config | 의도적 미선언 (`GAP-CFG-01`) |

데이터 이벤트, AWS Config, 추가 보완 통제는 이 모듈에 넣지 않는다. 실제 AWS 조회를
수행하는 data source도 사용하지 않는다.

## 입력

S3 버킷과 IAM 역할, VPC는 다른 모듈 또는 상위 구성에서 관리하며 이 모듈은 ID와
ARN만 입력받는다.

| 변수 | 필수 | 설명 |
|---|---:|---|
| `cloudtrail_s3_bucket_id` | 예 | CloudTrail 대상 S3 버킷 ID(버킷 이름) |
| `flow_log_iam_role_arn` | 예 | VPC Flow Logs의 CloudWatch Logs 전달 역할 ARN |
| `vpc_id` | 예 | Flow Log 대상 VPC ID |
| `region` | 아니요 | 기본값 `ap-northeast-2` |
| `name_prefix` | 아니요 | 기본값 `jcareer-asis` |
| `tags` | 아니요 | 추가 태그; 필수 증적 태그가 우선함 |

호출자가 제공하는 S3 버킷 정책과 IAM 역할 정책은 이 모듈에서 생성하거나 변경하지
않는다.

## 출력

- `cloudtrail_id`, `cloudtrail_arn`
- `cloudwatch_log_group_names`, `cloudwatch_log_group_arns`
- `vpc_flow_log_id`
- `guardduty_detector_id`

## 정적 검증

```text
terraform -chdir=terraform/asis/observability fmt -check -recursive
terraform -chdir=terraform/asis/observability init -backend=false
terraform -chdir=terraform/asis/observability validate
python scripts/check_asis_contract.py . terraform/asis
```

이 AS-IS 명세에는 `apply`를 수행하지 않는다.
