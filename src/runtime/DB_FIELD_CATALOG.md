# J-Career 회원DB·기업DB 필드 정의와 LLM02 계수 경계

**기준일:** 2026-08-28
**상태:** `SOURCE_CATALOG_DECISION_PENDING`
**용도:** 화이트보드 논리 필드, 현재 합성 런타임의 물리 필드, matcher 입력, LLM 설명 입력을
서로 다른 층으로 고정한다.

이 문서는 필드의 수집·이용을 승인하거나 개인정보보호법상 분류를 판정하지 않는다. 특히
아래 `민감정보`는 **화이트보드에 적힌 분류명**을 옮긴 것이며 법적 판정값이 아니다.
실제 지원자 데이터는 입력하지 않고 합성 데이터만 사용한다.

## 1. 근거와 상태

| 근거 | 이 문서에서의 용도 | 상태 |
|---|---|---|
| `context/findings/WHITEBOARD_IMPACT_ASSESSMENT_2026-08-28.md#0. 입력과 결정 경계` | 외부 통합 판독본의 출처 위치와 결정 경계 | `OBSERVED_WHITEBOARD_2026_08_28` |
| `context/raw/SCENARIO_FACTS-가상고객사J사.md#12` | 기존 수집·민감정보 설정과 충돌 확인 | 기존 기준선 · 변경 결정 필요 |
| `context/raw/D04-자료요청목록-문서보유현황.md#2.1` | 회원DB·회사DB 자산명 확인 | 기존 기준선 · 필드 미정의 |
| `src/runtime/api/app/models.py` | 현재 PostgreSQL 물리 column | `SOURCE_IMPLEMENTED` |
| `src/runtime/api/app/main.py` | matcher·설명 요청 조립 | `SOURCE_IMPLEMENTED` |
| `src/runtime/llm_gateway/app/main.py` | gateway request schema·현재 PII 필드명 계수 | `SOURCE_IMPLEMENTED` |

조직 기준선 교체 여부와 마찬가지로, 화이트보드 필드를 `SCENARIO_CONFIRMED`로 승격할지는
사람이 결정한다. 이 문서는 판독값이 코드와 어디서 일치·불일치하는지만 보여 준다.
회원DB 14개·기업DB 9개 전사는 해당 저장소 근거가 가리키는 외부 통합 판독본 §1.4에서
옮겼으며, 저장소 문서에서는 외부 절대경로 대신 위의 저장소 기준 앵커만 사용한다.

## 2. 화이트보드 논리 필드 모수

화이트보드 문구를 더 잘게 추정하지 않고 적힌 최소 단위로 세면 다음과 같다.

| 논리 저장소 | 일반/기본 필드 | 화이트보드상 민감정보 | 합계 |
|---|---:|---:|---:|
| 회원DB | 11 | 3 | **14** |
| 기업DB | 9 | 해당 표기 없음 | **9** |
| **전체** | **20** | **3** | **23** |

기업DB의 `담당자`는 이메일·전화번호 2개로, `우대사항`은 자격증·전공·교육 이수·경력 4개로
센다. `자격요건`은 하위 항목이 적혀 있지 않아 하나의 논리 필드 그룹으로 유지한다.

### 2.1 회원DB — 14개

| # | 논리 ID | 화이트보드 필드 | 현재 물리 매핑 | 현재 matcher/LLM 경로 | 구현 대조 상태 |
|---:|---|---|---|---|---|
| 1 | `member.name` | 이름 | `User.display_name` | 점수 미사용 · `candidate_context.name` · 현재 계수 포함 | `IMPLEMENTED_RENAMED` |
| 2 | `member.address` | 주소 | `Resume.address_region` | 점수 미사용 · `candidate_context.address` · 현재 계수 포함 | `PARTIAL_REGION_ONLY` |
| 3 | `member.age` | 나이 | 없음. 런타임에는 `Resume.birth_date`가 별도 존재 | `candidate_context.birthdate` · 현재 계수 포함 | `SEMANTIC_MISMATCH_DECISION_REQUIRED` |
| 4 | `member.school` | 학교 | `Resume.education` 자유문에 포함 가능 | `candidate_context.school` · 현재 계수 포함 | `PARTIAL_COMPOSITE` |
| 5 | `member.military_service` | 병역 | 없음 | 없음 | `NOT_IMPLEMENTED` |
| 6 | `member.certificates` | 자격증 | `Resume.certificates` | 점수 미사용 · `candidate_context.certificates` · 현재 계수 제외 | `IMPLEMENTED_NOT_CLASSIFIED_BY_COUNTER` |
| 7 | `member.gpa` | 학점 | 없음 | 없음 | `NOT_IMPLEMENTED` |
| 8 | `member.self_intro` | 자소서 | `Resume.self_intro` | 점수 미사용 · `candidate_context.self_intro` · 현재 계수 제외 | `IMPLEMENTED_NOT_CLASSIFIED_BY_COUNTER` |
| 9 | `member.career` | 경력 | `Resume.years_experience` 집계값만 존재 | matcher 사용 · `score_breakdown`과 label을 통해 설명 payload에 파생 표현 포함 가능 | `PARTIAL_AGGREGATE_OUTSIDE_COUNTER` |
| 10 | `member.projects` | 프로젝트 | 없음 | 없음 | `NOT_IMPLEMENTED` |
| 11 | `member.email` | 이메일 | `User.email` | 점수 미사용 · `candidate_context.email` · 현재 계수 포함 | `IMPLEMENTED` |
| 12 | `member.disability` | 장애 | 없음 | 없음 | `NOT_IMPLEMENTED_SOURCE_LABEL_SENSITIVE` |
| 13 | `member.physical` | 신체 | 없음 | 없음 | `NOT_IMPLEMENTED_SOURCE_LABEL_SENSITIVE` |
| 14 | `member.veteran_status` | 보훈 | 없음 | 없음 | `NOT_IMPLEMENTED_SOURCE_LABEL_SENSITIVE` |

