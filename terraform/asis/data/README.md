# terraform/asis/data — 데이터 계층 AS-IS 재현 명세

**브랜치** `feat/asis-data` · **범위** RDS PostgreSQL · ElastiCache · S3 3버킷

---

## 0. 이 코드의 지위

`terraform/asis/README.md` 의 전제를 그대로 승계한다.

- J사에는 IaC 가 없다. 이 코드는 도면·시나리오 문서를 근거로 **역으로 작성한 재현 명세**다.
- **apply 하지 않는다.** AWS 자격증명을 요구하지 않는다. CD 워크플로를 만들지 않는다.
- **AS-IS 결함을 고치지 않는다.** 결함은 그대로 두고 근거 주석을 결함 옆에 남긴다.
- 충족/미충족·잔여위험을 이 문서에서 판정하지 않는다 (`AGENTS.md` §0).

`docs/current/**` 는 현재 승인 문서 0건이다. 이 모듈은 `context/raw/**` 원문의
`SCENARIO_CONFIRMED` 서술만 근거로 쓰고, `context/proposals/**` 는 비권위 초안으로만
참조했다 (`AGENTS.md` §1).

---

## 1. 근거 원문

| 앵커 | 이 모듈이 가져온 것 |
|---|---|
| `context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2` | RDS Multi-AZ · 백업 7일 · PITR · 저장 암호화(AWS 관리형 키) · CMK 미사용 · ALB 액세스 로그 90일 · CloudTrail 관리 이벤트만 |
| `context/raw/SCENARIO_FACTS-가상고객사J사.md#10` | ElastiCache 성명·연락처 TTL 24h · S3 이력서 원본 버저닝 활성 · 퍼블릭 차단 · SSE-S3 · 수명주기 규칙 미처리 |
| `context/raw/SCENARIO_FACTS-가상고객사J사.md#5.2` | Secrets Manager 미사용 — 자격증명 실제 보관 위치는 GitHub |
| `context/raw/SCENARIO_FACTS-가상고객사J사.md#9.4` | 관리자 접근 경로 C — BI 가 읽기 복제본을 가명처리 없이 조회 |
| `context/raw/인프라컨텍스트-외부협업용.md#2.2` | Private Data 서브넷 2-AZ · Primary/Standby · 읽기 복제본 · ElastiCache 배치 |
| `context/raw/D02-진단대상-아키텍처-정의.md#3.1` | AZ-2a Primary / AZ-2c Standby 배치 |
| `context/raw/Jcareer-흐름과-기술취약점.md#2.5` | 파기 계층 — ElastiCache · S3 버전이 파기 미도달 저장소 |
| `context/raw/Jcareer-흐름과-기술취약점.md#4.1` | ALB 로그 90일 |

2-AZ 전개가 권위인 근거는 `context/findings/MIGRATION_AUDIT.md` §5 (MIG-C03 RESOLVED) 다.
현행 PNG 는 단일-AZ 참고이고 2-AZ 사양은 위 두 텍스트 원문이다.

---

## 2. 파일 구성

```
versions.tf        required_version · required_providers (provider 블록 없음)
variables.tf       입력 변수 · CloudTrail 정책 입력 contract
locals.tf          공통 태그 · 버킷 이름 · CloudTrail 키 경로
rds.tf             서브넷 그룹 · Primary(Multi-AZ) · 읽기 복제본
elasticache.tf     서브넷 그룹 · 추천 결과 캐시 복제 그룹
s3_resume.tf       이력서 원본 버킷 · 버저닝 · SSE-S3 · 퍼블릭 차단
s3_alb_logs.tf     ALB 로그 버킷 · 90일 수명주기 · SSE-S3 · 버킷 정책
s3_cloudtrail.tf   CloudTrail 로그 버킷 · SSE-S3 · 버킷 정책
outputs.tf         타 모듈 참조점 · CloudTrail 정책 contract 노출
```

**provider 블록은 이 모듈에 없다.** `provider "aws"` (mock 자격증명 · `skip_*` 3종) 는
공유 루트 `terraform/asis/main.tf` 소유다. 자식 모듈에 provider 를 선언하면 루트와
이중 선언이 된다.

---

## 3. 리소스 (16건)

