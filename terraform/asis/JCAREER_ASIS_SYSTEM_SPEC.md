# J-Career 기존 구성(AS-IS) 서비스 및 시스템 명세

> 문서 상태: 기준 설계 · 기술 검토 진행
> 기준일: 2026-08-30
> 다루는 대상: 기존 자료를 바탕으로 다시 그린 Terraform 구성과 별도 로컬 예시 코드  
> 문서 목적: 채용 서비스와 AWS 기준 설계, 데이터·보안·운영 검증 범위를 한 문서로 관리
> 이번 범위 아님: TRACE, JC-RECEIPT, Decision Receipt, Recourse Twin 등 제안 단계 서비스

## 0. 처음 읽는 분을 위한 안내

J-Career는 구직자와 기업을 연결하고 서로 맞는 선택지를 빠르게 좁혀 주는 채용 서비스다.
이 문서는 서비스 기능, 데이터, AWS 인프라, 보안과 운영 기준을 한곳에서 확인할 수 있도록
기존 기획 문서와 Terraform 코드를 대조해 정리한 시스템 명세다.

### 0.1 30초 요약

1. 업무망에는 PC 180대가 있다. Windows 100대와 macOS 80대다.
2. AWS는 서울 리전의 두 가용 영역과 6개 Terraform 모듈, 110개 계획 항목을 기준으로 설계했다.
3. 서비스 기능은 웹·API 구현 범위와 AWS 인프라 기준선을 나누어 관리한다.
4. 기준 Terraform의 애플리케이션 이미지와 AWS 실행 결과는 후속 배포 검증 항목이다.
5. MLOps는 기준 110개와 분리한 7단계 모델 검증 경로다. 기본 잠금 0개, 보관함 준비 13개, 한 번 실행 준비 14개 계획으로 나뉜다.
6. Slack은 AWS 리소스가 아닌 외부 업무 SaaS·자산대장 경계다. 두 운영체제 이미지의 바로가기 소스와 macOS 종료 시 best-effort 프로세스 종료만 확인했으며 실제 workspace 운영은 확인하지 못했다.
7. 컨설턴트 대시보드는 J-Career 고객사 AWS에 직접 연결하지 않는다. 외부 미리보기에는 민감한 내용을 지운 복사본만 쓴다.
8. TRACE와 JC-RECEIPT 같은 신규 AI 서비스는 아이디어 단계다. 이번 명세에 구현 내용으로 넣지 않았다.

> 핵심 기준은 **업무망 PC 180대, 서울 리전 2-AZ, Terraform 6개 모듈과 110개 계획 항목**이다.

### 0.2 핵심 숫자

| 숫자 | 무엇을 뜻하나 | 무엇을 뜻하지 않나 |
|---:|---|---|
| 180 | 업무망 PC 전체 수 | AWS 리소스 수가 아님 |
| 100 / 80 | Windows PC 100대 / macOS PC 80대 | 운영체제 버전이나 보안 상태가 확인됐다는 뜻이 아님 |
| 2 | 서울 리전 안에서 나눈 두 가용 영역(AZ) | 두 지역에 실제 배포했다는 뜻이 아님 |
| 6 | Terraform 구성을 나눈 모듈 수 | 실행 중인 서비스 수가 아님 |
| 110 | AWS 비접속 계획에서 생성 예정으로 계산된 항목 수 | AWS 배포 결과와는 별도 관리 |
| 7 | 합성 자료 준비부터 사람 검토 대기까지의 MLOps 단계 수 | 모델이 승인되거나 추천에 반영됐다는 뜻이 아님 |
| 0 / 13 / 14 | 별도 MLOps Terraform의 기본 잠금 / 보관함 준비 / 한 번 실행 준비 계획 수 | 기준 110개와 합산하지 않음 |
| 24 | 별도 AWS 검증 Lab의 HTTPS·Bedrock 포함 생성 계획 수 | 기준 110개와 합산하지 않으며 배포 완료 수가 아님 |
| 0 | 권한 차단 뒤 정리를 마친 현재 AWS 검증 Lab 리소스 수 | 계획이나 과거의 부분 생성까지 없었다는 뜻은 아님 |

### 0.3 지금 확인된 것과 확인되지 않은 것

| 구분 | 현재 확인된 내용 | 아직 확인되지 않은 내용 |
|---|---|---|
| 업무망 PC | 전체 180대, Windows 100대, macOS 80대 | 버전, 보안 프로그램, 인증, 실제 접속 경로 |
| 업무 시스템·Slack | Windows/macOS 이미지 소스의 `app.slack.com` 바로가기와 macOS 종료 시 best-effort Slack 프로세스 종료 | 실제 workspace 사용, 계정·보존 정책, webhook/token, AWS 연동 |
| AWS 설계 | 2-AZ, 6개 모듈, 기록된 계획 항목 110개 | 고객사 AWS 배포 결과와 실행 상태 |
| AWS 검증 Lab | 별도 24개 생성 계획과 Bedrock 직접 합성 호출 통과, 권한 차단 뒤 부분 자원 정리 완료 | 원격 여섯 서비스, HTTPS 인증 경계, Bedrock 전체 애플리케이션 경로 |
| 기준 애플리케이션 | 배치할 자리와 서비스 이름 | 실행 이미지, 실제 기동, 사용자 통합 시험 |
| 서비스 구현 범위 | 합성 데이터용 소스, 공개 릴리스 검사 6단계(정적 검사 3개·단위시험 묶음 3개) | 실제 사용자 데이터 처리와 장기 운영 관찰 |
| MLOps 전용 구성 | 7단계 흐름, 별도 Terraform 단계별 계획 0/13/14, 소스 경계 검사 19건과 합성 파이프라인 시험 22건 | AWS 배포, 이미지 등록, Lambda 실행, 모델 품질·공정성 판단 |
| 컨설턴트 대시보드 | 별도 소스와 제한적인 미리보기 응답 | 사용자별 로그인, 고객사 분리, 운영 감사 기록, 승인된 데이터 반입 |
| 신규 AI 서비스 | 제안 이름과 아이디어 | 구현, 승인, Terraform 반영, 운영 배포 |

### 0.4 낯선 말을 쉽게 풀면

| 문서에서 쓰는 말 | 쉬운 뜻 |
|---|---|
| 기존 구성(AS-IS) | 현재 자료로 다시 그린 기존 설계. 실제 운영 환경과 같다고 보장하지 않음 |
| Terraform | AWS 인프라를 어떤 모양으로 만들지 적는 설정 파일 |
| mock provider / mock plan | AWS에 접속하지 않고 설정 파일만으로 예상 결과를 계산하는 방식 |
| planned resource | Terraform이 실행된다면 만들 예정이라고 계산한 항목 |
| 2-AZ | 같은 AWS 리전 안의 서로 떨어진 두 시설 구역을 쓰는 설계 |
| 기준 구성(baseline) | 이번 명세의 중심이 되는 `terraform/asis` 설계 |
| 별도 변경분 | 기준 구성에 합쳐지지 않은 다른 폴더나 브랜치의 코드 |
| 로컬 합성 런타임 | 실제 고객 데이터 대신 검증용 합성 데이터로 확인하는 실행 코드 |
| 정적 검사 | 서버나 AWS를 실행하지 않고 코드와 파일 구조만 확인하는 검사 |
| 비식별 복사본(redacted snapshot) | 이름, 계정 등 민감한 내용을 지운 검토용 데이터 묶음 |
| 고객사 분리(tenant isolation) | 한 고객사의 데이터가 다른 고객사에 보이지 않도록 나누는 장치 |
| 감사 기록(audit log) | 누가 언제 무엇을 보고 바꿨는지 남기는 기록 |
| 승인 전 리소스 0개(0 resources) | 평가 승인이 나기 전에는 개선안용 AWS 리소스를 하나도 만들지 않는다는 뜻 |
| 안전 차단(fail-closed) | 승인이나 입력이 없거나 잘못되면 아무것도 만들거나 받지 않는 방식 |

### 0.5 이 문서가 할 수 없는 판단

이 문서는 자료와 코드에서 확인한 사실을 정리한다. 사람의 승인을 대신하지 않는다.
적합 또는 부적합, 인증 가능성, 통제 충족 여부도 판정하지 않는다. 저장소의
`docs/current/README.md`를 기준으로 승인 완료 문서는 0건이다. 따라서 기획 문서의 내용은
승인된 운영 기준이 아니라 검토할 계획으로만 기록한다.

### 0.6 문서 관리

| 항목 | 값 |
|---|---|
| 문서 번호 | `JC-ASIS-SPEC-001` |
| 개정 | 3.14 |
| 기준일 | 2026-08-31 |
| 작성 기준 | 기존 기획, AWS에 접속하지 않는 Terraform 계획, 별도 서비스 구현 범위 |
| 승인 상태 | 기준 설계 · 기술 검토 진행. `docs/current` 승인 문서 0건 |
| 배포 상태 | `terraform/asis`는 미적용. 별도 AWS 검증 Lab의 배포·호출 결과는 별도 기록으로 관리 |

| 개정 | 일자 | 변경 내용 |
|---|---|---|
| 1.0 | 2026-08-27 | Terraform 2-AZ·6모듈·110 planned 기준선 명세 |
| 2.1 | 2026-08-27 | Claude Artifact, 업무망 Windows 100대·macOS 80대, 대시보드·ISO 경계 대조 |
| 3.0 | 2026-08-28 | 로컬 P0 런타임, 70/20/10 matcher, 설명 gateway, 논리 DB, Bedrock 관련 변경분 반영 |
| 3.1 | 2026-08-28 | Claude 독립 재검토 반영: 대시보드 preview 상태, data block 계수, edge log, Bedrock 교차 리전, 도면 데이터 흐름 보완 |
| 3.2 | 2026-08-28 | Claude 2차 검토 반영: recruiter overview, preview API, AI payload 14필드, 흐름 원본 단일화, 검사·산출물 위생 보완 |
| 3.3 | 2026-08-28 | Orca 교차 세션 동기화: 양면 추천 cache 순서, API 소스·효과 계약, Evidence Desk 경계, AWS 비접속 회귀 83건 반영 |
| 3.4 | 2026-08-28 | 최종 교차검토 반영: 연속 목록 의미 구조 복구, 업무망 수량 요구 ID, Bedrock 과거 삭제 이력과 AIMS preview 제한적 관찰 상태 분리 |
| 3.5 | 2026-08-28 | 비기술 독자를 위한 30초 요약, 핵심 숫자, 용어 풀이 추가. 상태 문구와 도면 설명을 쉬운 한국어로 개정 |
| 3.6 | 2026-08-28 | 비기술 독자용 흐름도를 전면 간소화. AWS 이름은 한국어 역할 뒤에 표시하고 상세 IP·검증 이력·ISO 메모는 본문으로 이동 |
| 3.7 | 2026-08-28 | 전체 인프라 위에서 서비스별 경로를 골라 보는 도면 추가. 기업용 인재 찾기·구직자 첫 화면과 OpenDART 공개정보 복사본을 반영하고, 합성 데이터 전용 오프라인 학습 실험을 현재 추천 서비스와 분리 |
| 3.8 | 2026-08-28 | MLOps 현재 코드와 승인 전 확장 흐름을 분리해 표시. 전체 보기 1개와 서비스 경로 5개에 번호가 붙은 단계 설명을 추가. 당시 통합 runner 92건을 재검증해 반영 |
| 3.9 | 2026-08-28 | 대외 문서의 첫 화면을 서비스와 기준 설계 중심으로 개편. 내부 감사 표현은 상세 상태표로 옮기고 합성 데이터·배포 검증 경계는 유지 |
| 3.10 | 2026-08-28 | 첫 화면에 MLOps 7단계와 0/13/14 계획을 독립 영역으로 표시. 최신 서버리스 전용 루트의 데이터·보안·장애 경계와 전용 명세 연결을 반영 |
| 3.11 | 2026-08-29 | 서비스별 인프라 경로에 기능·보안·MLOps 상세 명세 바로가기를 추가하고 링크 자동 검사를 보강 |
| 3.12 | 2026-08-30 | AWS 검증 Lab과 AS-IS 모의 기준선을 분리하고, MLOps·대시보드의 최신 검사 수와 쉬운 한국어 상태표를 반영 |
| 3.13 | 2026-08-30 | 공개 문서 정합성 재검토. PDF 소스 결속, 시점별 Lab 관찰, 공개 도면 39셀·8연결, 서비스별 관찰 상태를 분리하고 고정 검사 추가 |
| 3.14 | 2026-08-31 | 공개 AS-IS 도면과 페이지에 기준선과 분리된 MLOps 0/13/14 실행 경계, 외부 Slack 자산대장 경계, 업무망 선언·구현·미확정 상태를 분리해 반영 |

### 0.7 상태를 읽는 법

표와 본문에서는 먼저 쉬운 한국어 상태를 보여 준다. 내부 코드가 필요할 때는 아래 표에서
원래 상태 코드를 찾을 수 있다.

| 화면에 보이는 상태 | 내부 상태 코드 | 의미 |
|---|---|---|
| 기준 설계 반영 | MODELLED | Terraform과 민감한 값을 뺀 AWS 비접속 계획에서 확인함 |
| 사용자 확인 | USER_CONFIRMED | 사용자가 직접 알려 준 내용. AWS 구성의 증거는 아님 |
| 계획만 있음 | PLANNED_UNIMPLEMENTED | 기획에는 있으나 실행 코드나 이미지가 없음 |
| 서비스 구현 범위 | LOCAL_SYNTHETIC_IMPLEMENTED | 합성 데이터용 소스와 자동 검사가 있음. AWS 배포 결과는 별도 관리 |
| 합성 실험·런타임 미연결 | EXPERIMENT_UNWIRED_NOT_APPROVED | 완전 생성형 오프라인 코드가 있음. 이 경로에는 AWS 자원과 추천 서비스 연결이 없음 |
| MLOps 소스·계획 | MLOPS_PLANNED_NOT_DEPLOYED | 별도 Terraform의 0/13/14 계획과 일회성 Lambda 소스가 있음. AWS 배포·호출과 모델 승인은 확인하지 않음 |
| 시나리오 사용 미확인 | SCENARIO_USE_UNVERIFIED | 자산대장 후보나 이미지 소스는 있으나 실제 조직·workspace 사용과 운영 정책은 확인하지 못함 |
| 코드만 검사 | STATIC_CHECKED | 서버를 켜지 않고 소스와 예상 결과만 대조함 |
| 코드 있으나 잠금 | IMPLEMENTED_GUARDED_NOT_ACTIVE | 호출 코드는 있지만 기본 잠금 상태이며 실제 외부 호출은 확인하지 않음 |
| 별도 실험·현재 미배포 | BRANCH_PROTOTYPE_UNDEPLOYED | 기준 구성에 합쳐지지 않은 실험 코드. 현재 관련 리소스는 없지만 과거 이력까지 없다는 뜻은 아님 |
| 저장소상 미리보기 기록 | REPO_REPORTED_PREVIEW_DEPLOYED | 별도 서비스의 소스와 배포 기록이 있음. 현재 AWS 상태를 다시 확인했다는 뜻은 아님 |
| 제한적 미리보기 확인 | PEER_OBSERVED_PREVIEW_AVAILABLE | 화면 껍데기와 일부 응답만 읽기 전용으로 확인함. 운영 준비 완료를 뜻하지 않음 |
| 초안에만 있음 | RAW_DRAFT_ONLY | 원시 설계 문서에만 있고 현재 코드에는 없음 |
| 확인 전 가정 | ASSUMED | AWS 비접속 계획을 계산하려고 임시로 둔 값 |
| 확인 못함 | UNKNOWN | 현재 자료만으로 확정할 수 없음 |
| 이번 범위 아님 | OUT_OF_SCOPE | 이번 작업에서 다루거나 구현하지 않음 |
| 승인 전 차단 | GATED | 사람 승인 같은 선행 조건이 갖춰질 때까지 생성이나 수집을 막음 |

### 0.8 어떤 근거를 먼저 보았나

자료끼리 내용이 다를 때는 아래 순서로 판단했다.

1. 이번 작업에서 사용자가 명시한 범위와 금지 사항
2. `AGENTS.md` 및 `docs/current/README.md`
3. `terraform/asis/**/*.tf`와 110개 planned resource 구조
4. 별도 `asis-runtime-mvp/src/runtime` 소스와 기록된 로컬 검증 결과
5. 별도 `feat/iso-dashboard` 브랜치의 AIMS Desk 소스·빌드·사용설명서
6. 별도 `feat/bedrock-managed-runtime` 브랜치의 관리형 설명 생성 실험 코드
7. `context/findings/PHASE1_ASIS_EVIDENCE.md` 등 조사 결과
8. `context/raw/**`의 기존 기획 자료. 승인 기준이 아니므로 계획 입력으로만 사용

업무망 수량 요구 `REQ-PC-01`의 2026-08-28 현재 대화 사용자 원문은 다음과 같다.

> “여기 있는 인프라인데 업무망 pc 180대가 윈도우 100대, mac 80대인거라고.”

이 명세는 표기만 PC, Windows, macOS로 정규화했다. 이 작업 지시는 산출물에 우선 적용하지만
저장소 승격, 고객사 확인 또는 조직 승인으로 확대하지 않는다.

## 1. 범위 요약

> 이 장에서는 **이번 문서에 넣은 것, 넣지 않은 것, 실제로 확인한 수준**을 구분한다.

### 1.1 포함 범위

- 서울 리전 모델의 2-AZ, 6개 Terraform 모듈
- 업무망 단말 180대의 운영 맥락: Windows 100대, macOS 80대
- AWS 밖의 외부 업무 SaaS·자산대장 경계로 둔 Slack과 VPN+MFA·UTM 선언 상태
- Route 53, CloudFront, AWS WAF, ALB를 통한 공개 진입 경로
- ECS Fargate의 `web`, `api`, `agent`, `llm-gateway` 네 배포 단위
- RDS PostgreSQL, ElastiCache Redis, S3 세 버킷
- CloudWatch Logs, VPC Flow Logs, CloudTrail, GuardDuty
- SSM 계열 Interface VPC Endpoint와 IAM 역할
- 기존 기획의 채용, 지원, 추천, 동의, 파기, 감사 흐름
- 별도 로컬 변경 세트의 P0 합성 런타임과 AI 매칭·설명 계약
- 기업 공개정보를 별도 복사본으로 저장하는 OpenDART 보조 기능과 합성 MLOps 로컬 학습·평가 코드
- 기준 110개와 분리된 MLOps 7단계 서버리스 경로, Terraform 0/13/14 계획과 사람 검토 대기 경계
- 기존 `llm-gateway` 내부 Bedrock Converse 어댑터와 별도 관리형 실험 브랜치의 경계
- 컨설턴트 소유 대시보드의 데이터 수신 경계와 운영 전제

### 1.2 제외 범위

