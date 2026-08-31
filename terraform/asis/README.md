# terraform/asis — AS-IS 재현 명세

## 처음 보는 분을 위한 요약

이 폴더는 기존 기획 문서와 도면을 바탕으로 J-Career의 AWS 구성을 다시 적은 기준
설계용 Terraform이다. 현재 구성과 개선 필요 지점을 같은 기준으로 검토할 때 사용한다.

- 업무망 PC는 180대다. Windows 100대와 macOS 80대다.
- Terraform은 여섯 부분으로 나뉘며, 기록된 모의 계획에는 생성 예정 항목이 110개다.
- 이 기준선은 AWS에 적용하지 않았으며 현재 생성 리소스는 0개다.
- 기준선에 애플리케이션 이미지와 실행 환경은 포함되어 있지 않다.
- MLOps는 별도 default-off Terraform 루트이며 2026-08-31 bootstrap 13개 적용만 확인됐다. runtime의 14번째 Lambda는 미배포·미실행이며 기준 110개와 합산하지 않는다.
- Slack은 AWS 밖의 외부 업무 SaaS·자산대장 경계다. 기본 비활성 webhook 어댑터 소스는 있으나 실제 workspace 운영·전송은 확인되지 않았다.
- TRACE·JC-RECEIPT는 실행 인프라나 구축 대상이 아니다. 관련 기본 비활성 로컬 source는 보조 설명으로만 다루며 Terraform 리소스와 AWS 실행은 없다.

자세한 설명은 아래의 [웹 명세](index.html)부터 읽으면 된다. 첫 장에 핵심 숫자와 용어
풀이가 있다.

## 이 코드의 지위 — 반드시 먼저 읽는다

**이 디렉터리의 Terraform 코드는 J사가 보유한 원본 IaC가 아니다.**

기존 자료에 따르면 J사의 인프라는 콘솔에서 수동으로 구성됐고 IaC는 없다
(`context/raw/SCENARIO_FACTS-가상고객사J사.md#9.5`). 이 코드는 컨설팅팀이 도면과
시나리오를 근거로 다시 작성한 명세다. 따라서 실제 AWS 상태와 같다고 단정할 수 없다.

이처럼 원본 IaC가 없어 다시 작성해야 했다는 점은 `GAP-IAC-01`의 근거다. 실제 IaC가
있었다면 기존 코드, 변경 이력, 검토 기록과 실제 구성 차이도 함께 확인할 수 있었을 것이다.

**Terraform 적용은 하지 않는다. AWS 로그인 정보도 요구하지 않는다. 자동 배포 절차도 만들지 않는다.**

## 현재 검토 산출물

- [웹 명세](index.html)
- [PDF 명세](JCAREER_ASIS_SYSTEM_SPEC.pdf)
- [도면 설명](architecture.html)
- [업무망·GitHub CI·AWS·MLOps 전체 지도 원본](JCAREER_FULL_INFRA.drawio)
- [전체 지도 해설](JCAREER_FULL_INFRA.md)
- [웹용 애니메이션 전체 지도](../../assets/JCAREER_FULL_INFRA_ANIMATED.svg)
- [기업 목표·USD 50 핵심 평가 슬라이스](../../assets/JCAREER_PRODUCTION_ASSESSMENT_MAP.svg)
- [핵심 평가 슬라이스 해설](../../assets/JCAREER_PRODUCTION_ASSESSMENT_MAP.md)
- [쉽게 보는 draw.io 원본](JCAREER_ASIS_FLOW.drawio)
- [쉽게 보는 PNG 도면](JCAREER_ASIS_FLOW.drawio.png)
- [보조 상세 draw.io 원본](JCAREER_ASIS_2AZ.drawio)
- [자동검사 결과](validation-report.json)

`JCAREER_FULL_INFRA.drawio`는 업무망·Slack, GitHub 검사·Pages 배포, AWS 기준 설계,
LLM Gateway·Bedrock·OpenDART와 별도 MLOps를 한 장에 합친 편집 원본이다. CI에서 AWS로
이어지는 자동 배포선은 없으며 실제 구현처럼 그리지 않는다.