| 리소스 | 상태 | 근거 |
|---|---|---|
| `aws_db_subnet_group.data` | Data 서브넷 2-AZ | `인프라컨텍스트#2.2` |
| `aws_db_instance.primary` | Multi-AZ · 백업 7일 · 저장 암호화(관리형 키) | `SCENARIO_FACTS#9.2` |
| `aws_db_instance.replica` | 동일 리전 읽기 복제본 | `인프라컨텍스트#2.2` |
| `aws_elasticache_subnet_group.data` | Data 서브넷 2-AZ | `인프라컨텍스트#2.2` |
| `aws_elasticache_replication_group.recommendation` | 전송·저장 암호화 **false** | `SCENARIO_FACTS#10` |
| `aws_s3_bucket.resume` + 버저닝 + SSE-S3 + 퍼블릭 차단 | 수명주기 규칙 **없음** | `SCENARIO_FACTS#10` |
| `aws_s3_bucket.alb_logs` + 수명주기 90일 + SSE-S3 + 정책 | 보존 90일 | `SCENARIO_FACTS#9.2` |
| `aws_s3_bucket.cloudtrail` + SSE-S3 + 정책 | 목적지 버킷만 | `SCENARIO_FACTS#9.2` |

`data "aws_iam_policy_document"` 2건은 계약상 유일하게 허용된 data source 다
(`terraform/asis/README.md`). 그 외 data source 는 쓰지 않았다.

---

## 4. 이 모듈이 재현한 GAP

주석은 전부 **결함이 있는 속성 바로 위**에 두었다. `.md` 에만 적으면
`scripts/check_expected_findings.py` 가 인정하지 않는다.

| GAP ID | 재현 지점 | 파일 |
|---|---|---|
| `GAP-RDS-01` | `backup_retention_period = 7` | `rds.tf` |
| `GAP-CACHE-01` | `transit_encryption_enabled = false` · `at_rest_encryption_enabled = false` | `elasticache.tf` |
| `GAP-S3-01` | 이력서 버킷 버저닝 Enabled + 수명주기 규칙 미선언 | `s3_resume.tf` |
| `GAP-KMS-01` | `kms_key_id` 미지정 · SSE-S3(AES256) 3버킷 | `rds.tf` · `s3_*.tf` |
| `GAP-SEC-01` | `password = var.db_master_password` · `manage_master_user_password` 미사용 | `rds.tf` |

**이 값들을 「보안 모범사례」로 바꾸면 진단 대상이 사라진다.** 바꾸지 말 것.

### 의도적 미선언

| 미선언 | 이유 |
|---|---|
| `aws_kms_key` | `GAP-KMS-01` · `terraform/asis/ABSENCE_MANIFEST.md` |
| `aws_secretsmanager_secret` | `GAP-SEC-01` · `terraform/asis/ABSENCE_MANIFEST.md` |
| `aws_s3_bucket_lifecycle_configuration.resume` | `GAP-S3-01` 의 재현 지점 그 자체 |
| ALB 로그·CloudTrail 버킷의 퍼블릭 차단 / 버저닝 / 수명주기 | 원문에 그 버킷 기준 서술이 없다 (아래 §5) |

---

## 5. 원문에 없는 통제를 채우지 않았다

원문이 퍼블릭 차단과 버저닝을 명시한 대상은 **이력서 원본 버킷 하나**다
(`context/raw/SCENARIO_FACTS-가상고객사J사.md#10`). 로그 버킷 2개에는 서술이 없다.
`context/raw/인프라컨텍스트-외부협업용.md#2.2` 의 「S3(버저닝)」는 계정 공통 서비스
나열이라 어느 버킷까지인지 확정되지 않는다.

없는 통제를 임의로 채우면 AS-IS 가 아니라 우리가 만든 상태가 된다. 그래서 채우지 않았고
`.tf` 에 `[OBSERVATION]` 주석으로 남겼다. 스캐너가 이 지점을 잡으면 명세 밖 발견으로
사람에게 올라간다 (`terraform/asis/README.md` 「왜 자르지 않는가」). **판정은 하지 않는다.**

같은 이유로 `EXPECTED_FINDINGS` 에 ID 가 없는 관찰(장애조치 시험 이력 없음, 경로 C 의
가명처리 없는 복제본 조회, 캐시 TTL 24h 와 파기 절차 부재)은 GAP ID 를 새로 만들지 않고
`[OBSERVATION]` 으로만 표기했다.