- TRACE, JC-RECEIPT 및 이에 준하는 제안 단계 신규 서비스의 구현 또는 AS-IS 편입
- 기준 Terraform에 신규 Lambda, EventBridge, Step Functions, DynamoDB를 추가하는 작업
- Slack webhook/token, Amazon Q Developer(AWS Chatbot), SNS, EventBridge 등 AWS 연동의 생성 또는 암시
- J-Career client 기준선 컨테이너 이미지 게시, AWS 런타임 배포, 공급자 실호출
- 실제 지원자 데이터, 실제 고객 계정, 실제 자격증명
- AWS 적용, 상태 변경, 실제 서비스 연결
- TO-BE 리소스 생성
- ISO/IEC 42001 적합성, 인증 가능성 또는 통제 충족 여부 판정

### 1.3 실제로 확인한 수준

아래 표의 각 줄은 서로 다른 대상을 설명한다. “설계 파일에서 확인”, “로컬 예시 구현”,
“제한적 미리보기 확인”은 모두 의미가 다르다. 한 줄의 결과를 다른 줄의 운영 상태로
넓혀서 해석하면 안 된다.

| 확인 대상 | 상태 | 현재 알 수 있는 내용 |
|---|---|---|
| 업무망 PC | `USER_CONFIRMED` | `REQ-PC-01`: 총 180대, Windows 100대와 macOS 80대. 관리 방식과 AWS 접속 경로는 확인하지 못함 |
| Slack 업무 시스템 | `SCENARIO_USE_UNVERIFIED` | 외부 업무 SaaS·자산대장 경계다. Windows/macOS 이미지 소스의 `https://app.slack.com/client` 바로가기와 macOS 종료 시 best-effort 프로세스 종료만 확인했으며 실제 workspace 사용·소유·보존 정책은 확인하지 못함 |
| 기준 AWS 설계(Terraform) | `MODELLED` | 여섯 모듈로 구성됨. 기록된 AWS 비접속 계획은 생성 예정 110개, 변경 0개, 삭제 0개임. 별도 로컬 변경분을 넣어 다시 계산하지는 않음 |
| J-Career 고객사 AWS 리소스 | 생성 안 함 | AWS에 접속하지 않는 모의 방식이므로 실제 AWS 상태를 나타내지 않음 |
| 별도 AWS 검증 Lab | 권한 보완 대기 | HTTPS·Bedrock 포함 24개 생성 계획은 통과. 적용은 IAM 역할 생성 권한 부족으로 중단됐고 부분 생성 16개를 정리해 현재 0개. Bedrock 직접 합성 호출은 통과했으나 전체 경로는 미확인 |
| 기준 폴더의 애플리케이션 | `PLANNED_UNIMPLEMENTED` | 실행할 소스와 이미지가 없음 |
| 서비스 구현 코드 | `LOCAL_SYNTHETIC_IMPLEMENTED` | `web`, `api`, `agent`, `llm-gateway`와 PostgreSQL, Redis 소스가 있음. 합성 데이터 검증 범위이며 AWS 배포 결과는 별도 관리 |
| 로컬 API | `LOCAL_SYNTHETIC_IMPLEMENTED` | 로그인, 동의, 추천, 작업 기록 등을 다루는 FastAPI 소스와 자동 API 문서 소스가 있음 |
| 기업 공개정보 복사본 | `LOCAL_SYNTHETIC_IMPLEMENTED` | OpenDART 회사 개황·최근 공시를 기업 자료와 분리해 저장하는 코드가 있음. 기본은 합성 예시이며 추천 점수·정렬·기업 인증에 쓰지 않음 |
| 합성 학습 실험 | `EXPERIMENT_UNWIRED_NOT_APPROVED` | 완전 생성형 오프라인 코드가 있으며 현재 추천 런타임에 연결하지 않음 |
| MLOps 전용 서버리스 경로 | `MLOPS_PLANNED_NOT_DEPLOYED` | 합성 DB 옆 exporter, S3 입력·결과, Lambda 학습, DynamoDB 상태와 CloudWatch 로그 소스가 있음. 기본 계획 0, 단계별 계획 13/14이며 AWS 배포·호출 결과는 없음 |
| 로컬 코드 검사 | `STATIC_CHECKED` | 현재 공개 릴리스 검사는 6단계이며 Lab·MLOps·OpenDART 정적 검사와 단위시험 묶음을 실행함 |
| 로컬 검토 도구(Evidence Desk) | `LOCAL_SYNTHETIC_IMPLEMENTED`, `STATIC_CHECKED` | 민감정보를 지운 내부 검토용 복사본을 읽는 소스가 있음. 네트워크 전송과 브라우저 저장을 막지만, 승인 진위와 고객사별 데이터 분리는 구현하지 않음 |
| Bedrock 내부 연결 코드 | `IMPLEMENTED_GUARDED_NOT_ACTIVE` | `llm-gateway` 안에 코드가 있으나 기본값은 합성 응답이며 실제 호출은 잠겨 있음. 필요한 AWS 권한도 기준 설계에 없음 |
| 별도 Bedrock 실험 | `BRANCH_PROTOTYPE_UNDEPLOYED` | API Gateway, Lambda, Guardrail 실험 코드와 단위 검사가 있음. 과거 삭제 완료 이력 2건과 현재 관련 리소스 0개만 다른 세션이 읽기 전용으로 확인함. 성공한 AI 응답은 확인하지 못함 |
| 기준 ECR 이미지 | `PLANNED_UNIMPLEMENTED` | 이미지를 둘 저장소의 자리와 예시 주소만 있음. 최신 소스를 올리거나 AWS에서 실행한 증거는 없음 |
| 컨설턴트 대시보드 미리보기 | `PEER_OBSERVED_PREVIEW_AVAILABLE` | 화면과 API 소스, 빌드 결과가 있음. 다른 세션에서 최신 작업 성공, 화면 껍데기 응답, 공유 비밀번호 세션 발급을 확인함. 같은 버전인지, 실제로 접근 가능한지, 운영 요건을 갖췄는지는 확인하지 못함 |
| 대시보드 운영 조건 | `GATED` | 현재의 공유 비밀번호, 직접 입력한 이름, 공용 작업 공간은 사용자별 로그인, 고객사 분리, 운영 감사 기록을 대신할 수 없음 |
| 개선안(TO-BE) | `GATED` | 평가 승인 전에는 리소스 0개를 유지함. 승인에 문제가 있으면 아무것도 만들지 않음(fail-closed) |

기준 Terraform과 별도 변경분은 같은 상태가 아니다. 이전 92건 검사는 서버를 켜지 않고 코드와
합성 시험 자료의 예상 결과를 대조한 것이다. AWS, Docker, Bedrock, 서버, Terraform
계획과 적용은 실행하지 않았다. 과거에 확인한 `llm-gateway` 실행 이미지도 최신 소스와 달랐다.
따라서 최신 애플리케이션을 실제로 실행해 전체 흐름을 확인했다고 말할 수 없다.

## 2. 서비스 및 구성 요소 명세

> 이 장에서는 사용자의 요청이 어떤 AWS 서비스를 지나고, 데이터가 어디에 저장되도록
> 그려져 있는지 설명한다. 여기서 “그려져 있다”는 말은 실제 AWS에 배포됐다는 뜻이 아니다.

### 2.1 업무망 단말 현황

업무망에는 PC 180대가 있다는 사실과 운영체제별 수량만 `REQ-PC-01`로 사용자가 확정했다. 이번 명세에는
사용자가 정정한 Windows 100대, macOS 80대를 적용한다. 제공된 Claude Artifact와 현행 raw
`SCENARIO_FACTS`는 180대를 모두 Windows 단말로 적어 이 정정과 충돌한다. 따라서 100/80은
이번 명세의 `USER_CONFIRMED` 입력으로만 쓰며 저장소나 조직의 승인 근거로 취급하지 않는다.
단말은 AS-IS Terraform의 110개 planned resources에 포함되지 않는다.

| 구분 | 수량 | 비율 | 근거 수준 | 이 문서에서 확정하지 않는 항목 |
|---|---:|---:|---|---|
| Windows PC | 100대 | 55.6% | `USER_CONFIRMED` | Windows 버전, 도메인 가입, 패치·백신·EDR 상태 |
| macOS PC | 80대 | 44.4% | `USER_CONFIRMED` | macOS 버전, MDM 등록, FileVault·EDR 상태 |
| 합계 | 180대 | 100.0% | `USER_CONFIRMED` | 사용자 수, 동시 접속 수, 소유·대여 구분 |

단말에서 J-Career 공개 진입점까지의 실제 접속 방식, 사내 DNS·proxy·NAC·IdP 구성,
단말 관리 주체와 로그 수집 경로는 현재 근거로 확인되지 않았다. VPN+MFA와 UTM은 시나리오에
선언된 업무망 통제이며 구현·배치·운영 관찰 결과가 아니다. 흐름도에서는 업무망과 선언 통제를
별도 영역으로 표시하고 사용자 요청 흐름과 직접 연결하지 않는다.

Slack은 AWS 리소스나 J-Career 런타임 구성요소가 아니라 AWS 밖의 외부 업무 SaaS·자산대장
경계다. 확인된 구현 소스는 Windows와 macOS 이미지 정의의 자격증명 없는
`https://app.slack.com/client` 바로가기, 그리고 macOS 세션 정리에서 Slack 프로세스 종료를
best-effort로 시도하는 코드뿐이다. 이 종료 시도는 인증 cookie 삭제를 증명하지 않는다. 실제
workspace 사용, 소유자, 로그인, 개인정보 입력, 보존·삭제 설정은 `SCENARIO_USE_UNVERIFIED`로
남긴다. 따라서 Slack과 AWS 사이에 흐름선을 그리지 않으며 webhook/token, Amazon Q Developer
(AWS Chatbot), SNS, EventBridge 연동을 만들거나 현재 구성처럼 암시하지 않는다.

### 2.2 Terraform 구성을 나눈 여섯 부분

| 구성 부분 | 계획에 잡힌 항목 수 | 맡은 역할 | 주요 범위 |
|---|---:|---|---|
| `network` | 47 | VPC, 6개 subnet, IGW, NAT 2개, route table, security group | 2a/2c, public/app/data 계층 |
| `compute` | 27 | ALB, listener/rule/target group, ECS/ECR, scaling target | 네 서비스 경로 라우팅 |
| `data` | 16 | RDS, ElastiCache, S3 세 버킷과 정책 | 관계형 데이터, 캐시, 객체 및 로그 저장 |
| `security` | 9 | IAM 역할과 정책, SSM endpoint 3개 | 태스크 실행, S3 접근, 관리 채널 |
| `observability` | 6 | CloudWatch log group, CloudTrail, VPC Flow Log, GuardDuty | 로그, 관리 이벤트, 흐름 기록, 탐지 |
| `edge` | 5 | Route 53, CloudFront, ACM, WAF | 공개 DNS, 엣지 TLS, 관리형 WAF 규칙 |
| 합계 | 110 | AWS 비접속 계획 구조 | 배포 결과는 별도 검증 |

근거: `terraform/asis/main.tf`, 각 모듈의 `.tf` 파일,
`context/findings/PHASE1_ASIS_EVIDENCE.md`.

### 2.3 네트워크 배치

| 항목 | 2a | 2c | 상태 |
|---|---|---|---|
| Public subnet | `10.0.0.0/24` | `10.0.1.0/24` | `MODELLED` |
| Private App subnet | `10.0.10.0/24` | `10.0.11.0/24` | `MODELLED` |
| Private Data subnet | `10.0.20.0/24` | `10.0.21.0/24` | `MODELLED` |
| NAT Gateway | AZ별 1개 | AZ별 1개 | `MODELLED` |
| App 기본 경로 | 같은 AZ의 NAT | 같은 AZ의 NAT | `MODELLED` |
| Data 기본 경로 | 없음 | 없음 | VPC-local 경로만 `MODELLED` |

전체 내부 네트워크 주소 범위는 `10.0.0.0/16`이다. 여섯 서브넷은 각각 통신 경로표에
연결된다. 공개 서브넷은 인터넷 게이트웨이(IGW)를 쓴다. 애플리케이션 서브넷은 같은 AZ의
NAT를 거쳐 외부로 나가도록 설계됐다. 데이터 서브넷에는 인터넷으로 바로 나가는 기본
경로가 없다. 근거: `terraform/asis/network/main.tf`.

### 2.4 사용자가 들어오는 공개 경로

| 구성 요소 | 모델 값 | 상태와 한계 |
|---|---|---|
| Route 53 | 합성 `.example` 도메인의 public hosted zone과 alias A | `MODELLED`, 실제 위임 없음 |
| CloudFront | viewer HTTP는 HTTPS로 redirect, ALB origin은 HTTPS only, 동적 요청 캐시 비활성 정책 | `MODELLED` |
| Viewer TLS | ACM 인증서, 최소 `TLSv1.2_2021` | 인증서 DNS 검증 리소스 없음 |
| AWS WAF | CloudFront scope, Common 및 SQLi 관리형 그룹 | 커스텀 자유서술 입력 규칙 없음 |
| ALB | internet-facing, public subnet 2개, HTTPS 443 | 합성 인증서 ARN을 사용한 plan 모델 |

CloudFront, WAF, ACM의 제어 리전은 AWS 제약에 따라 별도 provider alias로 모델링되어
있다. 서비스 워크로드 리전의 확장으로 해석하지 않는다. 근거:
`terraform/asis/edge/main.tf`, `terraform/asis/providers.tf`.

### 2.5 애플리케이션을 나눈 네 서비스

| 서비스 | ALB 경로 | 포트 | CPU/메모리 | desired/min/max | 확인된 책임 | 상태 |
|---|---|---:|---|---|---|---|
| `web` | `/*` | 3000 | 256/512 MiB | 2/2/4 | React 정적 빌드, Nginx, P0 화면 | AWS 인프라 `MODELLED`; 별도 소스 `LOCAL_SYNTHETIC_IMPLEMENTED` |
| `api` | `/api`, `/api/*` | 8000 | 256/512 MiB | 2/2/4 | 인증·동의·이력서·지원·기업 프로필·추천·감사 API | AWS 인프라 `MODELLED`; 별도 소스 `LOCAL_SYNTHETIC_IMPLEMENTED` |
| `agent` | `/agent`, `/agent/*` | 8100 | 256/512 MiB | 2/2/4 | 결정론적 matcher와 후보자/공고 양방향 정렬 | AWS 인프라 `MODELLED`; 별도 소스 `LOCAL_SYNTHETIC_IMPLEMENTED` |
| `llm-gateway` | `/llm`, `/llm/*` | 8200 | 256/512 MiB | 2/2/4 | 설명 생성, 공급자 장애 격리, prompt 기록, Bedrock 내부 어댑터 | AWS 인프라 `MODELLED`; 합성 stub `LOCAL_SYNTHETIC_IMPLEMENTED`; Bedrock `IMPLEMENTED_GUARDED_NOT_ACTIVE` |

기준 Terraform에서 각 서비스는 Fargate task definition, ECS service, target group,
listener rule, ECR repository, scaling target으로 표현된다. task placement strategy는
명시하지 않고 두 App subnet을 ECS 서비스에 전달한다. 기준 worktree의 ECR에는 이미지가
없고 ECS 기동은 확인하지 않았다. 별도 로컬 변경 세트에는 프로세스와 health handler,
FastAPI OpenAPI 소스가 있으나 그 이미지가 이 ECR과 연결됐다는 증거는 없다.

`matcher`는 다섯 번째 ECS 서비스가 아니다. 로컬 변경 세트에서 `agent` 내부의 결정론적
구성으로 구현됐고, 제공된 Artifact의 독립 상자는 논리 책임을 표현한다. `llm-gateway`가
별도 ECS 단위로 승격된 과거 결정 근거는 현재 자료에서 확인되지 않는다. React Renderer는
별도 서비스가 아니라 로컬 `web`의 React 렌더링 책임이다. 근거:
`context/raw/D02-진단대상-아키텍처-정의.md#그림 1이 말하는 것 (시스템 구성 · 논리)`.

### 2.6 데이터 저장소

| 구성 요소 | 모델 값 | 상태와 한계 |
|---|---|---|
| RDS Primary | PostgreSQL, Multi-AZ, port 5432, 백업 보존 7일, 저장 암호화 | 엔진/크기/200 GiB는 `ASSUMED` |
| RDS Replica | 동일 리전 read replica, public 접근 비활성 | BI 연결 구현 없음 |
| ElastiCache | Redis, port 6379, node 2개, Multi-AZ/failover, 전송·저장 암호화 `false` | 크기/노드 수는 `ASSUMED`; 암호화 플래그는 `MODELLED`; 앱 TTL은 Terraform 속성이 아님 |
| Resume S3 | versioning enabled, SSE-S3, public access block | noncurrent version lifecycle 없음 |
| ALB log S3 | SSE-S3, bucket policy, 90일 expiration | public access block과 versioning은 미선언 |
| CloudTrail S3 | SSE-S3, CloudTrail bucket policy | lifecycle, versioning, public access block 미선언 |

기준 Terraform은 RDS와 ElastiCache endpoint를 task environment로 주입하지 않는다. 별도
런타임 변경 세트는 API에 회원·기업 DB URL 계약을 추가했지만 실제 기업 DB와 전용 role을
만드는 bootstrap, Redis 주소, agent/gateway 주소, session key와 검증된 service discovery는
없다. resource와 module block은 늘리지 않았다. 근거: 기준 `terraform/asis/*.tf`와 별도
변경 세트의 `terraform/asis/compute/*.tf`, `terraform/asis/data/*.tf`.

변경 세트는 애플리케이션 role 비밀번호가 포함된 두 DSN과 기존 LLM API key를 ECS
task definition의 일반 `environment` 값으로 구성한다. Terraform variable의 `sensitive`
표시는 화면 노출을 줄일 뿐 런타임 secret store를 만들지 않는다. ECS `secrets`와 Secrets
Manager가 없는 현재 계약은 credential 노출면이며 운영 배선으로 승인되지 않았다.

### 2.7 보안과 관리 경로

| 구성 요소 | 책임 | 모델 내용 |
|---|---|---|
| ALB SG | 공개 진입 | IPv4 전체에서 TCP 443, ECS의 4개 서비스 포트로만 egress |
| ECS SG | 내부 서비스 및 외부 egress | ALB와 self 참조 ingress, IPv4 전체 프로토콜 egress |
| RDS SG | DB 경계 | ECS SG에서 TCP 5432 ingress |
| Cache SG | 캐시 경계 | ECS SG에서 TCP 6379 ingress |
| Endpoint SG | 관리 endpoint | ECS SG에서 TCP 443 ingress |
| SSM endpoint | 관리 채널 | `ssm`, `ssmmessages`, `ec2messages`, App subnet 2개 |
| ECS execution role | 이미지 pull과 awslogs | AWS 관리형 execution policy attachment |
| ECS task role | S3 resume와 session channel | resume 객체 read/write/list 및 session message actions |
| Flow Log role | CloudWatch 전달 | 로그 그룹 생성 및 스트림 쓰기 권한 |

SSM endpoint 경유 여부는 기획 원문이 확정하지 않은 `ASSUMED` 모델이다. bastion, key pair,
SSH 22 ingress는 선언하지 않았다. 근거: `terraform/asis/security/*.tf`,
`terraform/asis/network/security_groups.tf`.

### 2.8 로그와 이상 징후 탐지

