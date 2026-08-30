# terraform/asis/security — SSM 접근 경로와 최소 IAM

## 이 모듈의 지위

`terraform/asis/README.md` 의 「이 코드의 지위」와 「결함 보존 원칙」이 그대로 적용된다.
여기 있는 것은 J사가 보유한 코드가 아니라 컨설팅팀이 도면과 시나리오 문서를 근거로
역으로 작성한 재현 명세다. **apply 하지 않는다.**

이 모듈은 **AS-IS 를 고치지 않는다.** 안전한 기본값으로 수렴하고 싶어지는 자리마다
왜 선언하지 않는지를 근거 앵커와 함께 주석으로 남겼다.

## 만드는 것

| 파일 | 내용 |
|---|---|
| `endpoints.tf` | SSM 계열 VPC Interface Endpoint 3종 — `ssm` · `ssmmessages` · `ec2messages` |
| `iam.tf` | ECS task execution role · ECS task role · VPC Flow Logs 전달 role |
| `absences.tf` | 리소스 없음. 의도적 미선언 대장 |
| `variables.tf` · `outputs.tf` · `versions.tf` | 입출력 계약 |

역할은 세 개뿐이다. 도면에 이미 있는 서비스가 동작하기 위해 반드시 있어야 하는 것만 만들고,
그 밖의 역할은 만들지 않는다.

## 만들지 않는 것 — bastion · SSH

운영 접근은 SSM Session Manager 이고 SSH 22 는 미개방이며 MFA 가 적용돼 있다.
`context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2` · `context/raw/SCENARIO_FACTS-가상고객사J사.md#9.4`

그래서 bastion 호스트 · 키페어 · 22번 인바운드 규칙을 만들지 않는다.
**이것은 GAP 이 아니라 AS-IS 에 이미 존재하는 통제다.** 관리자 접근 경로 A~F 여섯 중
통제되는 것이 B 하나라는 서술의 그 B 이며, 없애면 AS-IS 가 바뀐다.

## 의도적 미선언 — GAP 주석 위치

같은 설명을 두 곳에 쓰지 않는다. 아래는 어디에 있는지만 가리킨다.

| GAP ID | 미선언 대상 | 주석 위치 |
|---|---|---|
| `GAP-EGRESS-01` | Network Firewall · Route53 Resolver DNS firewall | `terraform/asis/security/endpoints.tf` 하단 |
| `GAP-SEC-01` | Secrets Manager secret · secret_version | `terraform/asis/security/iam.tf` · execution role 뒤 |
| `GAP-KMS-01` | `aws_kms_key` · alias · key policy | `terraform/asis/security/iam.tf` · task role 의 S3 정책문 안 |
| `GAP-CFG-01` | Config recorder · delivery channel · 서비스 역할 | `terraform/asis/security/iam.tf` 하단 |
| `GAP-WAF-01` | WAF 커스텀 regex 규칙 (소유는 edge 모듈) | `terraform/asis/security/absences.tf` |

주석을 근거가 드러나는 코드 옆에 둔 이유는, 「의도적 미선언」과 「그냥 빠뜨림」의 차이가
**대장에 이름이 있느냐가 아니라 왜 없는지가 코드에서 읽히느냐**이기 때문이다.
예를 들어 `GAP-KMS-01` 은 task role 의 S3 정책문에 `kms:Decrypt` 가 없는 자리에 있다.

`terraform/asis/ABSENCE_MANIFEST.md` 는 공유 파일이고 사람이 관리한다. 이 모듈은 건드리지 않는다.

## 입력 계약 — 루트에서 배선한다

기본값이 없는 변수는 공유 파일 `terraform/asis/main.tf` 가 다른 모듈의 출력으로 배선한다.
이 모듈은 그 배선을 직접 만들지 않고, 다른 모듈의 `.tf` 도 건드리지 않는다.

| 변수 | 기본값 | 공급자 |
|---|---|---|
| `vpc_id` | 없음 | network 모듈 |
| `app_subnet_ids` | 없음 | network 모듈 — Private App 2-AZ |
| `vpc_endpoint_security_group_ids` | 없음 | network 모듈 — SG 는 network 소유 |
| `resume_bucket_name` | `jcareer-asis-resume` | data 모듈 |
| `region` | `ap-northeast-2` | 상수 |
| `name_prefix` | `jcareer-asis` | 상수 |
| `common_tags` | `jk_layer` · `jk_apply` | 상수. `jk_source` 는 리소스별 merge |

출력은 `ssm_interface_endpoint_ids` · `ssm_interface_endpoint_arns` ·
`ecs_task_execution_role_arn` · `ecs_task_execution_role_name` · `ecs_task_role_arn` ·
`ecs_task_role_name` · `vpc_flow_logs_role_arn` 이다.
**판정값은 내보내지 않는다** (AGENTS.md §0 · §4).

## 작성 계약 준수

- `data source` 는 `aws_iam_policy_document` 만 쓴다. 다른 data source 는 없다.
- 리전은 variable 상수 기본값으로 받는다. 이 모듈은 AZ 이름과 계정 ID 를 참조하지 않으므로
  쓰지 않는 변수를 선언해 두지 않았다.
- `provider "aws"` 블록은 이 모듈에 두지 않는다. mock provider 는 공유 파일
  `terraform/asis/main.tf` 소유이며 사람이 관리한다. 자식 모듈이 provider 를 선언하면
  루트와 이중 선언이 되고 모듈 재사용이 깨진다.

## 확정되지 않은 것

**ASSUMED** — 시나리오 원문은 "SSM Session Manager 사용"까지만 확정한다.
그 접근이 interface endpoint 경유인지 NAT 경유인지는 원문에 없다.
이 재현 명세는 `context/raw/D02-진단대상-아키텍처-정의.md#3.1` 의
"개인정보가 AWS 경계를 넘는 지점은 NAT → 외부 LLM API 한 구간뿐" 이라는 문장에 맞춰
관리 트래픽을 VPC 내부 endpoint 로 모델링했다. 확정 사실이 아니며 사람 확인 대상이다.

## 검증

```bash
terraform -chdir=terraform/asis/security fmt -check -recursive
terraform -chdir=terraform/asis/security init -backend=false
terraform -chdir=terraform/asis/security validate
```

`python3 scripts/check_asis_contract.py . terraform/asis` 는 `terraform/asis` 전체에서
`provider "aws"` 블록을 찾는다. 공유 파일 `terraform/asis/main.tf` 가 아직 없으므로
그 검사는 루트 파일이 생기기 전까지 provider 항목에서 실패한다.
**모듈 단독으로는 해소할 수 없다** — 루트 파일은 사람이 관리하는 공유 파일이다.
`data source` 항목은 이 모듈만 놓고 돌려도 통과한다.