`나이`와 `생년월일`, 전체 `주소`와 `시/도·시군구 수준 지역`, `학교`와 복합 `education`, 전체
경력과 경력연차는 동의어로 자동 병합하지 않는다. 이 매핑을 승인하기 전에는 필드 수를 서로
상쇄하거나 하나로 세지 않는다.

### 2.2 기업DB — 9개

| # | 논리 ID | 화이트보드 필드 | 현재 물리 매핑 | 현재 LLM 경로 | 구현 대조 상태 |
|---:|---|---|---|---|---|
| 1 | `company.name` | 사명 | `Company.name` | `company_context.company_name` | `IMPLEMENTED` |
| 2 | `company.business_registration_number` | 사업자번호 | 없음 | 없음 | `NOT_IMPLEMENTED` |
| 3 | `company.contact.email` | 담당자 이메일 | `User.email`이 회원 DB에 존재하며 `User.company_id`로 논리 연결 | 회사 설명 context에는 없음 | `IMPLEMENTED_IN_OTHER_DB` |
| 4 | `company.contact.phone` | 담당자 전화번호 | 없음 | 없음 | `NOT_IMPLEMENTED` |
| 5 | `job.preference.certificate` | 우대사항: 자격증 | 명시 column 없음 | 없음 | `NOT_IMPLEMENTED` |
| 6 | `job.preference.major` | 우대사항: 전공 | 명시 column 없음 | 없음 | `NOT_IMPLEMENTED` |
| 7 | `job.preference.education_completion` | 우대사항: 교육 이수 | 명시 column 없음 | 없음 | `NOT_IMPLEMENTED` |
| 8 | `job.preference.career` | 우대사항: 경력 | `Job.min_experience`는 최소요건으로 존재하나 우대경력과 동일하지 않음 | score와 `score_breakdown`에 반영 | `PARTIAL_NON_EQUIVALENT` |
| 9 | `job.requirements` | 자격요건 | `Job.summary`, `required_skills`, `min_experience`로 부분 표현 | 제목·요약은 company context, 기술·경력은 score envelope에 포함 가능 | `PARTIAL_COMPOSITE` |

`Company.opendart_corp_code`는 OpenDART 고유번호이고 사업자등록번호가 아니다.
`Company.opendart_snapshot`도 공개 projection만 저장하므로 이 둘을 화이트보드의 `사업자번호`로
대체하지 않는다.

## 3. 현재 PostgreSQL 물리 스키마

화이트보드 필드만 보여 주면 현재 런타임에 추가로 존재하는 운영·참조·감사 필드가 사라지므로,
`src/runtime/api/app/models.py`의 column을 별도 inventory로 둔다.

### 3.1 `jcareer_member`

| 테이블 | 현재 column |
|---|---|
| `users` | `id`, `email`, `password_hash`, `display_name`, `role`, `company_id`, `active`, `withdrawn_at`, `created_at` |
| `consent_events` | `id`, `user_id`, `consent_type`, `action`, `policy_version`, `collected_items`, `purposes`, `legal_basis`, `occurred_at` |
| `resumes` | `id`, `user_id`, `phone`, `birth_date`, `address_region`, `education`, `desired_role`, `years_experience`, `skills`, `certificates`, `self_intro`, `updated_at` |
| `applications` | `id`, `job_id`, `candidate_id`, `status`, `applied_at`, `updated_at` |
| `audit_events` | `id`, `event_type`, `actor_user_id`, `actor_role`, `company_id`, `target_type`, `target_ref`, `purpose`, `action`, `result`, `correlation_id`, `retention_class`, `detail`, `occurred_at` |

### 3.2 `jcareer_company`

| 테이블 | 현재 column |
|---|---|
| `companies` | `id`, `name`, `address`, `direction_statement`, `declared_values`, `profile_version`, `opendart_corp_code`, `opendart_snapshot`, `opendart_sync_state`, `opendart_snapshot_version`, `opendart_synced_at`, `opendart_last_attempt_at`, `status`, `created_at` |
| `jobs` | `id`, `company_id`, `title`, `summary`, `location`, `employment_type`, `required_skills`, `min_experience`, `status`, `created_at`, `updated_at` |

