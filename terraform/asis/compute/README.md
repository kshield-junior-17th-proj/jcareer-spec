# AS-IS compute 모듈

J-Career 서비스망의 ALB, ECS Fargate, ECR 구성을 역으로 작성한 재현 명세다. AWS에 적용하지 않으며, 구성 기준은 `context/raw/인프라컨텍스트-외부협업용.md#2.2`와 `context/raw/D02-진단대상-아키텍처-정의.md#3.1`이다.

## 선언 범위

- 서로 다른 두 public subnet의 internet-facing ALB 1개
- `ELBSecurityPolicy-TLS13-1-2-2021-06`을 사용하는 HTTPS 443 listener 1개
- `web:3000`, `api:8000`, `agent:8100`, `llm-gateway:8200` target group 4개
- `/api/*`, `/agent/*`, `/llm/*`, `/*` path routing
- ECS Fargate cluster 1개와 네 task definition·service
- 각 service의 `desired_count = 2`, Application Auto Scaling `min_capacity = 2`, Availability Zone spread
- 서비스별 ECR repository 4개

`matcher`는 별도 배포 단위가 아니다. 결정론적 점수 계산은 `agent` 내부 기능이므로 다섯 번째 task definition, service, target group, ECR repository를 만들지 않는다.

## 입력 계약

실제 환경 식별자를 조회하는 data source는 사용하지 않는다. 다음 값은 루트 구성에서 변수로 전달한다.

| 구분 | 변수 |
|---|---|
| 계정·리전 | `account_id`, `region` |
| 이미지 | `container_images` |
| 인증서 | `certificate_arn` |
| IAM | `task_execution_role_arn`, `task_role_arns` |
| 네트워크 | `vpc_id`, `public_subnet_ids`, `application_subnet_ids` |
| SG | `alb_security_group_ids`, `service_security_group_ids` |
| 로그 | `cloudwatch_log_group_names` |

기본값은 자격증명 없는 정적 검증을 위한 합성 식별자다. `public_subnet_ids`와 `application_subnet_ids`에는 각각 `ap-northeast-2a`, `ap-northeast-2c`의 subnet을 하나씩 전달한다.

## AS-IS 결함 보존

- `GAP-SEC-01`: Secrets Manager를 선언하지 않고 합성 `llm_api_key`를 container 환경변수로 모델링한다. 근거: `context/raw/인프라컨텍스트-외부협업용.md#2.2`
- `GAP-KMS-01`: 고객관리형 KMS key를 선언하지 않고 ECR의 AES256 암호화를 사용한다. 근거: `context/raw/인프라컨텍스트-외부협업용.md#2.2`
- `GAP-SBOM-01`: ECR scan-on-push를 켜지 않는다. 근거: `context/raw/SCENARIO_FACTS-가상고객사J사.md#9.5`

위 항목을 이 모듈에서 보완하지 않는다. 판정과 보완대책 선택은 사람 소유다.

## 검증

```bash
terraform -chdir=terraform/asis/compute fmt -check -recursive
terraform -chdir=terraform/asis/compute init -backend=false
terraform -chdir=terraform/asis/compute validate
python scripts/check_asis_contract.py . terraform/asis/compute
```

`terraform apply`는 금지한다.
