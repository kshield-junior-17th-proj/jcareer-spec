# J-Career 정보보호시스템 목록

> 상태: `DRAFT_FOR_HUMAN_CONFIRMATION`
> 목적: 합성 AS-IS AI 서비스 시연에서 정보보호시스템의 범위와 근거를 한 화면에서 설명한다.
> 경계: 아래의 `시나리오 기록`은 가상 고객사 설정이고, `source 모델`은 코드에 선언된 상태다.
> 어느 쪽도 실제 운영 배포를 자동으로 증명하지 않는다.

## 1. 상태 읽는 법

| 상태 | 의미 |
|---|---|
| `SCENARIO_BASELINE` | 기존 `SCENARIO_FACTS`에 기록된 가상 고객사 설정 |
| `SOURCE_MODELED` | 현재 Terraform 또는 런타임 source에서 구조를 확인할 수 있음 |
| `MENTOR_REQUESTED_UNVERIFIED` | 8/28 멘토 메모가 대장 편입을 요구했으나 존재·구성 자료는 아직 없음 |
| `DECLARED_ABSENT` | 기존 시나리오가 미도입·미사용으로 명시함 |
| `HUMAN_CONFIRMATION_PENDING` | 제품명·소유자·실제 구성·운영 증적을 사람이 확인해야 함 |

조직도와 자산 소유자는 계속 바뀔 수 있으므로 이 문서에서 확정하지 않는다. 모든 소유자는
`HUMAN_ASSIGNMENT_PENDING`이며, 시스템의 사실 경계만 유지한다.

## 2. 현재 정보보호시스템 대장