| 구성 요소 | 모델 값 | 미표현 또는 한계 |
|---|---|---|
| Access log group | 보존 365일 | 로컬 로그 계약과 AWS log stream 연결은 미검증 |
| VPC Flow log group | 보존 30일 | VPC `ALL` 흐름을 CloudWatch Logs로 전달 |
| Prompt raw log group | 보존기간 미설정 | 로컬 gateway는 volume에 raw prompt를 쓰지만 CloudWatch 연결·파기 미검증 |
| CloudTrail | logging enabled, 관리 이벤트 기본 범위 | S3 data event selector 없음 |
| GuardDuty | detector enabled | finding 처리, 알림, 대응 런북 없음 |
| AWS Config | 선언 없음 | 구성 변경 이력 수집을 표현하지 않음 |
| CloudFront access log | 선언 없음 | distribution에 `logging_config` 없음 |
| AWS WAF log | 선언 없음 | `aws_wafv2_web_acl_logging_configuration` 없음 |

근거: `terraform/asis/observability/main.tf`,
`terraform/asis/security/absences.tf`, `terraform/asis/ABSENCE_MANIFEST.md`,
`terraform/asis/edge/main.tf`.

### 2.9 컨설턴트 대시보드가 지켜야 할 경계

대시보드는 컨설턴트가 소유하는 별도 서비스다. AS-IS의 110개 planned resources에 포함되지
않으며 client AWS에 직접 연결하지 않는다. 구현도 하나로 뭉뚱그리지 않는다. 별도
`feat/iso-dashboard`의 AIMS Desk는 React SPA, build 산출물, Amplify 배포 스크립트와
API Gateway·Lambda·DynamoDB·SSM 계약을 가진 팀 preview다. 사용설명서는 2026-08-28 배포본을
기록한다. 별도 동료 세션의 같은 날 읽기 전용 확인에서 최신 Amplify job 성공, 공개 shell
HTTP 200과 shared-passcode session 발급을 관찰했다. 이 명세 작성 세션은 AWS를 조회하지 않았고,
관찰된 preview를 client AWS나 운영 서비스로 취급하지 않는다.

| 층 | 구현·허용 입력 | 경계와 한계 | 상태 |
|---|---|---|---|
| 외부 미리보기 번들 | `publicationMode=preview-redacted` 집계 snapshot | 상세 finding, 원문, 계정 식별자, 비밀정보 제외 | `REPO_REPORTED_PREVIEW_DEPLOYED` |
| 팀 공유 preview | YAML/JSON 검토 초안과 shared workspace | shared passcode, 자기 선언 nickname, 8시간 일괄 session; 개별 사용자 인증·개별 revoke 아님 | `PEER_OBSERVED_PREVIEW_AVAILABLE` |
| 로컬 Evidence Desk | `jcareer-consulting-snapshot/v1`, `INTERNAL_REVIEW`, `REDACTED` 입력 | 브라우저 메모리에서만 읽고 `connect-src 'none'`, fetch/XHR와 브라우저 영구 저장 없음. `EXTERNAL_PREVIEW` 입력은 거부 | `LOCAL_SYNTHETIC_IMPLEMENTED`, `STATIC_CHECKED` |
| 컨설턴트 backend | HTTP API/Lambda, 암호화 DynamoDB+PITR, SSM SecureString, activity 기록 | client AWS가 아니라 컨설턴트 영역. activity는 성공한 session/save 중심이며 immutable audit trail 아님 | 소스·템플릿 존재, 저장소상 배포 기록 |
| 운영 배치 | approved snapshot ingestion만 | per-user auth, tenant isolation, audit logs, 승인 진위 검사 | `GATED` |
| client AWS 직접 조회 | 없음 | 자격증명, cross-account role, API poller를 두지 않음 | `OUT_OF_SCOPE` |

로컬 Evidence Desk의 validator·화면 변환·원본 자료 결속 시험은 28건을 통과했다. 이는 소스와
합성 시험 범위이며, 승인된 복사본 반입이나 운영 배포를 확인한 결과는 아니다.

AIMS Desk의 현재 소스에는 조항별 다음 조치 행과 네 가지 빠른 필터(우선순위, 판단 대기,
근거 없음, 담당자 없음)가 있다. 담당자와 확인 기한을 입력·표시하며 대비 token도 보정했다.
이는 저장소 코드 상태다. 읽기 전용 가용 관찰만으로 원격 배포본이 같은 revision인지, 해당
기능이 모두 반영됐는지 또는 실제 접근성 검사를 통과했는지는 확인할 수 없다.

Snapshot에는 생성자, 생성 시각, tenant, schema version, source classification, 승인자,
redaction 상태와 원본 해시가 필요하다. AIMS Desk import와 로컬 Evidence Desk는 구조와 선언
metadata를 검사하지만 승인자 진위나 선언 해시의 정본 여부는 증명하지 못한다. Evidence Desk의
`tenant_ref` 일치 검사는 한 파일 안에서 자료가 섞이는 것을 막는 내용 결속일 뿐 서버 저장소
분할이나 객체 인가가 아니다. 운영용 approved snapshot schema, 서명·검증 방식과 tenant binding은
아직 `UNKNOWN`이다.

### 2.10 운영자와 분석가의 접근 지점

기존 토폴로지와 제공된 Artifact에는 운영자 콘솔, BI 조회, staging band가 관리·분석 접근
지점으로 나타난다. 이들은 경로 A·C·D의 진단 맥락이지만 AS-IS Terraform 110개 리소스에
대응하는 콘솔, BI, staging 리소스는 없다. 접속 주체, 인증, network path, read/write 권한과
데이터 담당 인원도 확인되지 않았다. 따라서 모두 `PLANNED_UNIMPLEMENTED` 또는 `UNKNOWN`으로
기록하며 VPC 내부의 실제 배치로 해석하지 않는다.

### 2.11 로컬 AI 예시 코드와 별도 실험

아래 변경은 기준 Terraform 110개 planned resources와 구분해 읽는다. 신규 ECS
마이크로서비스가 추가된 것이 아니라 기존 네 단위의 책임과 로컬 실행 계약이 구체화됐다.

| 변경 항목 | 구현 내용 | 경계와 미완료 사항 | 상태 |
|---|---|---|---|
| React/Nginx 화면 | 업무 동적 경로 16개와 `/privacy`, `/terms` 정적 안내 | 로컬 127.0.0.1 바인딩; ECR 게시·ECS 기동 미확인 | `LOCAL_SYNTHETIC_IMPLEMENTED` |
| FastAPI 업무 API | 가입·인증·동의·이력서·지원·기업 프로필·추천·감사 | 합성 seed 전용; 운영 키·migration·service discovery 미완료 | `LOCAL_SYNTHETIC_IMPLEMENTED` |
| API 소스·효과 계약 | API 라우트 30개 + agent 별칭 6개 + gateway 별칭 4개, 합계 40개 경로를 35개 처리 함수로 정리. 같은 작업의 저장·감사·외부 호출 효과를 소스 지문으로 고정 | 소스 구조를 보는 부분 검사다. 실제 분기 실행, 횟수, 원자성, 후속 서비스 수신과 완전한 OpenAPI 계약은 증명하지 않음 | `STATIC_CHECKED` |
| 결정론적 matcher | 기술 70, 경력 20, 희망 직무 10의 버전 고정 산식 | 실제 모델 품질·편향·설명 충실도 평가를 대신하지 않음 | `LOCAL_SYNTHETIC_IMPLEMENTED` |
| 설명 생성기 | 점수·정렬을 바꾸지 않는 설명과 `company_alignment` 생성 | 의미 grounding과 금칙 결론 검증 없음; alignment의 `score_effect=NONE` | `LOCAL_SYNTHETIC_IMPLEMENTED` |
| OpenDART 공개정보 보조 기능 | 회사 개황과 최근 1년 공시 최대 5건을 별도 복사본으로 저장하고 출처 시각을 표시 | 기본은 합성 예시를 바로 읽는다. 선택적인 SQS FIFO→Lambda 작업자 소스도 있으나 패키지·키·DB 권한·AWS 자원·실행 증거는 없음. 등록 기업명 불일치·조회 실패 때 기존 정상 복사본을 유지하며 점수 영향은 없음 | 로컬 `LOCAL_SYNTHETIC_IMPLEMENTED`, 작업자 `PROTOTYPE_UNDEPLOYED` |
| 오프라인 학습 비교 실험 | seed 고정 합성 자료로 단순 도전자 모델과 관찰값을 파일로 생성 | 실제 회원·고객사 자료를 읽지 않음. `runtime_wired=false`, 자동 승격·채용 판정·AWS 자원 생성 없음 | `EXPERIMENT_UNWIRED_NOT_APPROVED` |
| 서버리스 MLOps 경로 | 합성 DB 옆 exporter가 원문 없는 숫자 특징 5개를 만들고, feature-only S3 입력 세 파일을 일회성 Lambda가 검사·학습해 S3 결과 6개, DynamoDB 상태와 CloudWatch Logs를 남김 | 별도 Terraform 0/13/14 계획. 기본 잠금, 수동 시작, 동시성 1. 실제 AWS 배포·호출, 자동 일정·승격·추천 런타임 배선 없음 | `MLOPS_PLANNED_NOT_DEPLOYED` |
| Bedrock 내부 어댑터 | 기존 `llm-gateway`에서 Converse 호출 코드와 `apac.amazon.nova-lite-v1:0` 기본 profile 제공 | 기본 provider는 합성 stub, 실호출 잠금 유지, 기준 task IAM 권한 없음; APAC 교차 리전 처리 가능성 미승인 | `IMPLEMENTED_GUARDED_NOT_ACTIVE` |
| 회원/기업 데이터 경계 | 같은 PostgreSQL의 두 논리 DB와 서로 다른 role | 동일 RDS 장애·백업 경계 공유; 기업 DB bootstrap 미구현; 교차 쓰기 비원자적 | 로컬 `LOCAL_SYNTHETIC_IMPLEMENTED`, AWS 계약 `MODELLED` |
| Redis 추천 캐시 | 응답을 24시간 저장. 지원자 경로는 이력서·공고 재료를 key에 묶지만 기업 경로는 cache hit를 회원 DB보다 먼저 반환 | 기업 경로 key에는 지원자 집합·이력서 version이 없고 탈퇴 시 cache와 raw prompt도 즉시 삭제되지 않음 | `LOCAL_SYNTHETIC_IMPLEMENTED` |
| 관리형 Bedrock 실험 | 별도 브랜치에 API Gateway, Lambda, Guardrail/Version과 `apac.amazon.nova-micro-v1:0` profile | 기준 서비스에 미병합. 과거 `DELETE_COMPLETE` 2건, 현재 관련 리소스 0으로 관찰됐으며 성공 추론 증거는 미확인. RAG 없음, 기준 110개에 미포함; 서울 외 APAC destination 허용 정책 선언 | `BRANCH_PROTOTYPE_UNDEPLOYED` |
| TRACE·JC-RECEIPT 계열 | 비교용 권고안에서 TRACE는 서비스 브랜드, Decision Receipt는 사용자 경험, JC-RECEIPT는 기술적 증적 형식, Recourse Twin은 권리 여정으로 구분 | 명칭 관계도 미확정이며 구현·승인·Terraform/API 연동 0건. AS-IS 구성요소로 세지 않음 | `OUT_OF_SCOPE` |

관리형 Bedrock 실험 템플릿의 리소스 선언은 12개다. Guardrail과 그 버전 두 개는 항상
선언되며, 로그 그룹·IAM·Lambda·HTTP API·통합·라우트·스테이지·호출 권한 열 개에는
런타임 활성화 조건이 붙는다. 이 수치는 CloudFormation 소스의 선언 수이며 Terraform mock plan의
110개에 더하지 않는다. 배포 수량이나 실제 AWS 자원 수로도 읽지 않는다.

JC-RECEIPT 제안의 fail-closed 동작과 기존 외부 공급자 흐름 사이에는 미해소 충돌이 있다.
사람이 채택 여부를 정하기 전에는 제안 문구를 현재 추천 응답 계약이나 TO-BE gate로 옮기지 않는다.

원시 설계 자료의 `screening`, `chatbot`, `detector`, `harness` 명칭은 현재 Compose와
런타임 소스에 없다. 해당 항목은 `RAW_DRAFT_ONLY`로 분류한다.

### 2.12 MLOps 현재 범위와 인프라 변경 경계

MLOps는 추천 모델을 바로 교체하는 기능이 아니라, 합성 자료로 후보 모델을 만들고 사람이
검토할 수 있게 결과를 남기는 별도 경로다. 기존 오프라인 예시와 합성 DB를 직접 읽는 로컬
경로에 더해, 숫자 특징 파일만 받는 서버리스 경로가 `terraform/serverless-mlops`에 추가됐다.
세 경로 모두 현재 추천 순위를 정하는 70·20·10 산식을 바꾸지 않는다.

완전 생성형 오프라인 경로의 결과 상태는 `TRAINED_SYNTHETIC_NOT_APPROVED`와
`MEASURED_SYNTHETIC_NOT_ASSESSED`다. 서버리스 경로는 이를 그대로 쓰지 않고 `RUNNING` 뒤
`TRAINED_PENDING_HUMAN_REVIEW` 또는 `FAILED_SAFE`로 기록한다. 두 경로의 상태를 섞어 읽지 않는다.

서버리스 경로는 다음 일곱 단계로 읽는다. 도면에서 합성 DB와 exporter는 소스 구현 범위,
S3·Lambda·DynamoDB·CloudWatch는 별도 Terraform 계획 범위, 마지막 상태는 미승인 사람 검토
경계로 구분한다.

| 단계 | 하는 일 | 자료 또는 AWS 구성 | 멈추는 지점 |
|---|---|---|---|
| 1. 합성 자료 읽기 | 별도 EC2 랩의 합성 회원·기업 DB를 exporter가 읽음 | DB 연결은 exporter 안에서만 사용 | 운영 자료 표식이나 합성 형식이 맞지 않으면 중단 |
| 2. 비교 수치 만들기 | 기술·경력·직무, 자소서와 공고의 단어 겹침, 기업 방향과 공고의 단어 겹침을 숫자 5개로 바꿈 | 이름·이메일·전화·원문은 입력 파일에 보관하지 않음 | 허용되지 않은 항목이 생기면 중단 |
| 3. 입력 파일 보관 | 원문 없는 feature CSV 1개와 검증 JSON 2개를 실행 번호별 경로에 둠 | Amazon S3, 버전 관리, SSE-S3 | 필수 세 파일이 없거나 크기·상호 해시가 다르면 중단 |
| 4. 담당자가 한 번 시작 | 확인값, 실행 번호와 내용 지문으로 고정한 이미지 주소를 입력 | 공개 API와 자동 일정 없음 | 확인값이나 이미지 조건이 맞지 않으면 시작하지 않음 |
| 5. 파일 검사·후보 학습 | 파일 사이 해시와 허용 항목을 확인하고 후보 모델을 한 번 학습 | AWS Lambda, 동시 실행 1 | 검사나 학습 실패 시 안전 실패 기록을 시도 |
| 6. 결과와 상태 기록 | S3 결과 파일 6개, DynamoDB 실행 상태와 CloudWatch Logs를 실행 번호별로 남김 | Amazon S3, DynamoDB, CloudWatch Logs | 같은 실행 번호로 기존 결과를 덮어쓰지 않음 |
| 7. 사람 검토 대기 | 결과를 `TRAINED_PENDING_HUMAN_REVIEW`로 끝냄 | 자동 모델 등록·승격·배포 없음 | 승인 전 추천 서비스에 연결하지 않음 |

Terraform은 기본값에서 닫히고, 필요한 단계만 따로 계획하도록 나뉜다.

| Terraform 단계 | 계획 수 | 포함 범위 | 확인 조건 |
|---|---:|---|---|
| `disabled` | 0 | 생성 계획 없음 | 기본값 |
| `bootstrap` | 13 | ECR, S3, DynamoDB, CloudWatch Logs와 경로·표 범위로 제한한 IAM | 정확한 확인값과 보관함 이름 |
| `runtime` | 14 | 위 13개와 일회성 Lambda 1개 | 같은 ECR의 내용 지문(`@sha256`)으로 고정한 이미지 |

이 수치는 AWS에 접속하지 않은 Terraform 검증 결과이며 기준 AS-IS의 110개와 합산하지 않는다.
MLOps 전용 루트에는 RDS, NAT Gateway, API Gateway, EventBridge 일정, SageMaker와 Bedrock 임베딩이
없다. Lambda는 회원·기업 DB에 직접 연결하지 않고 S3의 정해진 feature-only 세 파일만 읽는다. 확인값은 실수로
켜는 것을 막는 절차 장치이지 사용자 인증이나 조직 승인 증거는 아니다. 저장 암호화는 현재
SSE-S3이며 별도 KMS 키는 연결하지 않았다.

단어 겹침 두 항목은 문맥 이해나 임베딩이 아니다. 지원 진행 단계 표식도 합격 가능성, 지원자
품질이나 채용 성공을 나타내지 않는다. 관찰값이 좋아 보여도 모델 품질·공정성·출시 가능성을
판정하지 않으며 자동 승격하지 않는다. AWS 배포, 이미지 등록과 Lambda 실행 결과도 별도 검증
기록이 생기기 전에는 확인된 사실로 쓰지 않는다.

공개 검증 기록에는 MLOps Terraform 단계 3/3, 경계 시험 19/19, 합성 파이프라인 단위시험 22/22가
PASS로 적혀 있다. 이는 코드와 계획의 정해진 조건만 확인한 결과다. 기준 110개 구성은 그대로 유지하고,
전용 페이지와 PDF에서 7단계 흐름과 계획 상태를 별도로 제공한다.

## 3. 기능 명세

> 이 장은 사용자가 보게 될 화면과 기능을 설명한다. 기획에만 있는 기능과 별도 로컬
> 코드에 있는 기능을 나누어 적었다. 실제 운영 서비스가 완성됐다는 뜻은 아니다.

### 3.1 사용자와 역할

| 역할 | 계획 기능 | 현재 상태 |
|---|---|---|
| 구직자 | 가입, 동의, 이력서 입력, 공고 탐색/지원, 추천 공고, 철회/탈퇴 | 로컬 합성 `LOCAL_SYNTHETIC_IMPLEMENTED`; AWS 미배포 |
| 기업 채용 담당자 | 기업 가입, 기업 방향·핵심가치 관리, OpenDART 공개정보 복사본 확인, 공고 관리, 지원자 pipeline, 공고별 지원자 탐색·근거 확인·최대 3명 임시 비교 | 로컬 합성 `LOCAL_SYNTHETIC_IMPLEMENTED`; 공개정보는 점수에 영향 없음, AWS 미배포 |
| 운영자 | audit event 조회 | 로컬 합성 `LOCAL_SYNTHETIC_IMPLEMENTED`; 추천 실행 전용 감사 이벤트는 미구현 |
| IS/DevOps | SSM 관리 채널 | 인프라 경로만 `MODELLED` |
| 컨설턴트 preview 사용자 | redacted/imported 검토 초안을 공유 workspace에서 검토 | `PEER_OBSERVED_PREVIEW_AVAILABLE`; shared passcode와 자기 선언 nickname 사용 |
| 운영 대시보드 사용자 | approved snapshot 기반 tenant별 조회·감사 | `GATED`; per-user auth·tenant isolation 미구현 |
| 외부 미리보기 사용자 | redacted snapshot 기반 집계만 열람 | public shell 응답만 관찰. approved snapshot 내용, 동일 revision과 접근성은 미확인 |