별도 핵심 평가 슬라이스 지도는 전체 기업 목표를 대체하지 않는다. 고정비가 큰 목표 구조와
USD 50 한도에서 실제 평가·시연에 사용할 서버리스 실행면, 사람이 승인한 snapshot만 읽는
Evidence Desk를 구분한다. AWS 적용 전에는 `DEPLOYMENT EVIDENCE PENDING`으로 표시하며,
GitHub Pages 배포를 AWS 서비스 배포 증거로 사용하지 않는다.

`JCAREER_ASIS_2AZ.drawio`는 원본 작업 트리에서 관리한 별도 기술 기록이다. 공개 기준 도면의
수량과 검증 결과에는 합치지 않는다. 공개 화면은 60개 셀·14개 연결의
`JCAREER_ASIS_FLOW.drawio`와 같은 이름의 PNG를 기준으로 읽는다. `JCAREER_ASIS_2AZ.md`는
초기 2-AZ 구판(legacy) 설명이다.

공개 도면의 MLOps 연결은 기준 110개 Terraform과 분리된 `terraform/serverless-mlops`의
왼쪽→오른쪽 검증 흐름을 설명한다. bootstrap 13개(S3 보호 설정 7, ECR 2, IAM 2,
DynamoDB 1, CloudWatch Logs 1)는 적용됐지만 Lambda runtime·실행·결과 생성은 없다. Slack 상자는 실제 workspace 운영과 AWS 통합을 나타내는
연결선을 갖지 않는다. 기존 API의 Slack·Notion·SMTP 어댑터와 TRACE는 소스 구현 메모로만
표시하며, 실계정·실전송·AWS 배포를 암시하지 않는다.

## 서비스 기획과의 경계

이 디렉터리의 Terraform은 기존 채용 매칭 서비스의 2-AZ AS-IS만 재현한다. TRACE·JC-RECEIPT와
외부 업무도구 어댑터는 `src/runtime`의 기본 비활성 애플리케이션 소스로 구현하되, 이 Terraform에
Lambda, EventBridge, Step Functions, DynamoDB 같은 새 리소스를 추가하지 않는다. 실제 외부 연결과
운영 활성화에는 별도 사람 승인과 검증 단계가 필요하다.

---

## 결함 보존 원칙 — 이 디렉토리의 가장 중요한 규칙

**AS-IS 코드의 결함을 고치지 않는다.**

에이전트는 Terraform 을 쓸 때 안전한 기본값으로 수렴하는 성향이 있다.
CMK 를 붙이고, Config 를 켜고, 로그 보존을 늘리고, Secrets Manager 를 도입한다.
**그렇게 되면 AS-IS 가 사라지고 진단 대상이 없어진다.**

사용자 확정 AS-IS 사실은 그대로 두고 근거 주석을 남긴다. 현재
`context/proposals/docs-current/EXPECTED_FINDINGS.yaml` 은 승인 전 초안이므로 현행 기준으로
승격하지 않으며, 스캐너 출력과 명세 결함을 비교하는 입력으로만 사용한다.
**없는 것에도 주석을 남긴다.** 주석이 없으면 CI 가 「의도적 미선언」과 「그냥 빠뜨림」을
구분하지 못해 실패한다.

```hcl
# GAP-CFG-01 [ABSENCE] AWS Config 미활성
# 근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2
# 이 리소스를 선언하지 않는 것이 AS-IS 다. 추가하지 말 것.
# aws_config_configuration_recorder — 의도적 미선언
```

---

## 필수 태그

```hcl
tags = {
  jk_layer  = "asis-model"
  jk_source = "context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2"
  jk_apply  = "forbidden"
}
```

## 작성 규칙 — 무자격증명 plan (필수)

CI 는 AWS 자격증명 없이 `plan` 을 돌린다. 그래서 두 가지가 강제된다.

### provider 는 이 블록을 그대로 쓴다

```hcl
provider "aws" {
  region                      = var.region        # 기본값 "ap-northeast-2"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
  access_key                  = "mock"
  secret_key                  = "mock"
}
```

### data source 를 쓰지 않는다

plan 시점에 실제 API 를 호출하므로 자격증명 없이 깨진다.