---

## 6. 모듈 간 계약

### 6.1 이 모듈이 받는 것 (기본값 없음 — 반드시 주입)

| 변수 | 출처 |
|---|---|
| `data_subnet_ids` | `network` 모듈 — Private Data 10.0.20.0/24 · 10.0.21.0/24 |
| `db_security_group_ids` | `network` 모듈 |
| `cache_security_group_ids` | `network` 모듈 |

나머지 변수는 상수 기본값이 있다. AZ·계정 ID·리전은 data source 금지 계약에 따라
전부 variable 상수로 받는다.

### 6.2 이 모듈이 주는 것

| 출력 | 받는 쪽 |
|---|---|
| `alb_logs_bucket_id` · `alb_logs_prefix` | `compute` — `aws_lb.access_logs.bucket` · `.prefix` |
| `cloudtrail_bucket_id` | `observability` — `aws_cloudtrail.s3_bucket_name` |
| `db_primary_endpoint` · `cache_primary_endpoint_address` | `compute` — ECS 태스크 환경변수 |
| `resume_bucket_arn` | `security` — api 태스크 IAM 정책 대상 |
| `db_replica_endpoint` | 경로 C(BI) 문서화용 |

### 6.3 CloudTrail 정책 입력 contract

`aws_cloudtrail` 리소스와 selector 미선언(= `GAP-TRAIL-01`)은 `observability`
모듈(TASK-105) 소유다. 이 모듈은 목적지 버킷과 그 정책만 소유한다.
버킷 정책의 `aws:SourceArn` 조건이 실제 trail 을 가리키려면 아래가 일치해야 한다.

| 이 모듈 변수 | observability 쪽 값 |
|---|---|
| `cloudtrail_name` | `aws_cloudtrail.<x>.name` |
| `cloudtrail_s3_key_prefix` | `aws_cloudtrail.<x>.s3_key_prefix` |
| `cloudtrail_source_account_ids` | trail 소유 계정 (단일 계정이면 `[var.account_id]`) |

일치 여부를 눈으로 대조할 수 있게 조립 결과를 `cloudtrail_policy_contract` 출력으로
노출한다. ALB 쪽도 같은 구조다 — `alb_log_prefix` 가 어긋나면 버킷 정책과 90일
수명주기 규칙이 **둘 다** 적용되지 않는다.

---

## 7. 공유 루트에 필요한 것 — 사람이 반영한다

`terraform/asis/main.tf` 와 `terraform/asis/variables.tf` 는 공유 파일이다.
에이전트가 고치지 않는다 (`BOOTSTRAP_PROMPT.md` Phase 1). 아래는 **요청**이다.

```hcl
# terraform/asis/main.tf
provider "aws" {
  region                      = var.region
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
  access_key                  = "mock"
  secret_key                  = "mock"
}

module "data" {
  source = "./data"

  data_subnet_ids          = module.network.data_subnet_ids
  db_security_group_ids    = [module.network.rds_security_group_id]
  cache_security_group_ids = [module.network.cache_security_group_id]

  account_id  = var.account_id
  region      = var.region
  common_tags = var.common_tags
}
```

**현재 `terraform/asis` 루트에 `.tf` 가 하나도 없다.** 그래서 루트가 만들어지기 전에는
아래 두 가지가 통과하지 못한다. 이 모듈의 결함이 아니라 선행 조건이다.

- `python scripts/check_asis_contract.py . terraform/asis`
  → `provider "aws" 블록을 찾지 못했다`. 루트 `main.tf` 가 생기면 해소된다.
- CI 의 `terraform -chdir=terraform/asis init/validate/plan`
  → 루트 구성이 없으면 모듈이 호출되지 않는다.

---

## 8. 권위 상충 — 직접 해소하지 않았다

`AGENTS.md` §1 에 따라 발견만 기록한다. 판단은 사람이 한다.

### 8.1 GAP-S3-01 의 companion_absent 가 ALB 로그 90일과 부딪친다

| 쪽 | 원문 |
|---|---|
| A | `context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2` — 「ALB · Multi-AZ · TLS 1.2+ 종단 · **액세스 로그 S3 적재, 보존 90일**」 `SCENARIO_CONFIRMED` |
| B | `context/proposals/docs-current/EXPECTED_FINDINGS.yaml` — `GAP-S3-01.plan_assertion.companion_absent: aws_s3_bucket_lifecycle_configuration` |