### 3.2 우선 구현 대상(P0) 화면 계획

기존 계획의 P0 동적 화면 14개에 기업 overview와 지원자 홈이 추가되어 로컬 합성 런타임에는 동적
경로 16개가 있다. 아래 경로는 로컬 React/Nginx 소스 기준이며 기준 ECR 이미지나 AWS
서비스의 동작을 뜻하지 않는다.

| 영역 | 경로 | 계획 기능 |
|---|---|---|
| 공개 | `/jobs` | 공고 검색, 필터, 목록 |
| 공개 | `/jobs/:id` | 공고 상세와 지원 액션 |
| 구직자 | `/signup` | 회원 가입 |
| 구직자 | `/signup/consent` | 개인정보 수집 및 이용 동의 |
| 구직자 | `/login` | 역할 공용 로그인 |
| 구직자 | `/candidate/home` | 이력서·동의·지원 현황과 다음 할 일을 모아 보는 홈 |
| 구직자 | `/candidate/resume` | 구조화 이력서와 자유서술 입력 |
| 구직자 | `/candidate/applications` | 지원 현황 |
| 구직자 | `/candidate/recommendations` | AI 추천 공고 |
| 구직자 | `/candidate/withdraw` | 동의 철회와 탈퇴 |
| 기업 | `/recruiter/signup` | 기업 회원 가입 |
| 기업 | `/recruiter/overview` | 공고·지원 단계 집계와 최근 공고 조회 |
| 기업 | `/recruiter/jobs` | 공고 등록, 수정, 마감 |
| 기업 | `/recruiter/jobs/:id/pipeline` | 지원자 pipeline |
| 기업 | `/recruiter/jobs/:id/recommendations` | 해당 공고 지원자 안에서 검색·필터, 점수 근거, 최대 3명 임시 비교 |
| 운영자 | `/admin/audit` | audit event 조회 |

`/privacy`와 `/terms`는 기존 계획에서 정적 페이지로 분리한다. 근거:
`context/raw/Orca-범위확정-EnterpriseMVP.md#P0 — 14화면 (측정 5건이 나오는 최소 경로 · 절대 불가침)`.
로컬 구현 근거: `src/runtime/README.md#구현된-P0-경로`.

### 3.3 다음 단계(P1) 기능 계획

P1 원문 제목은 12화면이라고 적지만 열거 항목은 동적 화면 11개와 Mailpit 비화면 기능
1개다. 이 명세는 열거된 기능의 성격에 따라 11개 화면과 비화면 기능으로 분리한다.
feature flag, 라우트, 어댑터는 구현되지 않았다.

| 기능군 | 계획 항목 | 상태 |
|---|---|---|
| 공개/구직자 | landing, profile, GitHub portfolio | `PLANNED_UNIMPLEMENTED` |
| 기업 | Kakao 주소, 합성 증빙, 후보 저장 목록, 후보 조회 기록 | `PLANNED_UNIMPLEMENTED` |
| 운영자 | company review, consent history, AI call history, integration status | `PLANNED_UNIMPLEMENTED` |
| 알림 | Mailpit 기반 가입/지원/상태 알림 | `PLANNED_UNIMPLEMENTED` |

P1 외부 연계인 GitHub, Kakao, Mailpit에 대해 timeout, cache, schema validation,
rate-limit 처리, mock fixture, disabled fallback이 계획되어 있으나 구현 증거는 없다.

### 3.4 추천 결과를 만드는 순서

로컬 합성 런타임의 지원자 추천과 기업 추천은 cache 조회 위치가 다르다.

지원자 추천은 다음 순서다.

1. `api`가 bearer token, candidate 역할, 본인 범위와 최신 `privacy_core` 동의를 검사한다.
2. 회원 DB에서 Resume를 읽고 기업 DB에서 공개 Job과 Company profile을 읽는다.
3. 이력서 갱신 시각과 열린 공고 재료를 묶은 key로 Redis를 조회한다.
4. cache miss이면 `agent`가 구조화 feature로 기술 70, 경력 20, 직무 10의 점수와 breakdown을 만든다.
5. `llm-gateway`가 설명과 `company_alignment`를 만들고 정상 응답을 24시간 캐시한다.

기업 추천은 다음 순서다.

1. `api`가 bearer token, recruiter 역할과 해당 공고의 `company_id` 소유 범위를 검사한다.
2. Redis를 먼저 조회한다. cache hit이면 회원 DB와 현재 공급자를 다시 확인하지 않는다.
   저장된 후보자 payload, 점수와 설명을 그대로 반환한다.
3. cache miss일 때만 회원 DB에서 활성 지원자와 현재 Resume를 읽고 `agent`, `llm-gateway`를 호출한다.
4. 기업 cache key에는 지원자 집합과 이력서 version이 없다. 탈퇴·비활성화·이력서 변경이
   TTL 안에 즉시 반영된다고 보장할 수 없다.

`web`은 두 경로 모두 API의 score breakdown을 재계산하지 않는다. cache miss에서 gateway 연결,
HTTP, JSON, 계약 또는 경로 오류가 생기면 legacy 상태 `UNAVAILABLE_PROVIDER`로 묶는다. 이 상태는
외부 공급자 자체의 장애를 증명하지 않는다. cache hit도 과거 설명을 반환할 뿐 현재 공급자를
재검증하지 않는다.

기업 화면의 검색·기술·최소 표시 점수 필터는 이미 받은 응답을 화면에서만 좁힌다. 서버가 준
순서를 바꾸지 않고 새 후보를 조회하지 않는다. 최대 3명 임시 비교도 기존 점수 내역을
나란히 표시할 뿐 저장·공유·후보 저장 목록·채용 결정 이벤트를 만들지 않는다. 따라서 “기업용 인재
찾기”는 현재 **자기 회사의 한 공고에 지원한 활성 지원자 범위**이며, 플랫폼 전체 인재 소싱이나
기업 적합성 판정으로 읽지 않는다. 기업 선언 가치와 자소서의 문자열 대조도 `score_effect=NONE`이다.

일반 인증·동의·거부·기업 프로필 감사 이벤트는 있으나 추천 실행 단위 `match_run` 이벤트와
`match_results`, `ai_explanations` 전용 영속 모델은 없다. 위 흐름은
`LOCAL_SYNTHETIC_IMPLEMENTED`이며 Terraform이 확인하는 것은 ALB 경로, 태스크 경계, NAT
egress와 로그 목적지뿐이다.

### 3.5 개인정보 동의와 회원 탈퇴 계획

- 로컬 합성 런타임은 동의를 상태 덮어쓰기가 아닌 `ConsentEvent` 이력으로 기록한다.
- 핵심 동의 전 이력서 저장과 추천 요청, 철회 후 추천 요청을 거부하는 경로가 있다.
- AI 추천 목적을 별도 consent type으로 분리하지 않은 기존 한계는 남아 있다.
- 로컬 탈퇴는 주 DB의 이력서·지원 관계를 제거하고 기존 token을 무효화하지만, Redis 추천
  캐시와 raw prompt 기록은 즉시 함께 제거하지 않는다.
- `pii_purged_at`, 전 저장면 삭제 orchestration, RDS backup·S3 version 전파는 미구현이다.
- 실제 지원자 데이터는 사용하지 않으며 검증 데이터는 전량 합성이어야 한다.

근거: `context/raw/C플러스-범위델타-구직자흐름.md#1.6`,
`context/raw/C플러스-범위델타-구직자흐름.md#3`.

### 3.6 AI 추천 점수와 설명 규칙

| 항목 | 현재 로컬 계약 | 금지하는 해석 |
|---|---|---|
| 산식 | `deterministic-70-20-10-v1`: 요구 기술 최대 70 + 경력 최대 20 + 희망 직무 연관 최대 10 | 실제 모델 성능, 기업별 승인 가중치, 공정성 결과로 해석하지 않음 |
| 점수 입력 | 기술, 최소 경력, 공고 제목과 희망 직무의 정규화 일치 | 이름·연락처·생년월일·주소·학교·자격증·자기소개를 점수에 썼다고 해석하지 않음 |
| 설명 입력 | 현재 경로는 candidate 8개와 company 6개, 합계 14개 context 필드를 전달하며 candidate 필드 중 6개 이름을 PII 후보로 기록 | 필드명 분류가 법적 개인정보 판정이나 masking 완료를 뜻하지 않음 |
| 설명 권한 | `llm-gateway`는 확정된 점수·정렬을 문장화하고 이를 덮어쓰지 않음 | 생성 문장을 채용 결정, 우선 채용 보장, 점수 근거의 자동 검증으로 사용하지 않음 |
| 기업 방향 비교 | 기업 선언 가치와 자기소개 직접 표현의 일치를 `company_alignment`로 반환 | `score_effect=NONE`; 점수·정렬·합격 여부에 반영됐다고 표현하지 않음 |
| 설명 경로 실패 | gateway 연결·HTTP·JSON·계약·경로 오류를 legacy `UNAVAILABLE_PROVIDER`로 묶고 점수와 순서는 유지 | 이 상태만으로 외부 공급자 장애, 요청 도달 또는 prompt 기록 생성을 단정하지 않음 |
| cache 출처 | 과거 설명을 반환하며 `CACHE_HIT_PROVIDER_NOT_REVALIDATED`, `CACHE_ENTRY_ACCEPTED_ORIGIN_NOT_VERIFIED`로 현재 검증 부재를 표시 | 현재 공급자 정상, 과거 gateway 검증 완료, 원본 준비 field 집합 확인으로 읽지 않음 |
| Bedrock | 내부 adapter는 APAC Nova Lite, 별도 lab은 APAC Nova Micro 교차 리전 profile을 선언하지만 기본 잠금·미배포 상태 | 별도 신규 기준 서비스, AWS 준비 완료, 실제 호출, 서울 고정 처리 또는 처리 위치 승인으로 표현하지 않음 |

장애·보훈·군경력·한부모 등 참고 화면에만 있는 속성은 현재 데이터 모델과 산식에 없다.
수집 목적, 동의, 접근권한, 추천 사용 여부를 사람이 결정하기 전에는 입력 항목으로 승계하지
않는다.

## 4. API 명세

> API는 화면과 서버가 요청을 주고받는 주소와 규칙이다. 이 장은 확인된 주소, 입력값,
> 결과와 오류를 적는다. 주소가 문서나 소스에 있다는 사실만으로 실제 서버가 켜져 있다고
> 볼 수는 없다.

### 4.1 외부 요청이 들어오는 경로

| 우선순위 | 경로 | 대상 | 포트 | health path | 상태 |
|---:|---|---|---:|---|---|
| 100 | `/api`, `/api/*` | `api` | 8000 | `/health` | `MODELLED` |
| 200 | `/agent`, `/agent/*` | `agent` | 8100 | `/health` | `MODELLED` |
| 300 | `/llm`, `/llm/*` | `llm-gateway` | 8200 | `/health` | `MODELLED` |
| 400 | `/*` | `web` | 3000 | `/` | `MODELLED` |

ALB listener는 HTTPS 443이고 default action도 `web` target group이다. Target group과
태스크 사이 프로토콜은 HTTP다. 근거: `terraform/asis/compute/locals.tf`,
`terraform/asis/compute/main.tf`.

### 4.2 로컬 예시용 업무 API

아래 계약은 별도 FastAPI 소스에서 직접 확인했다. 성공 코드는 decorator와 기본 FastAPI
동작을 기준으로 적었다. 요청·응답의 전체 필드 정의는 실행 시 생성되는 OpenAPI가 기준이며,
이 표는 검토용 요약이다. 모든 경로는 `LOCAL_SYNTHETIC_IMPLEMENTED`이고 AWS 배포는
확인하지 않았다.

| Method | Path | 기능 | 인증·객체 범위 | 정상 상태 |
|---|---|---|---|---:|
| GET | `/health` | 회원·기업 DB 연결을 포함한 API health | 공개 로컬 endpoint | 200 |
| GET | `/api/v1/runtime` | 합성 데이터 profile, 설명 provider, 기능 flag 표시 | 공개; 실제 서비스 상태로 사용 금지 | 200 |
| POST | `/api/v1/auth/signup` | 구직자 가입 | 가입 전 입력 검증 | 201 |
| POST | `/api/v1/auth/signup/recruiter` | 기업 조직과 담당자 가입 | 두 논리 DB split write | 201 |
| POST | `/api/v1/auth/login` | 활성 계정 인증과 token 발급 | 구직자·기업·운영자 | 200 |
| GET | `/api/v1/auth/me` | 현재 계정과 역할·기업 연결 조회 | bearer token | 200 |
| POST | `/api/v1/candidates/me/consents` | 동의 grant/revoke 이벤트 기록 | candidate 본인 | 201 |
| GET | `/api/v1/candidates/me/consents` | 동의 이력 조회 | candidate 본인 | 200 |
| DELETE | `/api/v1/candidates/me/consents/{consent_type}` | `privacy_core` 또는 `marketing` 철회 기록 | candidate 본인 | 201 |
| GET | `/api/v1/candidates/me/resume` | 구조화 이력서 조회 | candidate 본인; 미존재 404 | 200 |
| POST | `/api/v1/candidates/me/resume` | 구조화 이력서 생성·갱신 | candidate 본인; 핵심 동의 필요 | 200 |
| GET | `/api/v1/jobs` | 공개 중인 공고 검색 | 공개; `q`, `location` query | 200 |
| GET | `/api/v1/jobs/{job_id}` | 공고 상세 | 공개 | 200 |
| POST | `/api/v1/jobs/{job_id}/applications` | 공고 지원 | candidate 본인; 핵심 동의와 이력서 필요 | 201 |
| GET | `/api/v1/candidates/me/applications` | 본인 지원 현황 | candidate 본인 | 200 |
| GET | `/api/v1/candidates/me/recommendations` | 후보자 기준 추천 공고·점수·설명 | candidate 본인; 핵심 동의 필요 | 200 또는 matcher 불가 시 503 |
| DELETE | `/api/v1/candidates/me` | 계정 탈퇴와 주 DB 정리 | candidate 본인 | 202 |
| GET | `/api/v1/recruiter/jobs` | 소속 기업 공고 조회 | recruiter의 `company_id` 범위 | 200 |
| GET | `/api/v1/recruiter/overview` | 공고·지원 단계 집계와 최근 공고 조회; 채용 판단 없음 | recruiter의 `company_id` 범위 | 200 |
| GET | `/api/v1/recruiter/company-profile` | 기업 방향·선언 가치 profile 조회 | recruiter의 `company_id` 범위 | 200 |
| PUT | `/api/v1/recruiter/company-profile` | 기업 profile 새 version 저장 | recruiter의 `company_id` 범위 | 200 |
| POST | `/api/v1/recruiter/company-profile/opendart/refresh` | 회사 개황·최근 공시 복사본 갱신 요청 | recruiter의 `company_id` 범위; 기업명 일치와 입력 형식 검사 | 202 |
| POST | `/api/v1/recruiter/jobs` | 소속 기업 공고 생성 | recruiter의 `company_id` 범위 | 201 |
| PUT | `/api/v1/recruiter/jobs/{job_id}` | 소속 기업 공고 수정 | 서버 측 소유 기업 검사 | 200 |
| GET | `/api/v1/recruiter/jobs/{job_id}/pipeline` | 공고별 지원자 pipeline | 서버 측 소유 기업 검사 | 200 |
| PATCH | `/api/v1/recruiter/applications/{application_id}` | 지원 단계 변경 | application→job→company 소유 검사 | 200 |
| GET | `/api/v1/recruiter/jobs/{job_id}/recommendations` | 공고 기준 후보 추천·점수·설명 | 서버 측 소유 기업 검사 | 200 또는 matcher 불가 시 503 |
| GET | `/api/v1/admin/audit` | event type·company 필터 감사 조회 | admin 역할; limit 1~500 | 200 |

`explanation_mode` query는 합성 장애 주입이 명시적으로 켜진 로컬 시험에서만 사용한다.
정상 운영 API의 공개 기능으로 승계하지 않는다.

`api_surface.json`은 위 API 30개와 agent 별칭 경로 6개, gateway 별칭 경로 4개를 합친
40개 라우트 항목을 35개 처리 함수로 고정한다. `api_effects.json`은 같은 35개 처리 함수의
회원·기업 DB, 감사, Redis, 추천 처리, 설명 중계와 입력 기록 효과를 기록하고 도우미 20개와 선택 순서
9개를 지문으로 대조한다. 두 계약은 `AST_PARTIAL` 소스 목록이다. 실행 분기의 지배 관계,
효과 발생 횟수, 트랜잭션 원자성, 실제 후속 서비스 수신이나 versioned OpenAPI 전체를
검증한 결과가 아니다.

기업 `status`는 모델 기본값 `approved`로 생성된다. 별도 검토 전환이나 상태 변경 API가 없고,
공개 공고 목록·상세, 신규 지원·지원 현황, 지원자 추천과 기업 overview·pipeline·추천에서 이를
권한 gate로 쓰지 않는다. `status` 문자열이 있다는 사실을 기업 심사·승인 절차 구현으로 읽지 않는다.

### 4.3 내부 AI 요청 주소

| Method | Path | 요청·응답 책임 | 현재 보호 상태 | 상태 |
|---|---|---|---|---|
| GET | `/agent/health`, `/health` | matcher와 산식 version 표시 | 로컬 loopback/Compose network | `LOCAL_SYNTHETIC_IMPLEMENTED` |
| POST | `/agent/internal/match/candidates`, `/internal/match/candidates` | 한 공고에 대한 후보 점수·정렬·상위 limit | service-to-service 인증 없음 | `LOCAL_SYNTHETIC_IMPLEMENTED` |
| POST | `/agent/internal/match/jobs`, `/internal/match/jobs` | 한 후보에 대한 공고 점수·정렬·상위 limit | service-to-service 인증 없음 | `LOCAL_SYNTHETIC_IMPLEMENTED` |
| GET | `/llm/health`, `/health` | provider, contract version, 실호출 잠금 상태 | 로컬 loopback/Compose network | `LOCAL_SYNTHETIC_IMPLEMENTED` |
| POST | `/llm/internal/explanations`, `/internal/explanations` | 확정 score를 바꾸지 않는 설명, prompt metadata, alignment | service-to-service 인증 없음; 합성 장애 주입은 기본 비활성 | `LOCAL_SYNTHETIC_IMPLEMENTED` |

`agent`와 `llm-gateway`는 DB DSN을 받지 않는다. DB 조회와 tenant 범위 조합은 `api`가
수행한다. 내부 endpoint에 애플리케이션 인증이 없으므로 loopback 밖이나 LAN, ALB에 그대로
노출하면 안 된다. 기준 Terraform은 `/agent/*`, `/llm/*`를 공개 ALB rule에 연결하므로,
AWS 전환 전 공개 경로 제거 또는 별도 인증·network policy 결정이 필요하다.