| ID | 시스템 | 보호 목적 | 현재 기록 | AI 서비스와의 접점 | 근거 |
|---|---|---|---|---|---|
| `IPS-EDGE-01` | 경계 UTM 방화벽 | 사내 업무망 경계 통제 | `SCENARIO_BASELINE` · 1식 · 이중화 없음 | 운영·개발 단말에서 AI 서비스 관리면으로 가는 사내 경계 | `context/raw/SCENARIO_FACTS-가상고객사J사.md` §9.3 |
| `IPS-EDGE-02` | AWS WAF | 공개 웹 요청 필터링 | `SCENARIO_BASELINE` + `SOURCE_MODELED` · 관리형 Common/SQLi 규칙 · 자유서술 커스텀 규칙 없음 | 이력서·자기소개서가 들어오는 첫 엣지 | `terraform/asis/edge/main.tf` · `terraform/asis/edge/README.md#4. WAF — 관리형 두 개뿐인 것이 AS-IS 다` |
| `IPS-NET-01` | VPC Security Group | ALB·ECS·RDS·Redis·SSM endpoint 간 네트워크 허용 경계 | `SOURCE_MODELED` · 실제 배포 미주장 | API→matcher/LLM gateway와 DB 접근 경로 | `terraform/asis/network/security_groups.tf` |
| `IPS-ACCESS-01` | VPN + MFA | 사내 원격 접속 | `SCENARIO_BASELINE` · 런타임 재현 없음 | 원격 운영자 접근의 선행 경로 | `context/raw/SCENARIO_FACTS-가상고객사J사.md` §9.3 |
| `IPS-ACCESS-02` | SSM Session Manager | 서버 관리 셸 접근·SSH 비개방 | `SCENARIO_BASELINE` + `SOURCE_MODELED` · endpoint 상세는 source 가정 | ECS/서버 셸에서 DB·로그로 이어지는 관리자 경로 | `terraform/asis/security/endpoints.tf` · `terraform/asis/security/README.md#이 모듈의 지위` |
| `IPS-ACCESS-03` | AWS IAM 역할·정책 | 워크로드 및 로그 전달 권한 | `SOURCE_MODELED` · 실제 계정 적용 미주장 | ECS task의 S3·Bedrock 후보 권한과 Flow Logs 전달 | `terraform/asis/security/iam.tf` |
| `IPS-DETECT-01` | Amazon GuardDuty | AWS 위협 탐지 | `SCENARIO_BASELINE` + `SOURCE_MODELED` | 서비스망 이상 징후의 탐지 평면 | `terraform/asis/observability/main.tf` |
| `IPS-AUDIT-01` | AWS CloudTrail | AWS API 감사 추적 | `SCENARIO_BASELINE` + `SOURCE_MODELED` · 관리 이벤트만 · S3 데이터 이벤트 없음 | AI 서비스 자원 변경 이력과 데이터 접근 이력의 경계 | `terraform/asis/observability/main.tf` |
| `IPS-AUDIT-02` | VPC Flow Logs | 네트워크 흐름 기록 | `SCENARIO_BASELINE` + `SOURCE_MODELED` · CloudWatch 30일 | llm-gateway 외부 송신 및 내부 서비스 연결 관찰 보조 | `terraform/asis/observability/main.tf` |
| `IPS-AUDIT-03` | Amazon CloudWatch Logs | 접속·흐름·프롬프트 로그 보관 | `SCENARIO_BASELINE` + `SOURCE_MODELED` · access 365일 · flow 30일 · prompt-raw 보존기간 미설정 | LLM 전송 원문과 내부 열람면이 만나는 로그 경계 | `terraform/asis/observability/main.tf` |
| `IPS-ENDPOINT-01` | 전통 백신 | 업무 단말 악성코드 방어 | `SCENARIO_BASELINE` · lab 설치 증적 아님 | 개발·운영자가 합성 AI 서비스에 접속하는 단말 | `fleet/README.md#시나리오 inventory — 구축하지 않는다` |
| `IPS-NET-02` | IPS | 침입 차단 | `MENTOR_REQUESTED_UNVERIFIED` | 배치 위치·제품·룰·로그 연계가 아직 없음 | [8/28 멘토 회의](https://app.notion.com/p/3ca0be5710e8805badf9c7fa7c8f762b?pvs=204) |
| `IPS-NET-03` | IDS | 침입 탐지 | `MENTOR_REQUESTED_UNVERIFIED` | 배치 위치·제품·룰·로그 연계가 아직 없음 | [8/28 멘토 회의](https://app.notion.com/p/3ca0be5710e8805badf9c7fa7c8f762b?pvs=204) |

등록 대상은 13행이다. 이 가운데 IPS·IDS 2행은 존재 확인 전 후보이며, 나머지도
`SCENARIO_BASELINE` 또는 `SOURCE_MODELED`일 수 있으므로 **13대를 실제 운용한다는 뜻이 아니다**.

## 3. 정보보호 관련 명시적 부재

부재 항목을 현재 시스템처럼 세지 않는다. 다만 AS-IS 설명에서 빠지지 않게 별도 보존한다.

| 항목 | 현재 기록 | source 위치 |
|---|---|---|
| EDR | `DECLARED_ABSENT` · 시나리오상 미도입 | `fleet/README.md#시나리오 inventory — 구축하지 않는다` |
| AWS Config | `DECLARED_ABSENT` · Terraform 의도적 미선언 | `terraform/asis/observability/main.tf` |
| AWS Secrets Manager | `DECLARED_ABSENT` · 합성 키는 환경변수 모델 | `terraform/asis/security/iam.tf` |
| 고객 관리형 KMS 키(CMK) | `DECLARED_ABSENT` · AWS 관리형 암호화만 모델 | `terraform/asis/ABSENCE_MANIFEST.md` |
| WAF 자유서술 커스텀 규칙 | `DECLARED_ABSENT` · 관리형 규칙 두 종류만 모델 | `terraform/asis/edge/main.tf` |

## 4. 인접 자산 — 정보보호시스템 수에 포함하지 않음

| 분류 | 자산 | 현재 경계 |
|---|---|---|
| 정보처리시스템 | J-Career web·API·matcher(agent)·llm-gateway | 합성 source 구현 · 운영 배포 미주장 |
| 정보처리·복구 | RDS 자동 백업 7일·PITR | 시나리오와 Terraform 모델 존재 · 장애조치 시험 이력은 별도 |
| 관찰 자산 | 백업 서버 | 화이트보드 관찰값 · 기준선 아님 · 존재 확인 전 |
| 데이터 | 회원DB·기업DB | 합성 논리 DB 구현 · 필드 경계는 `src/runtime/DB_FIELD_CATALOG.md#4. 현재 matcher와 LLM 설명 payload` |
| 물리 | 랙 장비 | 멘토 요청 후보 · 존재 확인 전 |
| SaaS | Slack | 멘토 요청 후보 · 사용·workspace·보존 범위 확인 전 |
| 단말 | 업무용 PC·프린터 | 시나리오/화이트보드 기록 · 실제 lab 조달로 읽지 않음 |

그룹웨어 서버와 사내DB는 과거 기록을 삭제한 것이 아니라 **이번 8/28 멘토 제안 대장 범위에서만**
제외한다. 회원DB와 기업DB는 AI 서비스의 양면시장 데이터 경계이므로 그대로 유지한다.

## 5. 다음 확인 자료

1. UTM·IPS·IDS의 제품명, 논리/물리 배치, 이중화, 룰 소유자, 로그 목적지
2. WAF Web ACL과 실제 연결 대상, 관리형/커스텀 규칙, 로그 설정
3. GuardDuty·CloudTrail·Flow Logs·CloudWatch의 활성 화면과 보존 설정
4. VPN·MFA·SSM·IAM의 계정·역할·승인·회수 흐름
5. Windows/macOS별 백신 적용 범위와 EDR 도입 여부
6. Slack workspace 사용 여부, 개인정보 입력 정책, 앱 연동, 보존·삭제 설정
7. 회원DB·기업DB에서 matcher와 Bedrock 설명기로 나가는 필드 allowlist

이 자료가 들어오기 전에는 제품 존재, 배포 상태, 운영 효과, 담당 조직을 자동 확정하지 않는다.