`scripts/check_expected_findings.py` 의 `companion_absent` 는 **layer 전체의 타입 존재
여부**로 판정한다 (`comp in types_present`). 버킷 단위가 아니다. 따라서 ALB 로그 버킷에
90일 규칙을 두면 이력서 버킷의 결함이 그대로여도 `GAP-S3-01` 이 FAIL 한다.

A 는 `SCENARIO_CONFIRMED` 원문이고 B 는 승인 전 초안이므로(`AGENTS.md` §1 의 4번 계층)
A 를 코드에 반영하고 B 는 건드리지 않았다. **초안 수정은 사람 소관이다.**
해소 방향 후보는 두 가지로 보인다 — 판정하지 않고 적어만 둔다.

1. `companion_absent` 를 버킷 단위 조건으로 바꾼다 (이력서 버킷에 한정).
2. `GAP-S3-01` 의 재현 근거를 「수명주기 미선언」 대신
   「`noncurrent_version_expiration` 부재」로 좁힌다.

### 8.2 at_rest_encryption_enabled 는 provider 6.x 에서 string 이다

`GAP-CACHE-01` 은 `attribute_equals` 로 `at_rest_encryption_enabled: false` 를 본다.
검사기는 `str(plan값) == str(spec값)` 으로 비교한다.

| provider | plan 표현 | `str()` 비교 |
|---|---|---|
| aws 5.x | bool `false` | `"False" == "False"` → 일치 |
| aws 6.x | string `"false"` | `"false" != "False"` → **불일치** |

`terraform providers schema -json` 으로 확인했다 (통합 루트 고정 aws v6.59.0:
`at_rest_encryption_enabled -> string`, `transit_encryption_enabled -> bool`).
HCL 쪽은 두 major 모두 `false` 리터럴로 동작하므로 코드는 바꾸지 않았다.
초안 명세를 승격할 때 값을 `"false"` 로 적거나 검사기 비교를 정규화해야 한다.
`terraform/asis` 루트가 provider 버전을 어디에 고정하느냐에 따라 갈린다.

### 8.3 참고 — 초안 명세의 scanner_assertion.rule_id 는 비어 있다

`GAP-RDS-01` · `GAP-S3-01` · `GAP-CACHE-01` 은 `SCANNER` 타입이라
`rule_id` 가 비면 검사기가 fail-closed 한다. 채우는 것은 실제 tfsec/checkov 출력을
본 뒤의 Phase 1 과제이며 (`context/proposals/docs-current/EXPECTED_FINDINGS.yaml`
머리말), 명세 파일은 사람 소유다. 이 모듈에서는 채우지 않았다.

---

## 9. 검증

이 모듈 단독 기준.

```bash
terraform -chdir=terraform/asis/data fmt -check -recursive
terraform -chdir=terraform/asis/data init -backend=false
terraform -chdir=terraform/asis/data validate
```

`terraform/asis` 루트가 생긴 뒤에는 `terraform/asis/README.md` 의 전체 절차를 쓴다.

**검증 결과 (통합 루트 고정 aws provider v6.59.0)**

| 검사 | 결과 |
|---|---|
| `fmt -check -recursive` | 통과 (재작성 0건) |
| `init -backend=false` · `validate` | Success |
| 무자격증명 `plan` (저장소 밖 임시 루트) | 16 리소스 · 오류 0 |
| data source | `aws_iam_policy_document` 2건뿐 |
| plan 확인값 | `multi_az=true` · `backup_retention_period=7` · `storage_encrypted=true` · `kms_key_id=null` · `transit_encryption_enabled=false` · `at_rest_encryption_enabled=false` · 이력서 버킷 `versioning=Enabled` |

---

## 10. 이 모듈에서 하지 않는 것

- `apply` · CD 워크플로 생성
- `docs/current/**` · `context/raw/**` · `context/MANIFEST.yaml` · `context/proposals/**` ·
  `.github/**` · `terraform/asis` 루트 공유 파일 수정
- `aws_kms_key` · `aws_secretsmanager_secret` 추가
- 자기 모듈 밖 `.tf` 수정
- 충족/미충족 · 잔여위험 판정