### 4.4 별도 Bedrock 실험용 API

별도 브랜치의 실험은 기존 `llm-gateway`와 결합되지 않은 독립 adapter다.

| Method | Path | 입력·출력 | 인증 | 상태 |
|---|---|---|---|---|
| GET | `/health` | provider와 RAG 비활성 상태 | API Gateway `NONE` | `BRANCH_PROTOTYPE_UNDEPLOYED` |
| POST | `/v1/explanations` | score와 이미 선택된 일치 label을 받아 짧은 설명 반환 | API Gateway `AWS_IAM` | `BRANCH_PROTOTYPE_UNDEPLOYED` |

이 adapter는 `candidate_context`를 거부하고 가명 subject reference, 내부 feature ID, 원문
개인정보를 모델 prompt에 넣지 않도록 작성됐다. Guardrail 개입은 422, 형식이 잘못된 모델
응답은 502, throttling은 provider detail을 숨긴 429로 매핑한다. 단위시험의 mock 통과는
실제 Bedrock 호출, 요청별 실제 destination, 과금 한도, 모델 품질 또는 운영 통제의 검증이
아니다. 템플릿은 APAC cross-Region profile과 서울을 포함한 여섯 destination model ARN을
선언하므로 서울 리전 안에서만 처리된다고 가정할 수 없다. RAG,
Knowledge Bases, embedding model, vector DB는 이 실험에 없다.

### 4.5 컨설턴트 대시보드 미리보기 API

아래 네 경로는 client AWS가 아니라 컨설턴트 소유 shared preview backend의 계약이다.
저장소상 배포 기록은 있으나 이번 작업에서 원격 endpoint와 현재 리소스를 재확인하지 않았다.

| Method | Path | 요청·응답 | 보호와 제한 | 정상·주요 오류 |
|---|---|---|---|---|
| POST | `/session` | `nickname`, shared passcode를 받아 HMAC bearer token·만료 시각·정규화 nickname 반환 | passcode hash는 SSM SecureString, session 8시간, source-address hash별 15분 8회 실패 제한 | 200; 인증·rate-limit 오류 |
| GET | `/workspace` | shared workspace, version, 수정 시각·nickname 반환 | bearer token; tenant별 workspace가 아닌 단일 공유 영역 | 200 |
| PUT | `/workspace` | workspace와 `expectedVersion`을 받아 조건부 저장 | bearer token, 직렬화 크기 350 KiB 제한 | 200; stale version은 409 `VERSION_CONFLICT`와 최신본 반환 |
| GET | `/activity` | 최신 activity event 최대 100건 반환 | bearer token; 성공 session·save 중심이며 immutable audit trail 아님 | 200 |

nickname은 자기 선언 attribution이며 사용자 identity나 권한 경계가 아니다. shared passcode를
아는 사용자는 workspace 전체를 읽고 바꿀 수 있다. 따라서 이 API를 운영용 per-user auth,
tenant isolation, audit logs, approved snapshot ingestion 구현으로 간주하지 않는다.

### 4.6 아직 규칙을 정하지 못한 API

- snapshot export, redaction approval, 운영용 approved ingestion API
- dashboard per-user auth, tenant scope, audit export API
- 외부 공급자와 기존 gateway 사이의 승인된 request/response schema
- GitHub/Kakao/Mailpit adapter API
- idempotency key, 공통 error envelope, pagination, retry budget 계약
- 추천 실행 감사 이벤트와 저장면별 파기 orchestration API

### 4.7 모든 API에 필요한 보안 규칙

로컬 소스에는 bearer token, 역할 dependency, candidate 본인 범위, recruiter company 범위,
Pydantic schema validation과 일반 감사 기록이 있다. 이는 합성 재현용 구현이며 운영 수준의
per-user auth·tenant isolation을 충족한다고 판정하지 않는다. 다음은 운영 전 별도 결정과
검증이 필요하다.

- session 서명키 생성·회전·보관, token 수명과 강제 로그아웃
- 모든 tenant 객체의 object-level authorization 회귀시험
- 내부 agent/gateway 호출 인증과 공개 ALB 경로 차단
- audit event의 actor, tenant, target reference, purpose, result, correlation ID 완전성
- 민감 원문을 포함하지 않는 error·application log·audit detail
- rate limit, timeout, retry, circuit state와 idempotency 계약
- dashboard의 per-user auth, tenant isolation, audit logs, approved snapshot ingestion

## 5. 데이터 및 이벤트 명세

> 이 장은 데이터가 **어디서 들어와 어디로 이동하고, 어디에 남는지** 순서대로 설명한다.
> 실선은 Terraform에서 확인한 관계다. 점선은 계획, 로컬 예시 또는 아직 확인하지 못한
> 연결이다.

### 5.1 다루는 데이터와 저장 위치

| 객체 | 내용 | 로컬 저장 위치 | 구현 상태 |
|---|---|---|---|
| User | 계정, role, company 논리 참조, 활성 상태 | 회원 논리 DB | `LOCAL_SYNTHETIC_IMPLEMENTED` |
| ConsentEvent | grant/revoke, policy version, items, purpose, occurred_at | 회원 논리 DB | `LOCAL_SYNTHETIC_IMPLEMENTED` |
| Resume | 구조화 항목과 자유서술 | 회원 논리 DB | `LOCAL_SYNTHETIC_IMPLEMENTED`; S3 원본 연계 없음 |
| CompanyProfile | 기업 방향, 선언 가치, profile version | 기업 논리 DB의 Company 필드 | `LOCAL_SYNTHETIC_IMPLEMENTED` |
| OpenDARTSnapshot | 정식 회사명, 시장·업종, 설립일, 최근 공시, 조회 시각과 내용 hash | 기업 논리 DB의 Company 필드 | 기본 합성 예시 `LOCAL_SYNTHETIC_IMPLEMENTED`; 점수 영향 없음 |
| Job | 공고, 요구 기술, 최소 경력, 상태 | 기업 논리 DB | `LOCAL_SYNTHETIC_IMPLEMENTED` |
| Application | 구직자-공고 논리 참조와 단계 | 회원 논리 DB | `LOCAL_SYNTHETIC_IMPLEMENTED`; cross-DB FK 없음 |
| MatchResult | 결정론적 점수, breakdown, 일치 feature, 설명 | 응답과 Redis 24시간 cache | 전용 영속 모델 `PLANNED_UNIMPLEMENTED` |
| PromptLog | prompt 원문, 전송 field metadata, prompt hash | 로컬 `prompt-logs` volume | `LOCAL_SYNTHETIC_IMPLEMENTED`; 즉시 파기·보존정책 없음 |
| AuditEvent | actor, tenant, target 가명 참조, purpose, result | 회원 논리 DB | 일반 event `LOCAL_SYNTHETIC_IMPLEMENTED`; `match_run` 없음 |
| Snapshot | redacted/approved assessment export | 컨설턴트 서비스 | schema `UNKNOWN` |

기획 P0는 구조화 이력서 form만 포함하고 file upload/parser는 제외한다. Terraform에는
첨부 이력서 원본 S3 버킷이 존재한다. 로컬 런타임은 구조화 form만 저장하고 S3 client가
없으므로 file upload나 S3 업로드가 구현됐다고 표현하지 않는다.

### 5.2 사용자가 서비스에 접속하는 흐름

업무망 PC도 사용자 단말 후보에 포함되지만, 해당 단말이 이 경로를 실제 사용한다는 근거는
없다. 아래 1~4는 Terraform에 표현된 공개 진입 구조이고 단말별 실제 접속 이력은 아니다.

1. 사용자 DNS 요청이 Route 53 alias를 거쳐 CloudFront로 향한다.
2. CloudFront에 연결된 AWS WAF 관리형 규칙이 요청을 평가한다.
3. CloudFront가 HTTPS로 public ALB origin에 전달한다.
4. ALB가 path pattern에 따라 네 target group 중 하나를 선택한다.
5. 기준 ECS task는 이미지가 없어 응답을 검증하지 않았다. 별도 로컬 Compose에서는 같은
   네 서비스 경계를 127.0.0.1에 바인딩해 합성 요청을 처리한다.

1~4는 Terraform `MODELLED`다. 5의 AWS 경로는 `PLANNED_UNIMPLEMENTED`, 로컬 경로는
`LOCAL_SYNTHETIC_IMPLEMENTED`다. 로컬 응답을 CloudFront·WAF·ALB 종단간 검증으로 읽지 않는다.

### 5.3 추천과 AI 설명이 만들어지는 흐름

지원자 경로는 동의와 Resume, 공개 공고·기업 profile을 읽은 뒤 Redis를 확인한다. 기업 경로는
공고 소유 범위를 확인한 직후 Redis를 읽고, miss일 때만 회원 DB에서 활성 지원자와 현재 Resume를
조회한다. 두 경로 모두 miss이면 `agent`가 결정론적 score와 breakdown을 확정한다. `api`는 설명용
candidate context 8개, company context 6개와 score를 `llm-gateway`에 보낸다. gateway handler가
요청 검증을 마치고 진입한 경우에만 field metadata, prompt hash와 raw prompt record가 생긴다.
연결 실패나 handler 전 schema 거부만으로 prompt 기록이 남았다고 볼 수 없다.

정상 응답은 Redis에 24시간 저장한다. 기업 경로의 hit는 회원 DB, 지원자 활성 상태와 현재 공급자를
재확인하지 않고 과거 설명을 반환한다. 응답에는 공급자와 원본 준비 field 집합을 재검증하지 않았다는
상태를 따로 표시한다. 추천 실행 전용 audit event는 남기지 않는다. `web`은 API score breakdown과
설명 상태를 표시하며 점수를 다시 계산하지 않는다.

OpenDART 복사본은 기업 담당자가 별도 요청할 때만 갱신한다. 로컬 기본값은 합성 예시를 바로
읽는다. 선택 설정은 SQS FIFO 요청을 만들고, 별도 Lambda 작업자 소스는 이를 받아 OpenDART를
조회한 뒤 기업 DB의 정상 복사본을 바꾸도록 작성됐다. 그러나 큐·Lambda·키 보관·DB 연결 자원과
배포 묶음은 없고 실제 실행도 확인하지 않았다.
기업 방향 선언을 덮어쓰지 않고 추천 입력·점수·정렬에도 넣지 않는다. MLOps에서는 합성 기업
방향과 자소서의 단어 겹침을 다섯 숫자 특징 중 두 개로 만들 수 있지만, 현재 `agent`의 70·20·10
결과를 교체하거나 서비스 요청 경로에 참여하지 않는다.

이 흐름은 별도 로컬 합성 소스의 계약이다. 실제 공급자 호출은 기본 잠금 상태이며 실행하지 않았다.
Terraform이 확인하는 것은 NAT/IGW egress, unrestricted ECS egress, task와 log group 경계다.
별도 관리형 Bedrock 실험의 API Gateway/Lambda/Guardrail 경로는 이 흐름과 통합되지 않았다.

### 5.3.1 MLOps 학습·평가 데이터 흐름

전체 인프라 도면은 MLOps를 기준 110개 AWS 설계와 분리된 왼쪽→오른쪽 경로로 보여 주고,
MLOps 전용 페이지는 같은 자료 이동을 일곱 단계로 설명한다.

1. 별도 EC2 랩 안의 exporter가 합성 회원 DB와 합성 기업 DB를 읽는다.
2. 원문을 기술·경력·직무, 자소서와 공고의 단어 겹침, 기업 방향과 공고의 단어 겹침까지 다섯 숫자 특징으로 줄인다.
3. 원문 없는 feature CSV 1개, manifest와 source receipt JSON 각 1개를 `mlops/sources/{run_id}/`에 둔다.
4. 담당자가 확인값과 실행 정보를 넣어 일회성 Lambda를 직접 시작한다.
5. Lambda가 필수 세 파일의 존재·크기·허용 항목과 파일 사이 해시를 확인한 뒤 후보 모델을 학습한다.
6. 입력 특징 복사본 3개와 결과 3개, 합계 6개를 `mlops/runs/{run_id}/`에 저장하고 DynamoDB에 실행 상태, CloudWatch Logs에 실행 로그를 남긴다.
7. 상태를 `TRAINED_PENDING_HUMAN_REVIEW`로 끝내고 사람의 결정을 기다린다.

Lambda는 DB URL이나 비밀번호를 받지 않고 VPC에 붙지 않는다. 이름·이메일·전화·자소서와 기업·공고
원문은 S3 학습 파일과 모델 산출물에 보관하지 않도록 작성됐다. 다만 합성 표식 검사는 운영 자료
차단을 보장하는 인증 장치가 아니므로 실제 회원 자료에는 사용하지 않는다.

실행 상태를 처음 쓰기 전의 입력 거부나 상태 저장 실패는 `FAILED_SAFE` 기록 없이 끝날 수 있다.
`RUNNING`이 기록된 뒤의 파일 검사·학습·저장 오류만 안전 실패 상태 전이를 시도한다. 결과는
Bedrock 설명 계층과 현재 `agent`의 70·20·10 점수·정렬에 연결하지 않으며 자동 일정, 모델 승격,
제한 배포와 되돌리기는 이 경로에 없다.

### 5.4 데이터 저장과 로그 흐름

| 생산자 | 데이터 | 목적지 | 모델 상태 |
|---|---|---|---|
| ALB | access log | 전용 S3 bucket, 90일 lifecycle | `MODELLED` |
| CloudTrail | 관리 event | 전용 S3 bucket | `MODELLED` |
| VPC | ALL flow record | CloudWatch log group, 30일 | `MODELLED` |
| CloudFront | access log | 목적지 없음 | `PLANNED_UNIMPLEMENTED`; `logging_config` 미선언 |
| AWS WAF | sampled request/log | log 목적지 없음 | metric·sample은 `MODELLED`, logging configuration 미선언 |
| ECS web/api/agent | awslogs | access log group, 365일 | log driver만 `MODELLED` |
| ECS llm-gateway | awslogs | prompt-raw log group, retention 미설정 | log driver만 `MODELLED` |
| Application | resume 원본 | resume S3 bucket | IAM과 bucket만 `MODELLED`, 호출 코드 없음 |
| 로컬 API | User·Consent·Resume·Application·AuditEvent | PostgreSQL 회원 논리 DB | `LOCAL_SYNTHETIC_IMPLEMENTED` |
| 로컬 API | Company·Job·기업 profile | PostgreSQL 기업 논리 DB | `LOCAL_SYNTHETIC_IMPLEMENTED` |
| 로컬 API | 추천 응답 | Redis 24시간 cache | `LOCAL_SYNTHETIC_IMPLEMENTED`; 공고 version 무효화 없음 |
| 로컬 llm-gateway | raw prompt와 metadata | `prompt-logs` volume | `LOCAL_SYNTHETIC_IMPLEMENTED`; 운영 저장소 아님 |
| AWS Application | 추천 cache | ElastiCache | network/data `MODELLED`; ECS client wiring 미완료 |
| MLOps exporter | 가명 참조와 숫자 특징 5개, manifest, source receipt | 별도 MLOps S3의 `mlops/sources/{run_id}/` | `MLOPS_PLANNED_NOT_DEPLOYED`; 합성 DB 옆에서 원문을 줄인 뒤 업로드하도록 작성 |
| MLOps Lambda | 입력 3개와 후보 모델·비교 결과·실행 receipt | 같은 S3의 `mlops/runs/{run_id}/` | `MLOPS_PLANNED_NOT_DEPLOYED`; 실행별 파일 6개, 기본 7일 만료 계획 |
| MLOps Lambda | `RUNNING`, `TRAINED_PENDING_HUMAN_REVIEW`, `FAILED_SAFE` | DynamoDB 실행 상태표 | `MLOPS_PLANNED_NOT_DEPLOYED`; 중복 실행 번호 덮어쓰기 차단, TTL·시점 복구 없음 |
| MLOps Lambda | 실행 상태용 로그 | CloudWatch Logs | `MLOPS_PLANNED_NOT_DEPLOYED`; 기본 7일 보존 계획 |

### 5.5 로컬 예시에서 남기는 작업 기록

로컬 API가 회원 논리 DB의 `AuditEvent`에 쓰는 event type은 다음과 같다. 이 테이블의
감사는 애플리케이션 레코드이며 AWS CloudTrail이나 변경 불가능한 감사 원장과 같지 않다.

| Event type | 발생 조건 | 현재 한계 |
|---|---|---|
| `runtime_seed` | 합성 seed 초기화 | 개발용 자동 seed와 결합 |
| `signup`, `recruiter_signup`, `login` | 역할별 가입·로그인 | 인증 수명주기 전체 event가 아님 |
| `consent_grant`, `consent_revoke` | 동의 부여·철회 | 별도 AI 추천 동의 유형 없음 |
| `resume_saved`, `application_submitted` | 이력서 저장·지원 | S3 원본·cross-DB outbox 없음 |
| `job_created`, `job_updated` | 기업 공고 생성·변경 | 추천 cache 무효화 event 없음 |
| `company_matching_profile_updated` | 기업 방향 profile version 저장 | 점수 가중치 승인 event가 아님 |
| `company_opendart_refresh` | 공개정보 복사본 갱신 성공 또는 실패 | 외부 원문 전체나 API 키를 기록하지 않으며 기업 인증 완료 event가 아님 |
| `recruiter_overview_viewed`, `candidate_view` | 기업 overview·pipeline 후보 조회 | 조회량 제어·export event 미정의 |
| `application_status_changed` | 기업 담당자의 지원 단계 변경 | 채용 결정의 적정성을 뜻하지 않음 |
| `withdrawal` | 후보자 탈퇴 접수 | Redis·prompt log·backup 파기 완료 event 아님 |
| `authorization_denied` | 역할 또는 기업 범위 위반 거부 | 중앙 탐지·경보와 연결되지 않음 |
| `audit_log_viewed` | 운영자의 감사 조회 | immutable export와 보존 계약 없음 |

추천 실행, matcher 결과, 설명 provider 호출을 나타내는 `match_run` event는 없다. cross-DB
변경과 감사 기록을 묶는 outbox, 멱등 operation ID, 중앙 수집, 보존·삭제 정책도 구현되지
않았다.

### 5.6 회원 탈퇴와 데이터 삭제 흐름

로컬 탈퇴 요청은 계정을 비활성화하고 주 DB의 이력서·지원 관계를 제거하며 기존 token을
무효화한다. 합성 canary 관찰에서는 직전에 생성한 Redis 추천 cache와 raw prompt record가
즉시 남았다. MatchResult, S3 version, RDS backup까지 다루는 deletion orchestrator와 전파
event는 없다. 따라서 전 저장면 완전 삭제나 법적 파기 완료를 주장하지 않는다.

### 5.7 검토용 복사본과 대시보드 흐름

1. client AWS나 로컬 증적에서 별도 export 절차가 snapshot을 만든다고 가정한다.
2. 외부 미리보기용 snapshot은 승인된 redaction과 최소 field projection을 통과해야 한다.
3. 운영용 snapshot은 tenant와 승인 metadata, source hash와 schema version을 가져야 한다.
4. 대시보드는 승인 진위를 확인한 snapshot만 ingestion한다.
5. per-user auth와 서버 측 tenant isolation으로 조회 범위를 제한한다.
6. ingestion, 조회, 변경과 export 이벤트를 보호된 audit log에 남긴다.