이 물리 inventory에는 인증·감사·외부 snapshot 메타데이터가 포함되므로 화이트보드의 업무 필드
23개와 단순 총개수 비교를 하지 않는다.

## 4. 현재 matcher와 LLM 설명 payload

### 4.1 점수 입력

결정론적 matcher가 지원자 측에서 사용하는 값은 다음 세 가지다.

- `skills`
- `years_experience`
- `desired_role`

이름·전화번호·이메일·생년월일·주소·학교/학력·자격증·자소서는 점수에서 제외된다.
화이트보드에 새로 나타난 장애·신체·보훈도 현재 모델과 점수 입력에 없다.

### 4.2 설명 요청의 명시 context

| context | 현재 key 수 | key |
|---|---:|---|
| `candidate_context` | **8** | `name`, `phone`, `email`, `birthdate`, `address`, `school`, `certificates`, `self_intro` |
| `company_context` | **6** | `company_name`, `direction_statement`, `declared_values`, `profile_version`, `job_title`, `job_summary` |

Gateway의 현재 `PII_FIELD_NAMES`는 candidate context 8개 중
`name`, `phone`, `email`, `birthdate`, `address`, `school` **6개만** 표시한다. 이는 코드의 계수
규칙이지, 나머지 두 필드가 개인정보가 아니라는 판정이 아니다.

### 4.3 현재 8/6 계수 밖의 candidate-derived material

`ExplanationItem`은 두 context 외에도 다음 값을 provider용 항목과 raw prompt material에 넣는다.

- `subject_ref`: 기업의 지원자 추천 경로에서는 candidate UUID
- `score`와 `score_breakdown`: 후보 경력연차와 직무 일치 근거가 문장·details에 포함될 수 있음
- `matched_feature_ids`, `matched_feature_labels`: 일치 기술, 경력, 희망 직무 표현이 포함될 수 있음

현재 `prompt_fields_prepared`와 `pii_fields_prepared`는 `candidate_context`의 최상위 key만 센다.
따라서 **8개 준비/6개 분류**는 전체 provider payload의 candidate-derived field 수가 아니다.

## 5. LLM02 측정 모수 계약

현 시점에 사실로 고정할 수 있는 수치는 다음뿐이다.

| ID | 값 | 의미 |
|---|---:|---|
| `WB_MEMBER_LOGICAL_FIELD_COUNT` | **14** | 화이트보드 회원DB 최소 논리 필드 수 |
| `WB_COMPANY_LOGICAL_FIELD_COUNT` | **9** | 화이트보드 기업DB 최소 논리 필드 수 |
| `RUNTIME_CANDIDATE_CONTEXT_KEY_COUNT` | **8** | 현재 API가 설명 context에 준비하는 지원자 key 수 |
| `RUNTIME_COMPANY_CONTEXT_KEY_COUNT` | **6** | 현재 API가 설명 context에 준비하는 기업 key 수 |
| `RUNTIME_COUNTER_FLAGGED_KEY_COUNT` | **6** | 현재 gateway field-name counter가 표시하는 수 |
| `FULL_CANDIDATE_DERIVED_PROVIDER_FIELD_COUNT` | `DECISION_PENDING` | context 밖의 ID·score breakdown·label과 의미 매핑을 포함한 전체 수 |

따라서 `6 / 14` 같은 비율은 계산하지 않는다. 현재 6개에는 화이트보드 회원DB에 없는 전화번호와
생년월일이 들어가고, 화이트보드 14개 중 경력은 별도 score envelope를 통해 나갈 수 있으며,
나이↔생년월일 같은 의미 매핑도 승인되지 않았기 때문이다.

AI-V01/LLM02를 재측정하기 전 사람이 다음을 확정해야 한다.

1. 계수 단위를 DB column, 논리 업무 필드, 직렬화 key, 값의 의미 중 무엇으로 할지
2. `subject_ref`, score breakdown, matched label처럼 context 밖에서 파생된 지원자 정보를 포함할지
3. 나이↔생년월일, 학교↔education, 주소↔address_region, 경력↔years_experience 매핑
4. 자격증·자소서와 기업 담당자 이메일·전화번호의 분류와 사용 목적
5. 후보자 추천과 기업 추천을 route별로 따로 셀지
6. AS-IS 6→TO-BE 2 목표를 유지할 경우 어떤 두 필드가 목적상 필요한지와 승인자

## 6. 변경 통제

이 문서 신설로 다음 구현을 자동 변경하지 않는다.

- 회원·기업 DB column 추가 또는 이동
- 장애·신체·보훈·병역·학점·프로젝트 수집
- 해당 필드의 matcher·LLM 입력 사용
- 현재 70/20/10 산식 또는 추천 순위
- OpenDART 고유번호를 사업자등록번호로 취급

필드 수집·동의·점수·LLM 전송 변경은 승인된 기준선과 측정 계약이 생긴 뒤 별도 구현한다.