```
금지   data "aws_availability_zones"   data "aws_ami"
       data "aws_caller_identity"      data "aws_region"
       data "aws_vpc"                  data "aws_subnets"   ...
허용   data "aws_iam_policy_document"   ← 로컬 계산이라 API 호출이 없다

대체   variable + 상수 기본값
       variable "az_names"   { default = ["ap-northeast-2a", "ap-northeast-2c"] }
       variable "account_id" { default = "redacted" }   # 공개본 마스킹
       variable "ami_id"     { default = "ami-0000000000000000" }  # 가상
```

`scripts/check_asis_contract.py` 가 이것을 강제한다. **문서 규칙만으로는 안 막힌다** —
리소스가 100개를 넘으면 관행대로 `data "aws_availability_zones"` 를 쓰게 된다.

---

## 모듈 구조 — 에이전트 1개 = 모듈 1개

여러 에이전트가 병렬로 작업한다. 같은 `.tf` 를 동시에 건드리면 머지 충돌이 난다.
도메인으로 갈라서 브랜치 하나가 모듈 하나만 만진다.

```
terraform/asis/
  main.tf              provider · variable · locals · 모듈 호출
  variables.tf         az_names · account_id · ami_id · 태그 기본값
  network/             VPC · 서브넷 6 · IGW · NAT 2 · EIP · RT · SG
  edge/                Route53 · CloudFront · WAF (관리형 규칙셋만)
  compute/             ALB · target group · listener · ECS cluster/task/service · ECR
  data/                RDS Multi-AZ + read replica · ElastiCache · S3 3버킷
  observability/       CloudTrail · CloudWatch Log Group · VPC Flow Logs · GuardDuty
  security/            SSM 엔드포인트 · IAM role/policy
  ABSENCE_MANIFEST.md  미선언 리소스 대장 — 공유 파일. 사람이 관리한다
```

**2-AZ 전체 전개다** (`CONFLICT_MATRIX` C-01 RESOLVED). 축약하지 않는다.
도면에 있는 리소스를 전부 만드는 기준 설계다. 기록된 모의 계획은 생성 예정 110개다.

### 왜 자르지 않는가

`check_expected_findings.py` 는 명세한 17건만 검증하지만,
tfsec/checkov 는 **전체 인프라**를 훑어서 명세에 없는 결함을 찾아낸다.
그 결과가 `context/findings/unexpected_asis.json` 에 쌓이고 사람이 판정한다.

**그게 컨설팅 발견의 원천이다.** ALB·ECS·CloudFront·NAT 를 빼면 거기서 나올 발견을 잃는다.
ISO/IEC 42001 Annex A 매핑도 시스템 전체가 대상이다.

## 도면 대비 리소스 목록

2-AZ 소스 이미지는 현재 보유하지 않는다. 사용자 확정에 따라
`context/raw/인프라컨텍스트-외부협업용.md#2.2` 와
`context/raw/D02-진단대상-아키텍처-정의.md#3.1` 의 텍스트 사양을 함께 사용한다.
초기에 제공된 PNG는 단일-AZ 축약본이므로 2-AZ 리소스를 줄이는 근거로 쓰지 않는다.

현행 `JCAREER_ASIS_FLOW.drawio`에는 `web / Nginx` 아래 **React Renderer**를 표시했다.
이는 AI 응답이 프런트엔드 DOM으로 넘어가는 신뢰경계 TB⑥과 `R-04` 판정 지점을 드러내는
논리 노드다. 별도 Terraform 리소스나 ECS 서비스가 추가됐다는 뜻은 아니다.

## 스캐너 설치 — `curl | bash` 금지

CI 는 원격 스크립트를 파이프로 실행하지 않는다 (V2-P0-08).
tfsec/checkov 는 **검토한 릴리스 버전 + SHA256 검증** 또는 digest 고정 컨테이너로 설치한다.
Phase 1 에서 버전과 체크섬을 확정해 `REQUIRED_BEFORE_MERGE` 에 등재한다.

## 검증

```bash
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
terraform plan -out=tfplan -lock=false
terraform show -json tfplan > ../../plan_asis.json
python3 ../../scripts/check_expected_findings.py \
  --layer asis --plan ../../plan_asis.json \
  --spec ../../context/proposals/docs-current/EXPECTED_FINDINGS.yaml \
  --tfdir . --out ../../context/findings/absence_asis.json
```