1~6은 운영 요건이다. AIMS Desk preview는 빌드 시 기술 결과를 `preview-redacted` 집계로 축약하고,
사용자가 가져온 YAML/JSON 검토 초안을 shared backend에 저장한다. 별도 로컬 Evidence Desk는
`INTERNAL_REVIEW` 비식별 JSON 한 개를 브라우저 메모리에서만 읽는다. 네트워크와 browser
persistence를 막고 `EXTERNAL_PREVIEW` 입력을 거부한다. 같은 파일 안의 `tenant_ref` 일치와 논리
참조를 검사하지만 서명, 승인자 identity, 서버 partition이나 객체 인가를 확인하지 않는다.

두 구현 모두 승인 진위, 운영 tenant binding과 per-user identity를 검증하는 전체 pipeline은
구현하지 않았다. client AWS credential, cross-account role과 직접 API 연결은 현재 코드 경로에
없다.

### 5.8 데이터가 넘어갈 때 확인해야 할 경계

| ID | 경계 | 확인 대상 | 상태 |
|---|---|---|---|
| TB-00 | 업무망 단말 → 공개 진입점 | DNS, proxy, VPN, IdP, 단말 보안 기준 | 단말 수량만 `USER_CONFIRMED`, 연결은 `UNKNOWN` |
| TB-01 | Internet → edge | TLS, WAF, rate limit, session cookie | TLS/WAF 일부만 `MODELLED` |
| TB-02 | API authentication/authorization | object scope와 tenant isolation | 로컬 역할·company 검사 구현; 운영 검증 `UNKNOWN` |
| TB-03 | structured data → prompt | 포함 field, masking, 목적 최소화 | 로컬 context 14개(candidate 8, company 6) 전달·candidate 필드명 6개를 PII 후보로 기록; masking 미구현 |
| TB-04 | llm-gateway → provider | 전송 field, provider, 처리 위치, response validation | 합성 stub 구현; 두 APAC 교차 리전 profile 선언 확인. 실제 호출·요청별 destination·승인은 `UNKNOWN` |
| TB-05 | application → stores | cross-DB 쓰기, cache 무효화, 삭제 전파, backup | 로컬 일부 구현; 전체 전파 `PLANNED_UNIMPLEMENTED` |
| TB-06 | AI response → React DOM | schema, escaping, PII, URL handling | 로컬 schema/renderer 존재; 의미 검증 미구현 |
| TB-07 | application → optional providers | GitHub/Kakao/Mailpit 경계 | P1 `PLANNED_UNIMPLEMENTED` |
| TB-08 | evidence export → consultant dashboard | redaction, approval, tenant binding | redacted preview bundle·shared workspace 구현; approved tenant ingestion은 `GATED` |
| TB-09 | 기준 Terraform → 별도 Bedrock 실험 | IAM, API contract, failure semantics, 승인 | 통합되지 않은 `BRANCH_PROTOTYPE_UNDEPLOYED` |
| TB-10 | 로컬 API → OpenDART | API 키, 기업명 일치, 최소 필드, 오류·속도 제한, 복사본 출처 시각 | 합성 예시와 소스 계약만 확인. 외부 호출·운영 키·AWS 경로는 미확인 |
| TB-11 | 합성 DB exporter → MLOps S3 입력 | 합성 표식, 허용 특징 5개, 원문 제거, 파일 해시와 보존기간 | 소스·단위시험 확인. 출처를 독립 증명하는 서명과 AWS 실행은 미확인 |
| TB-12 | MLOps 결과 → 향후 추천 런타임 | 모델 승인, 버전 결속, 그림자 비교, 되돌리기 | 사람 검토 대기에서 멈춤. 현재 추천 연결·자동 승격 없음 |
| TB-13 | 업무망 단말 → Slack 외부 SaaS | workspace 소유·사용, 계정, 개인정보 입력, 보존·삭제, 연동 | 두 OS 이미지의 바로가기 소스와 macOS best-effort 종료만 확인. 실제 운영은 `SCENARIO_USE_UNVERIFIED`; AWS 흐름선·webhook/token·Amazon Q Developer(AWS Chatbot)·SNS·EventBridge 없음 |

## 6. 보안 및 운영 명세

> 이 장은 현재 설계에 적혀 있는 보호 장치와 빠진 장치를 나누어 설명한다. 보안 서비스
> 이름이 있다고 해서 실제 대응 체계나 보안 효과까지 확인됐다는 뜻은 아니다.

### 6.1 Terraform 설계에서 확인한 보호 설정

여기에는 존재 여부와 설정값만 기록했다. 통제 판정은 하지 않는다.

- CloudFront viewer와 ALB listener에 TLS 설정이 있다.
- AWS WAF에는 Common과 SQLi 관리형 규칙 그룹 두 개가 있다.
- ALB는 443만 공개 ingress로 모델링되어 있다.
- ECS task는 public IP를 받지 않고 App subnet 두 개에 배치된다.
- Data subnet에는 인터넷 기본 경로가 없다.
- RDS는 public access가 비활성이고 저장 암호화가 켜져 있다.
- ElastiCache는 전송 암호화와 저장 암호화 플래그가 모두 `false`로 모델링되어 있다.
- Resume S3에는 SSE-S3, versioning, public access block이 있다.
- 운영 shell 경로는 SSM 계열 endpoint와 ECS Exec 설정으로 모델링되어 있다.
- VPC Flow Logs, CloudTrail, GuardDuty가 선언되어 있다.

### 6.2 로컬 예시 코드에서 확인한 보안 상태

아래는 코드와 기록된 합성 시험의 관찰값이다. 운영 통제의 적합성 판정이 아니다.

- API는 bearer token, 역할 dependency, candidate 본인 범위와 recruiter company 범위를 검사한다.
- `Company.status`는 기본 `approved`지만 상태 전환 API와 업무 gate가 없다. 공개·지원자·기업
  주요 경로가 이 값을 확인하지 않는 상태를 기업 승인 절차로 포장하지 않는다.
- 핵심 동의 전 이력서 저장·추천 요청과 동의 철회 후 추천 요청을 거부한다.
- 기업 간 공고·지원 객체의 조회와 변경을 서버 측에서 거부하는 시험 기록이 있다.
- 일반 서비스 로그에서 bearer header와 합성 credential 문자열을 찾지 못한 기록이 있다.
- 호스트 포트는 127.0.0.1에만 바인딩한다.
- `agent`와 `llm-gateway` 내부 API에는 service-to-service 인증이 없다.
- API 프로세스는 회원·기업 두 DSN을 모두 가지며 교차 DB write는 단일 transaction이 아니다.
- ECS 변경 계약은 DB DSN과 LLM API key를 일반 task environment로 전달하며 별도 secret
  store 참조를 사용하지 않는다.
- raw prompt volume에는 설명 context가 남고, Redis 24시간 cache와 함께 탈퇴 즉시 삭제되지 않는다.
- 기업 추천 cache hit는 회원 DB와 현재 공급자를 재확인하지 않는다. 과거 설명과 후보자 payload가
  반환될 수 있다는 경계를 응답 상태로 드러내지만 자동 무효화나 즉시 파기는 구현하지 않았다.
- OpenDART 보조 기능은 recruiter 역할과 자기 기업 범위를 검사하고 공개용 응답에서 기업 고유번호와
  연락처·법인번호·사업자번호 같은 필드를 제외한다. 외부 조회 키 주입·회전과 실제 통신은 검증하지 않았다.
- 생성 문장의 grounding, 금칙 결론 차단, `match_run` audit event는 구현되지 않았다.
- MLOps의 DB 직접 실행 경로는 합성 전용 표식과 예약된 연락처 형식을 검사한다. 이는 기업 원문을
  포함한 자료 출처를 독립적으로 증명하는 인증이나 서명은 아니다.
- 서버리스 기본 경로는 DB URL·비밀번호·VPC 연결 없이 S3의 실행별 prefix 아래 필수 입력 파일
  세 개만 읽는다. 필수 파일이 없거나 경로·크기·허용 특징·파일 사이 해시가 맞지 않으면 거부한다.
  같은 prefix의 여분 객체를 따로 열거해 거부하는 검사는 없다.
- Terraform 소스는 private·versioned S3와 SSE-S3, 기본 7일 만료, immutable·scan-on-push ECR와
  최근 이미지 5개 보존, 암호화 DynamoDB, 기본 7일 CloudWatch Logs, 경로·표 범위 IAM을 선언한다.
  DynamoDB의 TTL과 시점 복구는 켜지 않았고 별도 KMS 키도 연결하지 않았다.
- `runtime` 단계는 같은 전용 ECR의 내용 지문으로 고정한 Lambda 이미지만 허용하고 동시 실행을
  1로 제한한다. 정확한 확인값도 요구하지만 이 값은 인증이나 조직 승인 증거가 아니다.
- MLOps 결과는 `TRAINED_PENDING_HUMAN_REVIEW`에서 멈춘다. 모델 보관소, 서명된 승인 기록,
  서비스 버전 결속, 그림자 비교와 되돌리기 기록은 아직 정의되지 않았다.
- 완전 생성형 로컬 출력은 별도 암호화·접근통제·보존 설정이 없고 명시적 `--overwrite`를 쓰면
  기존 파일을 바꿀 수 있다. 서버리스 경로의 S3 실행 번호 중복 방지는 이 로컬 동작과 구분한다.
- 실행 중 gateway 컨테이너와 최신 소스 해시가 달라 최신 이미지의 보안 회귀시험 완료를 주장하지 않는다.
- 공개 릴리스 검사는 Lab·MLOps·OpenDART의 정적 검사 3개와 단위시험 묶음 3개를 차례로 실행한다.
  단위시험 건수와 검사 단계 수는 서로 다른 숫자이며, 둘 다 실행 보안시험이나 통제 효과 판정을 뜻하지 않는다.

### 6.3 기존 모습을 보존하려고 추가하지 않은 구성

AS-IS 재현을 유지하려고 아래 리소스를 만들지 않았다. 근거 위치를 항목별로 분리해,
absence manifest가 다루지 않는 항목까지 같은 파일의 주장으로 묶지 않는다.

| 미선언 항목 | 식별자 | 직접 확인 위치 |
|---|---|---|
| AWS Config recorder/delivery channel | `GAP-CFG-01` | `terraform/asis/ABSENCE_MANIFEST.md`, `security/iam.tf` |
| Secrets Manager secret/version | `GAP-SEC-01` | `terraform/asis/ABSENCE_MANIFEST.md`, `security/iam.tf` |
| 고객 관리형 KMS key | `GAP-KMS-01` | `terraform/asis/ABSENCE_MANIFEST.md`, `security/iam.tf` |
| AWS Network Firewall·Route 53 Resolver DNS Firewall | `GAP-EGRESS-01` | `terraform/asis/ABSENCE_MANIFEST.md`, `security/endpoints.tf` |
| WAF custom regex/free-text rule | `GAP-WAF-01` | `terraform/asis/ABSENCE_MANIFEST.md`, `edge/main.tf` |
| CloudTrail S3 data event selector | `GAP-TRAIL-01` | `terraform/asis/observability/main.tf` |
| resume bucket noncurrent version lifecycle | `GAP-S3-01` | `terraform/asis/data/s3_resume.tf` |
| CloudFront access logging | 지정 GAP ID 없음 | `terraform/asis/edge/main.tf`의 `logging_config` 미선언 주석 |
| AWS WAF logging destination | 지정 GAP ID 없음 | `terraform/asis/edge/main.tf`의 logging configuration 미선언 주석 |

이 문서에서는 해당 부재를 적합성 또는 부적합성 결과로 변환하지 않는다.

### 6.4 비밀번호·키·계정 식별자 처리

- 문서와 도면에는 account ID, access key, secret key, database password, API key 값을
  싣지 않는다.
- Terraform의 sensitive variable은 mock plan 성립을 위한 합성값이다.
- 실제 운영 credential을 이 재현 모델에 넣지 않는다.
- 대시보드 snapshot에는 credential, ARN 속 account ID, 원본 사용자 식별자를 제거하거나
  승인된 token으로 치환해야 한다.

### 6.5 이 문서로 확인할 수 없는 운영 절차

허용되는 검증은 format, init with backend disabled, validate, refresh 없는 mock plan,
정적 계약 검사, 문서/도면 검증뿐이다. `terraform apply`, AWS API를 통한 변경, 배포
workflow 생성은 금지된다.

Plan 결과로 모델의 선언 구조는 확인할 수 있다. 아래 항목은 확인할 수 없다.

- AWS quota와 실제 service availability
- 인증서 발급과 DNS 위임
- 기준 ECR image pull, ECS process boot, AWS health endpoint
- 기업 DB bootstrap, schema migration, Redis·agent·gateway service discovery
- 실제 공급자 연결, APAC profile 안의 요청별 destination과 처리 계약 승인
- failover 시간, recovery point, recovery time
- 사용자의 end-to-end 업무 흐름

MLOps 전용 실행 도구도 계획을 기본 동작으로 둔다. 별도 승인을 받은 작업자가 배포·호출 옵션을
직접 켤 때만 다음 단계로 가도록 작성됐으며, 저장한 Terraform 계획에서 삭제·교체가 보이면 중단한다.
EC2 랩의 여섯 서비스 원격 점검을 먼저 통과해야 하고, 현재 보호된 CI는 이 전용 루트를 배포하지
않는다. 이 절차의 소스가 있다는 사실은 AWS 배포나 원격 점검을 마쳤다는 증거가 아니다.

### 6.6 대시보드를 운영하기 전에 필요한 조건

저장소가 배포본으로 기록한 현재 구성은 팀 preview다. 이를 운영 배치로 승격할 때의 선행
조건은 아래와 같다. 적합성이나 인증 충족 여부는 판정하지 않는다.

- 사용자별 인증과 session 관리
- tenant별 저장, query, cache, export 격리
- snapshot 생성자와 승인자 분리 또는 이에 준하는 승인 이력
- schema/version, redaction, approval, source classification fail-closed 검사
- ingestion, 조회, 변경, export audit log
- 외부 미리보기의 redacted snapshot 전용 경로
- client AWS 직접 연결 기능의 부재를 regression으로 확인
- snapshot 삭제와 보존 정책

| 경계 | 현재 preview 관찰 | 운영 전 필요한 상태 |
|---|---|---|
| 사용자 | shared passcode, 자기 선언 nickname, 전체 session 일괄 회전 | per-user identity, 개인 revoke, 역할별 권한 |
| tenant | 하나의 shared workspace key | tenant별 저장·query·cache·export 격리 |
| 감사 | 성공 session 생성과 workspace 저장 중심 activity record | ingestion·조회·변경·export를 포함한 보호된 audit log |
| snapshot 승인 | 브라우저가 구조와 선언 metadata를 검사하나 승인 진위·정본 hash를 증명하지 못함 | 승인자·source hash·tenant binding을 검증하는 ingestion gate |
| 외부 번들 | `preview-redacted` 집계 mode와 상세 finding 제외 | redaction 회귀검사와 승인된 snapshot만 게시 |
| client AWS | credential 입력·cross-account 조회 경로 없음 | 직접 연결 기능 부재를 계속 회귀검사 |

### 6.7 검증되지 않은 ISO 엑셀 템플릿 취급 규칙

70행이라고 전달된 ISO XLSX는 원본을 직접 열람하거나 행수를 재계수하지 못한 검증 전
템플릿으로 취급한다. 따라서 70은 검증된 계수 결과가 아니다.

- 다른 조직의 판정과 evidence를 J-Career 상태로 상속하지 않는다.
- 번역된 표준 문구를 출판 가능한 문구로 취급하지 않는다.
- 각 행의 상태는 사람 검토 전 `pending_human_review`를 유지한다.
- dashboard snapshot이 workbook 행을 담더라도 원본 조직, 근거 출처, 검증 상태를
  분리한다.
- 이 자료만으로 적합성, 인증 가능성, 충족 여부를 단정하지 않는다.

## 7. 운영 및 장애 시나리오

> 이 장은 문제가 생겼을 때 보이는 현상, 현재 설계가 할 수 있는 대응, 사람이 추가로
> 확인할 일을 적는다. 실제 장애 시험을 끝냈다는 기록은 아니다.

### 7.1 사용자가 접속하지 못하는 경우

| 시나리오 | 관찰 지점 | 현재 모델의 예상 구조 | 확인되지 않은 것 |
|---|---|---|---|
| Route 53/DNS 실패 | DNS resolution | alias가 CloudFront를 가리킴 | 실제 위임, health routing |
| CloudFront origin 실패 | distribution/origin metric | ALB HTTPS origin | custom error, retry 정책 |
| WAF 차단/오탐 | WAF metric/sample | 관리형 두 그룹 metric 활성, WAF logging destination 미선언 | 상세 request log와 운영 대응 |
| ALB target unhealthy | target health | 30초 interval, 5초 timeout, 2회 threshold | 앱 health handler와 복구 동작 |
| ECS task 종료 | ECS service | desired count 2, deployment 100/200 | 이미지 boot와 state handling |
| 단일 AZ App 장애 | ECS scheduler/subnet | 두 App subnet이 서비스에 전달됨 | 명시적 placement와 실측 복구 시간 |
| 로컬 Nginx upstream 변경 | Compose DNS | 과거 container IP 고정 문제를 Docker DNS 재해석으로 수정한 기록 | 최신 소스 이미지 전체 재시험 |

### 7.2 데이터베이스나 캐시에 문제가 생긴 경우

| 시나리오 | 모델 요소 | 기대되는 검토 포인트 | 미구현/미확인 |
|---|---|---|---|
| RDS Primary 장애 | Multi-AZ primary | endpoint 전환과 client reconnect | failover 시험 이력, retry 정책 |
| Read replica 지연 | same-region replica | BI 및 read path의 stale data 처리 | 연결 consumer와 lag threshold |
| Redis node 장애 | AWS 2-node/failover `ASSUMED`; 로컬 Redis 1 container | 로컬은 cache miss 후 recompute, 설명 경로 유지 기록 | AWS failover와 ECS client reconnect |
| Redis stale cache | 로컬 TTL 24시간 | 공고 추가가 기존 cache에 TTL 동안 반영되지 않을 수 있음 | catalog version 기반 무효화 |
| 기업 추천 stale cache | 기업 key에 지원자 집합·이력서 version 없음 | hit가 회원 DB 조회보다 먼저라 탈퇴·비활성·이력서 변경 전 payload가 남을 수 있음 | 지원자 집합/version 결속, revoke·withdrawal 무효화 |
| 두 논리 DB 중 한 write 실패 | 같은 PostgreSQL의 별도 DB | 기업 가입·기업 변경 감사가 부분 완료될 수 있음 | operation ID, outbox, 멱등 복구 |
| Resume object delete | versioning enabled | current와 noncurrent version 범위 | deletion orchestrator |
| RDS backup에 식별정보 잔존 | backup retention 7일 | backup 경계의 파기 절차 | restore/delete procedure |
| S3 policy 불일치 | ALB/CloudTrail bucket policy | log delivery error | alert와 runbook |

### 7.3 외부 AI 연결에 문제가 생긴 경우

| 시나리오 | 모델 요소 | 요구되는 동작 | 현재 상태 |
|---|---|---|---|
| NAT Gateway 단일 AZ 장애 | AZ별 NAT 2개 | App subnet이 같은 AZ NAT를 사용 | 실제 route failover 시험 없음 |
| 설명 경로 timeout·429·503 | 로컬 gateway/API | 점수·정렬 유지, 설명만 사용할 수 없음, 장애 응답 cache 미저장 | legacy 상태만으로 외부 provider 장애를 식별할 수 없음 |
| 설명 provider malformed 응답 | 로컬 gateway/API | 점수 breakdown 유지, 설명 상태 격리 | 생성 문장 의미 grounding 미구현 |
| 장애 중 cache hit | Redis/API | 과거 설명을 반환하고 현재 공급자 미재검증 상태를 표시 | 과거 설명을 계속 노출할지 사람 결정 필요 |
| matcher 중단 | 로컬 agent/API | 공고 조회는 유지, cache miss 추천은 503 | 다중 replica·AWS 복구 미검증 |
| 기존 gateway의 Bedrock 선택 | 내부 adapter와 실호출 잠금 | 기본 합성 stub 유지, 권한 없이는 호출 금지 | Nova Lite APAC 교차 리전 profile의 destination·호출량 승인 없음 |
| 별도 Bedrock 실험 실패 | Lambda adapter 단위시험 | guardrail 422, malformed 502, throttling 429 계약 | 기준 API와 미통합, 실제 호출 미검증 |
| OpenDART 입력 오류·기업명 불일치 | 로컬 API | 요청을 거부하고 이전 정상 복사본이 있으면 보존 | 외부 조회 실행·최신성·기업 인증을 증명하지 않음 |
| OpenDART 응답 없음·속도 제한·형식 오류 | 로컬 adapter | 오류 범주만 노출하고 비밀값·원문 오류를 반환하지 않음 | 재시도·운영 SLA·키 회전은 미확인 |
| OpenDART 큐 설정 없음·등록 실패 | 선택적인 큐 요청 코드 | 503으로 중단하고 이전 정상 복사본이 있으면 유지 | 작업자 소스는 있으나 큐·Lambda·배포 자원은 없음 |
| OpenDART 작업자의 오래된 요청·기업명 불일치 | 미배포 Lambda 소스 | 마지막 정상 복사본을 덮어쓰지 않고 실패를 반환하도록 작성 | 실제 SQS 재시도·부분 실패·DB 권한·동시성은 미검증 |
| GitHub 429/장애 | P1 계획 | cache/fixture/manual URL fallback 계획 | `PLANNED_UNIMPLEMENTED` |
| Kakao script 장애 | P1 계획 | free-text address fallback 계획 | `PLANNED_UNIMPLEMENTED` |
| Mailpit 장애 | P1 계획 | in-app notification 독립 계획 | `PLANNED_UNIMPLEMENTED` |

로컬 합성 장애 동작과 AWS 운영 장애 동작을 구분한다. 로컬 기록을 AWS failover, 실제 공급자
fallback 또는 운영 SLA로 표현하지 않는다.

### 7.4 로그가 남지 않거나 탐지가 멈춘 경우

| 시나리오 | 영향 | 현재 확인 가능한 것 | 미확인 |
|---|---|---|---|
| CloudWatch write 실패 | app/flow log 손실 | log driver와 IAM role 선언 | retry/alert |
| CloudFront/WAF 상세 log 필요 상황 | edge 요청 추적 공백 | 두 logging configuration 모두 미선언 | 목적지·보존·접근권한 |
| Prompt log 무기한 보존 | 저장량/개인정보 잔존 가능성 | AWS retention 미설정; 로컬 raw prompt write 관찰 | 승인 보존기간과 탈퇴 purge |
| CloudTrail data event 필요 상황 | S3 object access 추적 공백 가능성 | selector 미선언 | 사람의 통제 판정 |
| GuardDuty finding 발생 | detection event | detector enabled | notification, owner, response SLA |
| Config history 필요 상황 | configuration change trace 부재 | Config resource 미선언 | 사람의 보완 결정 |

### 7.5 대시보드와 검토용 복사본에 문제가 생긴 경우

| 층·시나리오 | 현재 preview 동작 또는 한계 | 운영 fail-closed 요구 |
|---|---|---|
| shared passcode 유출 | 공유 workspace 전체 접근 가능; 개인별 revoke 불가 | 사용자별 credential 폐기와 session revoke |
| nickname 사칭 | nickname은 attribution일 뿐 identity가 아님 | 검증된 사용자 ID를 audit actor에 결합 |
| 동시 저장 충돌 | optimistic version 불일치 시 HTTP 409, 사람이 server/local 초안을 선택 | tenant·object version별 충돌 정책과 변경 보존 |
| 승인 metadata 없음·위조 | browser import는 승인 진위를 증명하지 못하고 초안으로 취급 | ingestion 거부와 검토 요청 기록 |
| redaction 검사 실패 | preview build 게시 중단이 요구됨 | 민감값을 UI·bundle·log에 출력하지 않음 |
| tenant 불일치 | 현재 단일 shared workspace라 tenant isolation 없음 | 조회·ingestion 거부와 audit event 기록 |
| schema version 미지원 | 구조 validator는 있으나 운영 오류 계약 미확정 | ingestion 거부, 지원 version과 오류 코드 반환 |
| 로컬 Evidence Desk에 외부 preview 입력 | 현재 validator가 `EXTERNAL_PREVIEW`를 거부 | 승인된 외부 projection/schema가 없으면 계속 fail-closed |
| audit 저장 실패 | activity가 immutable external trail이 아님 | 보호 대상 동작 중단, 조용한 성공 금지 |
| client AWS 연결 시도 | 연결 기능·credential 입력 UI/API가 없음 | 이 부재를 유지하고 regression 검사 |

운영 ingestion API의 정확한 오류 코드, idempotency, retry, 보존 정책은 `UNKNOWN`이다.

### 7.6 개선안(TO-BE) 승인 확인에 실패한 경우

- 평가 승인이 없거나 해석할 수 없으면 planned resource count는 0을 유지한다.
- 승인 파일이 없거나 schema가 틀리거나 승인 값이 false이면 fail-closed다.
- 이 조건에서 `terraform/tobe` 리소스, module call, plan artifact를 만들지 않는다.
- AS-IS 리소스를 TO-BE로 복사해 gate를 우회하지 않는다.

### 7.7 업무망 PC에서 문제가 생긴 경우

| 시나리오 | 현재 확인 가능한 것 | 확인이 필요한 항목 | 문서 처리 |
|---|---|---|---|
| Windows 일부 단말에서 화면 또는 TLS 오류 | Windows PC 100대 | OS·브라우저 버전, 사내 proxy, 인증서 배포 | 호환성 시험 전 동작 단정 금지 |
| macOS 일부 단말에서 접근 오류 | macOS PC 80대 | OS·브라우저 버전, MDM 정책, DNS 경로 | 원인과 영향 범위 `UNKNOWN` 유지 |
| 업무망 전체에서 이름 해석 실패 | 단말 총 180대 | 사내 DNS와 Route 53 사이 실제 경로 | Terraform 공개 DNS 모델과 분리 기록 |
| 단말 분실 또는 계정 오용 | 수량만 확인 | 디스크 암호화, IdP, MFA, EDR, 원격 잠금 | 통제 존재 여부를 추정하지 않음 |

### 7.8 소스 코드와 실제 실행 이미지가 다른 경우

| 상황 | 판독 | 허용되는 결론 | 금지되는 결론 |
|---|---|---|---|
| 로컬 6개 container가 health 응답 | 조회 시점의 Compose 환경이 응답함 | 이전 빌드의 합성 경로가 기동한 관찰 | 최신 소스가 모두 빌드·시험됐다는 결론 |
| gateway source/container hash 불일치 | 실행 이미지가 최신 소스와 다름 | 재빌드·회귀시험 필요 | 최신 Bedrock adapter가 실행 중이라는 결론 |
| runtime Terraform에 변수·환경 계약 추가 | 기존 resource/module block 추가 없음 | 별도 변경 세트가 배선 계약을 확장 | 110-resource mock plan을 최신 변경으로 재검증했다는 결론 |
| 공개 릴리스 검사 6단계 | Lab·MLOps·OpenDART 정적 검사와 단위시험 묶음이 통과 | 공개된 소스 계약의 회귀 확인 | 장기 운영 안정성·성능·통제 효과 증명 |
| Bedrock 실험 단위시험 통과 | mock client 기반 handler 계약 확인 | 입력 제한·오류 mapping의 코드 수준 확인 | AWS 배포, 모델 품질, guardrail 운영 효과 확인 |

### 7.9 MLOps 자료·학습·승인에 문제가 생긴 경우

| 시나리오 | 현재 코드의 동작 또는 경계 | 운영 전 필요한 결정 |
|---|---|---|
| 기본 잠금에서 잘못 켜려 함 | `disabled`는 계획 0개다. 다음 단계의 확인값이 정확하지 않으면 Terraform이 거부함 | 승인 주체, 변경 기록과 비용 한도 |
| 실행 이미지가 내용 지문으로 고정되지 않음 | 같은 전용 ECR의 `@sha256` 이미지가 아니면 `runtime` 계획을 거부함 | 이미지 빌드·검사·서명과 보존 절차 |
| manifest가 합성 전용이 아니거나 허용하지 않은 항목이 있음 | 학습을 시작하지 않음 | 승인된 자료 출처, 입력 항목, 민감정보 검사와 삭제 절차 |
| 필수 파일이 없거나 크기·해시가 다름 | 세 입력 파일의 계약이 맞지 않으면 중단함. 같은 prefix의 여분 객체는 따로 찾지 않음 | 변경 승인, 서명, 보관 위치와 여분 객체 탐지 방식 |
| 같은 실행 번호가 다시 들어옴 | DynamoDB 조건부 쓰기로 기존 결과를 덮어쓰지 않음 | 재실행 번호 정책과 중복 처리 절차 |
| 최초 상태 기록 전에 오류가 남 | `RUNNING` 전 거부나 상태 저장 실패는 `FAILED_SAFE`를 남기지 못할 수 있음 | 외부 요청 기록, 경보와 조사 절차 |
| `RUNNING` 뒤 검사·학습·저장이 실패함 | `FAILED_SAFE` 전이를 시도함. 일부 외부 쓰기를 하나의 작업으로 되돌리는 보장은 없음 | 재시도, 남은 파일 정리와 원자성 기준 |
| 관찰값이 좋아 보임 | 사람 검토 대기에서 멈추며 자동 승격이나 추천 연결을 하지 않음 | 평가 기준, 검토자, 그림자 비교와 중단 조건 |
| 연결 뒤 품질 저하를 가정함 | 현재 연결·배포 기능이 없어 되돌리기도 구현하지 않음 | 버전 결속, 점진 배포, 감시와 되돌리기 절차 |

## 8. AS-IS 한계와 가정

> 이 장은 문서에서 가장 중요한 주의 사항을 모은다. 아래 한계 때문에 “설계가 있다”를
> “서비스가 실제로 잘 동작한다”로 바꾸어 말하면 안 된다.

### 8.1 다시 그린 설계의 한계

1. 이 Terraform은 J사가 보유한 IaC가 아니라 컨설팅팀이 역으로 작성한 mock 명세다.
2. 110은 planned resource 수이며 AWS에 존재하는 리소스 수가 아니다.
3. provider는 mock credential과 API skip 설정을 사용한다.
4. 인증서 DNS validation resource가 없어 실제 배포 가능한 edge stack이 아니다.
5. 기준 ECR repository에 실행 image가 없고 task definition의 기본 image URI는 합성값이다.
6. 별도 로컬 변경 세트는 회원·기업 DB URL 계약을 추가했으나 기업 DB·role bootstrap,
   migration, Redis·agent·gateway 주소와 검증된 service discovery가 없다.
7. health handler는 로컬 소스에 있지만 기준 ECS 이미지와 ALB 종단간 응답은 검증하지 않았다.
8. 기본 설명 provider는 합성 stub이다. 두 Bedrock 코드 경로는 서로 다른 APAC 교차 리전
   profile을 선언한다. 실제 공급자 호출, 요청별 destination, 처리 계약과 모델 승인은 확정되지 않았다.
9. 기존 gateway의 Bedrock adapter와 별도 관리형 실험은 코드 변경분이며 기준 110개에 포함되지 않는다. 관리형 실험은 과거 `DELETE_COMPLETE` 2건, 현재 관련 리소스 0으로 관찰됐고 성공 추론 증거는 확인되지 않았다.
10. 로컬 PostgreSQL 16과 Terraform RDS PostgreSQL 15.7 가정 사이 호환성을 시험하지 않았다.
11. consultant dashboard preview는 별도 코드와 저장소상 배포 기록이 있지만 기준 110개 밖이다.
    shared passcode·단일 workspace이므로 운영용 approved tenant snapshot pipeline과 같지 않다.
12. `docs/current` 승인 문서가 0건이므로 기획 참조는 현행 승인 기준이 아니다.
13. 업무망 PC 수량과 운영체제 구분 외에 단말 관리·인증·접속·수집 체계는 확인되지 않았다.
14. `docs/current/README.md`가 요구하는 Phase 1 선행조건은 승인 문서로 승격되지 않았다.
    이 재현 모델은 그 절차 상태를 해소하거나 승인을 대신하지 않는다.
15. 현재 공개 릴리스 검사는 6단계다. Lab·MLOps·OpenDART마다 정적 검사와 단위시험 묶음을 실행하지만,
    단말 180대 관찰이나 장기 운영 안정성·성능을 확인하는 시험은 아니다.
16. API 소스·효과 계약은 35개 처리 함수의 AST 지문과 선택 순서를 확인한다. 제어 흐름 지배,
    효과 실행 횟수, 트랜잭션 원자성과 후속 서비스 수신은 증명하지 않는다.
17. 신규 기업은 모델 기본값 `approved`로 생성되며 상태 전환과 전역 업무 gate가 없다.
18. 로컬 Evidence Desk는 무통신 정적 reader다. 승인 발급, 운영 tenant isolation, audit log나
    외부 preview 배포 서비스가 아니다.
19. OpenDART 복사본은 공개 출처를 표시하는 보조 자료다. 기업 인증, 추천 근거, 최신 공시의 완전성
    또는 외부 조회 성공을 증명하지 않는다.
20. 합성 MLOps는 현재 추천 런타임에 연결되지 않았고 실제 회원 자료로 학습하지 않는다. 별도
    서버리스 Terraform 루트는 0/13/14 단계별 계획과 실행 소스를 제공하지만 AWS 배포, 이미지 등록,
    Lambda 실행을 증명하지 않는다. 같은 seed의 재현 의도도 실행 환경이 달라도 항상 같은 결과를
    보장한다는 뜻이 아니다. 합격 가능성·인재 품질·공정성·출시 가능성을 판정하는 모델로 읽지 않는다.
21. OpenDART 온디맨드 작업자 소스는 있지만 SQS FIFO, Lambda, SSM 키, VPC·DB 권한과 배포 묶음은
    기준 Terraform에 없다. 소스 존재를 서버리스 경로 배포나 비용 측정 결과로 읽지 않는다.
22. Slack은 외부 업무 SaaS·자산대장 경계다. 바로가기와 macOS best-effort 종료 소스는 실제
    workspace 사용, 로그인·cookie 제거, 보존 정책이나 AWS 통합을 증명하지 않는다. VPN+MFA·UTM도
    시나리오 선언이며 이번 공개 저장소에서 구현·운영을 확인한 통제가 아니다.

### 8.2 확인 전 임시로 둔 값

| 항목 | 가정 | 영향 |
|---|---|---|
| RDS engine | PostgreSQL 15.7 | 실제 호환성 및 upgrade 요구 미검증 |
| RDS size | primary/replica `db.m6i.large`, 200 GiB | 비용과 성능 값이 사실로 확정되지 않음 |
| Redis | 7.0, `cache.m6g.large`, node 2개 | node 수와 failover가 원문 확정값이 아님 |
| ECS scaling | service별 min 2/max 4 | target tracking policy는 없음 |
| CloudFront | apex hostname, TLS policy, PriceClass 200 | 실제 DNS/비용 요구 미검증 |
| SSM endpoint | 세 Interface endpoint 경유 | 관리 트래픽의 실제 경로 미확정 |
| Fargate AZ | 두 subnet을 통한 scheduler 균형 | task별 고정 AZ 보장으로 읽지 않음 |
| 업무망 단말 | Windows 100대, macOS 80대, 합계 180대 | 사용자 확정 수량이며 Terraform 및 단말 관리 증적과 대조되지 않음 |
| 로컬 runtime dataset | `demo_not_for_measurement` 합성 seed | 실제 사용자·기업 자료 또는 정량 평가 evidence로 사용 금지 |
| AI 점수 | 기술 70/경력 20/직무 10 고정 | 기업 승인 가중치나 모델 품질 결과가 아님 |
| Redis TTL | 로컬 추천 cache 24시간 | AWS 운영 정책으로 승인되지 않았고 공고 변경 무효화 없음 |

### 8.3 자료끼리 다른 내용과 아직 정하지 못한 사항

- 기존 일부 module README는 통합 전 상태를 설명해 root `.tf`가 없다고 적지만 현재 root
  module과 provider 파일이 존재한다. 실행 코드가 우선 관찰 대상이다.
- P1 원문 제목은 12화면이지만 열거 내용은 화면 11개와 Mailpit 비화면 기능 1개다. 이
  명세는 제목 숫자를 그대로 상속하지 않고 열거 항목을 기능 성격별로 분리했다.
- P0 기획은 file upload/parser를 제외하지만 Terraform은 resume 원본 S3 bucket을
  모델링한다. runtime 관계는 `UNKNOWN`이다.
- ALB log bucket에는 90일 lifecycle이 있고 resume bucket에는 lifecycle이 없다. 승인 전
  finding template의 layer-wide 조건과 충돌하며 사람 판단 대기 상태다.
- RDS/cache/security group의 실제 운영 동작은 plan만으로 검증할 수 없다.
- 제공된 Artifact는 업무망 180대를 모두 Windows로 표시하고 AD domain, UTM, VPN MFA,
  전통 백신을 함께 그린다. 이 명세는 사용자의 후속 정정값인 Windows 100대와 macOS 80대를
  사용한다. VPN+MFA·UTM은 `SCENARIO_DECLARED`, 실제 구현·운영 관찰은 `UNKNOWN`으로 분리한다.
- Slack은 멘토 요청 자산대장과 Windows/macOS 이미지 소스에 이름이 있으나 실제 workspace 사용은
  `SCENARIO_USE_UNVERIFIED`다. AWS 자원이나 알림 경로로 승격하지 않고 외부 SaaS 경계로만 둔다.
- 제공된 Artifact는 AZ 2a 단면만 표시해 2c subnet, NAT-C, RDS standby가 보이지 않는다.
  AS-IS Terraform과 이 명세의 흐름도는 2a/2c를 모두 전개한다.
- 제공된 Artifact의 독립 `matcher` 상자는 논리 구성이다. Terraform에는 matcher 서비스가
  없으며, React Renderer·운영자 콘솔·BI 조회·staging band도 대응 리소스가 없다.
- Artifact의 임직원 180명과 경로별 사용자 합계는 같은 모집단임이 입증되지 않았다.
  업무망 PC 180대 수량을 애플리케이션 사용자 수나 동시 접속 수로 변환하지 않는다.
- Artifact와 일부 Terraform 주석의 "데이터 담당 2명"은 승인된 인원 근거를 찾지 못했다.
  이 명세는 인원수를 확정하지 않는다.
- 기준 Terraform worktree에는 애플리케이션 소스가 없지만 별도 `asis-runtime-mvp` 변경
  세트에는 합성 런타임 소스가 있다. 기준선의 "runtime 부재"와 변경 세트의 "로컬 구현"을
  서로 덮어쓰지 않는다.
- 별도 변경 세트의 Terraform은 변수·환경·논리 DB 계약을 바꿨지만 resource block 73개와
  module block 6개는 기준과 동일하다. 최신 변경으로 mock plan 110개를 다시 만들지는 않았다.
- 기존 gateway 내부 Bedrock adapter의 기본 잠금과 별도 관리형 Bedrock 실험 브랜치는 서로
  다른 코드 경계다. 전자는 Nova Lite, 후자는 Nova Micro APAC 교차 리전 profile을 기본으로
  둔다. 둘 다 실제 AWS 통합이나 J-Career 운영 서비스를 뜻하지 않는다.
- TRACE·JC-RECEIPT 관련 세션은 비교용 명칭·흐름 제안만 포함한다. 구현·승인·Terraform 변경은
  없고, 제안된 fail-closed와 기존 외부 공급자 흐름의 충돌도 사람 결정 전이다.

### 8.4 이렇게 단정하면 안 되는 내용

- 관리형 WAF 규칙이 존재한다는 사실을 자유서술 prompt 방어 완료로 읽지 않는다.
- Multi-AZ 선언을 장애조치 시험 완료로 읽지 않는다.
- GuardDuty 활성 선언을 대응 체계 보유로 읽지 않는다.
- CloudTrail 선언을 S3 object-level audit로 읽지 않는다.
- Terraform 검증 통과를 서비스 이용 가능 또는 운영 준비 완료로 읽지 않는다.
- 로컬 Compose health와 단위시험을 AWS 배포·공급자 실호출·최신 이미지 검증 완료로 읽지 않는다.
- Bedrock 코드와 Guardrail 선언을 안전성·공정성·설명 충실도 또는 APAC 교차 리전 처리 승인으로 읽지 않는다.
- `company_alignment`를 점수 반영, 합격 판단 또는 기업 문화 적합성의 검증 결과로 읽지 않는다.
- ISO template 행을 J-Career 판정, 외국 조직 evidence, 출판 가능한 표준 번역으로 읽지 않는다.

## 9. 추적성 표

> 아래 표는 주요 설명이 어떤 파일이나 확인 결과에서 나왔는지 보여 준다. 근거를 다시
> 확인해야 할 때 사용하는 목록이다.

| 명세 주장 | 저장소 근거 |
|---|---|
| 업무망 PC 180대: Windows 100, macOS 80 | 현재 대화 사용자 원문 “업무망 pc 180대가 윈도우 100대, mac 80대인거라고”를 `REQ-PC-01`로 식별. 이 산출물의 사용자 확정 입력이며 저장소·Terraform·조직 승인 근거 아님 |
| Slack 외부 업무 SaaS 경계 | `fleet/images/windows/build-component.yaml`, `fleet/images/macos/prepare-consultant.sh`, `fleet/images/macos/remove-jcareer-session.sh`, `fleet/images/endpoint_image_contract.yaml`, `src/runtime/contracts/mentor_feedback_2026_08_28.json`; 바로가기·macOS best-effort 종료 외 운영은 `SCENARIO_USE_UNVERIFIED` |
| 2-AZ, 6 subnet, AZ별 NAT | `terraform/asis/network/main.tf`, `terraform/asis/network/variables.tf` |
| 네 ECS 서비스와 path/port | `terraform/asis/compute/locals.tf`, `terraform/asis/compute/main.tf` |
| 110 planned resources | `context/findings/PHASE1_ASIS_EVIDENCE.md`, sanitized structural count |
| RDS/Redis/S3 속성 | `terraform/asis/data/*.tf` |
| IAM/SSM 경로 | `terraform/asis/security/*.tf` |
| 로그 보존과 CloudTrail/GuardDuty | `terraform/asis/observability/main.tf` |
| Route 53/CloudFront/WAF/ACM | `terraform/asis/edge/main.tf` |
| 앱 논리와 trust boundary | `context/raw/D02-진단대상-아키텍처-정의.md#그림 1이 말하는 것 (시스템 구성 · 논리)` |
| P0/P1 화면 계획 | `context/raw/Orca-범위확정-EnterpriseMVP.md#P0 — 14화면 (측정 5건이 나오는 최소 경로 · 절대 불가침)` |
| 명시된 candidate API 경로 | `context/raw/C플러스-범위델타-구직자흐름.md#1.5` |
| 파기와 저장면 계획 | `context/raw/Jcareer-흐름과-기술취약점.md#2.5` |
| 로컬 네 서비스·두 논리 DB·Redis | 별도 `asis-runtime-mvp/src/runtime/README.md`, `compose.yaml` |
| 업무 API 30개 경로 선언 | `src/runtime/api/app/main.py` |
| 전체 API 라우트 40개·처리 함수 35개 | `src/runtime/contracts/api_surface.json`, `scripts/check_api_surface_contract.py` |
| 35개 처리 함수의 효과와 선택 순서 | `src/runtime/contracts/api_effects.json`, `scripts/check_api_effects_contract.py` |
| OpenDART 공개정보 보조 기능 | 별도 `asis-runtime-mvp/src/runtime/api/app/opendart.py`, `api/app/opendart_dispatch.py`, `api/app/main.py`, `opendart_worker/handler.py`, `web/src/App.jsx`, `tests/opendart_*_contract.py` |
| 합성 MLOps 로컬 학습·평가 | `src/mlops/README.md`, `generate_synthetic_training.py`, `run_runtime_pipeline.py`, `tests/test_synthetic_pipeline.py`; 운영 추천 연결 없음 |
| 합성 MLOps 서버리스 경로 | `terraform/serverless-mlops/README.md`, `main.tf`, `tests/stages.tftest.hcl`, `src/mlops/lambda_handler.py`; 기준 110개와 별도인 0/13/14 계획, AWS 배포 결과는 없음 |
| 70/20/10 matcher와 양방향 내부 API | 별도 `asis-runtime-mvp/src/runtime/agent/app/main.py`, `AI_MATCHING_FLOW.md` |
| 설명 장애 격리·alignment·Bedrock 내부 adapter | 별도 `asis-runtime-mvp/src/runtime/llm_gateway/app/main.py` |
| 로컬 실행 관찰값과 한계 | 별도 `asis-runtime-mvp/src/runtime/VERIFICATION.md`; 과거 실행값은 승계하지 않고 소스 정적 검사만 별도 재실행 |
| 컨설턴트 AIMS Desk preview | 별도 `feat/iso-dashboard`의 `dashboard/README.md`, `backend/README.md`, `backend/template.yaml`, `docs/USER_GUIDE.md`, `dist/release-manifest.json`; 2026-08-28 동료 세션 읽기 전용 관찰 |
| 로컬 Evidence Desk의 무통신·tenant_ref 내용 결속 | 별도 `asis-runtime-mvp/dashboard/README.md`, `snapshot.schema.json`, `src/snapshot.js`, `src/view-model.js` |
| 관리형 Bedrock 실험 | 별도 `feat/bedrock-managed-runtime`의 `src/bedrock-ai-service/template.yaml`, `handler.py`, 단위시험; 2026-08-28 동료 세션의 삭제 이력·현재 0 관찰 |
| TRACE·JC-RECEIPT 미구현 | Orca로 조회한 관련 세션 답변과 runtime/Terraform 명칭 검색. 제안 내용은 AS-IS 근거에서 제외 |
| 승인 문서 0건 | `docs/current/README.md` |
| 기본 5개 GAP 미선언 대장 | `terraform/asis/ABSENCE_MANIFEST.md` |
| CloudTrail data event·resume lifecycle 미선언 | `terraform/asis/observability/main.tf`, `terraform/asis/data/s3_resume.tf` |
| CloudFront·WAF logging 미선언 | `terraform/asis/edge/main.tf`, `terraform/asis/edge/README.md` |

## 10. 산출물 연결

> 웹 문서는 읽기용, PDF는 전달·인쇄용, draw.io는 수정용, PNG는 빠른 확인용이다.

- 정식 HTML 명세: [`index.html`](index.html)
- 배포용 PDF 명세: [`JCAREER_ASIS_SYSTEM_SPEC.pdf`](JCAREER_ASIS_SYSTEM_SPEC.pdf)
- 편집 원본: [`JCAREER_ASIS_FLOW.drawio`](JCAREER_ASIS_FLOW.drawio)
- PNG: [`JCAREER_ASIS_FLOW.drawio.png`](JCAREER_ASIS_FLOW.drawio.png)
- 보조 상세 도면은 원본 작업 트리에 별도로 보관한다. 공개 기준 도면의 수량과 검증에는 포함하지 않는다.
- 상호작용 도면 설명: [`architecture.html`](architecture.html). 전체 보기 1개와 구직자 추천,
  기업용 인재 찾기, AI 설명, MLOps 학습·평가, 기록·탐지의 서비스·보조 경로 5개가 있다. 항목을
  누르면 관련 구간과 번호가 붙은 3단계 설명, 확인 수준, 해당 상세 명세 바로가기가 함께 바뀐다.
  해설 본문은 `JCAREER_ASIS_FLOW.md`에서 생성하며 source hash를 회귀검사한다.
- MLOps 전용 웹 명세: [`../../mlops/index.html`](../../mlops/index.html). 합성 자료부터 사람 검토
  대기까지 7단계, 별도 Terraform의 0/13/14 계획과 데이터·보안 경계를 제공한다.
- MLOps 전용 PDF: [`../../mlops/JCAREER_MLOPS_SYSTEM_SPEC.pdf`](../../mlops/JCAREER_MLOPS_SYSTEM_SPEC.pdf)
- MLOps 흐름도 원본·PNG: [`../serverless-mlops/JCAREER_MLOPS_FLOW.drawio`](../serverless-mlops/JCAREER_MLOPS_FLOW.drawio),
  [`../serverless-mlops/JCAREER_MLOPS_FLOW.drawio.png`](../serverless-mlops/JCAREER_MLOPS_FLOW.drawio.png)
- 기계 판독 검증 결과: [`validation-report.json`](validation-report.json)

## 11. 검증 기록

> 아래 PASS는 해당 행에 적힌 검사만 통과했다는 뜻이다. AWS 배포나 실제 서비스 운영을
> 통과했다는 뜻은 아니다.

2026-08-27~31에 원본 대조, 로컬 정적 검사, 문서 렌더링 검사를 수행했다.
기준 설계인 `terraform/asis`에는 AWS 변경이나 `terraform apply`를 수행하지 않았다.
별도 검증용 `terraform/lab`에서는 24개 생성 계획과 Bedrock 직접 호출을 확인했지만,
IAM 역할 생성 권한이 없어 적용이 중단됐다. 그 과정에서 만들어진 16개 항목은 같은 저장
계획으로 지워 현재 Lab 상태를 0개로 되돌렸다. 따라서 애플리케이션 전체 경로가 배포됐거나
서비스가 운영 중이라는 뜻이 아니다. 아래 PASS는 각 행에 적힌 범위만 뜻한다.

| 검사 | 결과 |
|---|---|
| Terraform 형식 | PASS — Terraform 1.15.9 `fmt -check -recursive`, `.tf` 38개 |
| Terraform 초기화·구문 검증 | PASS — 원본 작업 트리의 provider cache checksum 불일치를 재현한 뒤, `.tf` 38개만 임시 복제해 `init -backend=false`와 `validate`를 통과. AWS provider 6.59.0 설치 외 AWS API 호출·plan·apply 없음 |
| 기준선·변경 세트 정적 계수 | PASS — 양쪽 모두 `.tf` 38개, `resource` block 73개, module call 6개, `data` block 6개. heredoc 설명의 `data "..."` 문구 두 줄은 block에서 제외. runtime 배선 변경은 resource/module block을 추가하지 않음 |
| 기록된 mock plan 구조 수 | EVIDENCE — 기준선 Phase 1 산출물의 managed create 110, update/delete 0. 전체 change 113은 data read 3건을 포함. 모듈별 47/27/16/9/6/5이며 runtime 변경 세트로 plan을 다시 산출하지 않음 |
| 기대 GAP 대조 | 미완료 — 17건 중 PASS 5, FAIL 5, 문서 판정 7. FAIL은 `GAP-TRAIL-01`, `GAP-LOG-01`, `GAP-RDS-01`, `GAP-S3-01`, `GAP-CACHE-01`; 빈 scanner `rule_id`와 조건 범위 충돌을 해소하지 않음 |
| 스캐너 결과 분류 | `PROVISIONAL` — 중복 정규화 후 117건을 보존했으나 사람 판정 전이며 통과로 읽지 않음 |
| 인용 anchor | PASS — strict mode 55개, broken 0개 |
| 공개 합성 런타임 소스 | PASS(정적·단위시험 범위) — 현재 공개 릴리스 검사 6단계가 통과했다. API/agent/gateway 라우트 30/6/4개와 70·20·10 점수식, `score_effect=NONE`을 정적 대조했다. 단말·성능·장기 운영 결과는 포함하지 않는다. |
| AWS 검증 계정 Bedrock 직접 호출 | PASS(직접 호출 범위) — APAC Nova Lite에 합성 문장 한 건을 보내 입력 39·출력 53토큰 응답을 확인했다. 응답 본문과 계정 식별자는 기록하지 않았다. API→gateway→broker 전체 경로의 성공을 뜻하지 않는다. |
| AWS 검증 Lab 재배포 | BLOCKED 후 정리 완료 — 24개 생성 계획은 통과했으나 IAM 역할 생성 권한 부족으로 적용이 중단됐다. 부분 생성된 16개 항목만 지우는 저장 계획을 적용해 현재 Lab 상태를 0개로 되돌렸다. |
| MLOps 합성 파이프라인 | PASS(단위시험 범위) — `python -m unittest src/mlops/tests/test_synthetic_pipeline.py`를 실행해 22/22, FAIL 0을 확인했다. 합성 SQLite와 테스트 대역 S3·DynamoDB로 원문 잔류, 중복 실행과 실패 경계를 확인한 결과이며 AWS 자원·모델 품질 판정은 포함하지 않음 |
| MLOps 전용 Terraform | PASS(코드·계획 범위) — 전용 루트 경계 시험 19/19, mock 단계 시험 3/3과 `disabled 0`, `bootstrap 13`, `runtime 14` 계획을 확인했다. 기준 110개와 별도이며 AWS API, apply/destroy, 이미지 등록과 Lambda 실행은 하지 않음 |
| API 소스·효과 계약 | PASS(정적 범위) — `api_surface.json` 라우트 40개와 처리 함수 35개, 효과 회귀 17/17, 도우미 20개·선택 순서 9개 확인. `AST_PARTIAL`이며 제어 흐름 지배·실행 횟수·원자성·실제 후속 서비스 수신을 증명하지 않음 |
| 로컬 Evidence Desk | PASS(정적 범위) — validator·view-model·artifact 결속 시험 28건과 무통신·무브라우저저장·무자동판정 경계를 확인했다. 승인된 복사본 반입이나 운영 배포를 확인한 결과는 아님 |
| 별도 Bedrock 실험 브랜치 | PASS(단위시험 범위) — mock client 기반 7/7 통과. 실제 Bedrock 호출, AWS 배포, 기준 API 통합을 검증한 결과가 아님 |
| Orca 교차 세션 대조 | PASS — 런타임 Run, TRACE 기획, Terraform 독립 검증, AIMS Desk UX 세션을 분리 조회. TRACE·JC-RECEIPT는 제안 상태이고 신규 AS-IS 서비스가 아니며, 확인된 변화는 기존 API/gateway/cache와 두 대시보드의 소스 계약임을 재확인 |
| Claude/Codex/Orca 검토 | 독립 검토 의견을 문서 보완에 반영했다. 목록 구조, 수량 근거, Bedrock 관찰 범위, MLOps 경계와 쉬운 한국어 표현을 교차 확인했다. 공개 승인 여부와 통제 충족 여부는 사람이 별도로 결정한다. |
| draw.io XML 구조 | PASS — XML 형식, ID 중복, 연결선 양 끝, 그룹 구조를 자동 검사 |
| PNG 크기 및 시각 검토 | PASS — 2400×1400, 왼쪽에서 오른쪽으로 이어지는 6단계 기준 흐름, 독립 MLOps 실행 경로, AWS 흐름선이 없는 Slack 외부 SaaS·업무망 선언 경계를 눈으로 확인 |
| HTML 구조 및 로컬 링크 | PASS — HTML 2개, 내부 anchor·로컬 산출물 링크 broken 0, duplicate ID 0 |
| HTML 목록 의미 구조 | PASS — AS-IS 한계 22개와 도면 요청 흐름 6개가 각각 하나의 연속 `<ol>`로 생성되며 들여쓴 문장이 같은 `<li>` 안에 유지됨 |
| PDF 인쇄본 | PASS — PDF 1.4 헤더, A4 인쇄 스타일, HTML 원본 지문 결속과 페이지 객체 확인 |
| 웹 품질 계측 | 이전 PASS(로컬 모바일) — Lighthouse 12.8.2 기준 본문 96/100/100/100, 도면 98/100/100/100(성능/접근성/권장사항/검색). v3.10에서는 데스크톱·모바일 화면과 MLOps 영역의 배치를 확인했다. v3.11에서는 가로 390px의 휴대전화 화면으로 다시 확인했다. 도면 안쪽의 좌우 이동 영역을 제외하면 페이지 바깥으로 튀어나온 내용은 없었다. MLOps 버튼을 눌렀을 때 설명과 전용 명세 링크가 함께 바뀌는지도 확인했다. Lighthouse 점수는 다시 측정하지 않아 이전 값을 유지함 |
| 기계 판독 회귀검사 | PASS — `validate-spec.ps1` 25/25, FAIL 0. 상세 결과는 `validation-report.json`에 기록 |
| account ID·비밀정보 패턴 | PASS — 공개용 UTF-8 원본 6개에서 12자리 account ID, access key, private key, 일반 secret assignment 패턴 0건. PDF·PNG는 raw byte sentinel 검사와 검사를 마친 원본의 생성 체인으로 확인 |
| 쉬운 한국어와 문장 검토 | PASS — 처음 읽는 분을 위한 요약·숫자 설명·용어 풀이를 두고, 서비스별 설명을 3단계로 줄였다. 기술 명칭은 필요한 곳에만 원문을 함께 표시 |
