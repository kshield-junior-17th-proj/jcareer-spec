# J-Career AS-IS 합성 런타임 명세

**기준일:** 2026-08-28
**상태:** 코드·로컬 합성 재현환경 명세. 실제 J사 운영 서비스나 AWS 배포 상태가 아니다.

이 문서는 `src/runtime/**` 코드와 `terraform/asis/**` 모델을 한곳에서 대조한다. ISMS 또는
ISO/IEC 42001의 충족 여부, 적합성, 잔여위험 수준을 판정하지 않는다. 실제 개인정보·기업정보,
실제 자격증명은 입력하지 않는다.

## 0.1 2026-08-28 조직 관찰값과 이 명세의 경계

신규 화이트보드 통합 판독에는 CEO 아래 전략기획 10명, 명칭 미해결 80명 부서,
경영지원 30명, CS팀 15명, 마케팅 15명으로 총 150명이 적혀 있다. 80명 부서 아래에는
채용사이트 30명, **AI서비스 20명**, 정보보안팀 30명이 있고, AI서비스는 개발·서비스운영·
DevOps 기능을 자체 보유한다. 이 값은 현재 `OBSERVED_WHITEBOARD_2026_08_28`이며 기존
`context/raw/SCENARIO_FACTS-가상고객사J사.md#3`을 대체할지는 사람 결정 대기다.

따라서 이 명세에서 `web`·`api`·`agent`·`llm-gateway`는 **기술 배포 단위**이고 AI서비스
조직의 하위 기능이나 인원과 1:1 대응하지 않는다. 조직도만으로 ECS 서비스 수, replica 수,
내부 API, 점수 산식 또는 DB 경계를 바꾸지 않는다. 신규 조직이 기준선으로 승인되면 같은
80명 부서 안의 AI서비스와 정보보안팀 사이에서 검토 책임과 독립성을 따로 배정해야 한다.
80명 노드명과 정보보안팀 첫 기능 명칭은 미해결 상태를 유지한다.

문서별 영향과 결정 항목은
[`WHITEBOARD_IMPACT_ASSESSMENT_2026-08-28.md`](../../context/findings/WHITEBOARD_IMPACT_ASSESSMENT_2026-08-28.md)에
기록한다.

## 0.2 2026-08-28 멘토 제안 조직안과 학습 경계

Notion의 [`8/28 멘토 회의`](https://app.notion.com/p/3ca0be5710e8805badf9c7fa7c8f762b?pvs=204)
`0828 회의록 정리본`에는 화이트보드 관찰 조직을 그대로 확정하는 대신 다음 목표 조직 후보가
기록돼 있다.

- **DevOps를 별도 팀으로 두지 않고**, AI서비스의 DevOps 업무를 **인프라팀** 책임으로 옮기며
  인프라팀 안에 **SI팀**과 **데이터팀**을 둔다.
- 정보보안팀을 **Blue · Red · Compliance** 기능으로 구분한다.
- AI서비스팀이 `agent`를 자체 학습시키는 조직으로 표현하지 않는다.

이는 `MENTOR_PROPOSED_HUMAN_DECISION_PENDING`이며 §0.1의 화이트보드 관찰값이나 기존 시나리오
기준선을 자동 교체하지 않는다. 인프라팀 인원·보고선, SI·데이터·DevOps의 책임 범위,
Blue·Red·Compliance가 조직명인지 기능 구분인지도 사람 결정 대기다. 따라서 아래의 `agent`는
계속 결정론 점수 서비스다. `src/mlops/**`에는 기존 DB 비연계 생성형 예시와 별도로, 합성
회원DB·기업DB를 읽는 일회성 challenger와 S3 숫자 특징 snapshot을 읽는 Lambda 경로가 있다. 이 경로는 모델을
운영 `agent`에 배선하거나 자동 승격하지 않으며 AWS 실행도 주장하지 않는다. 조직·자산·학습·CEO 보고 후보의 통합 경계는
[`mentor_feedback_2026_08_28.json`](contracts/mentor_feedback_2026_08_28.json)에 기록한다.

구현 우선순위는 조직도가 아니라 **AI 서비스 사실 경계**다. 조직안은 변경 가능한 참고
컨텍스트로만 남기고, 결정론 점수·Bedrock 설명 전용·회원DB/기업DB 분리·현재 전송 key 계수·
승인 allowlist 대기·실제 이용자 데이터 학습 금지·합성 MLOps의 운영 순위 미배선은 조직 변경과 무관한
런타임 불변조건으로 유지한다.
정보보호시스템은 [`INFORMATION_PROTECTION_SYSTEM_INVENTORY.md`](INFORMATION_PROTECTION_SYSTEM_INVENTORY.md)에서
기존 시나리오·source 모델·멘토 요청 미확인 후보를 나누어 관리한다.

## 1. 행위자와 제품 경계

| 행위자 | 현재 구현된 목적 | 현재 경계 |
|---|---|---|
| 지원자 | 가입, 동의, 지원자 홈, 이력서, 공고 탐색·지원, 추천·점수 설명, 탈퇴 | 합성 계정·데이터만 사용 |
| 기업 고객 담당자 | 기업 가입, 기업 방향·가치 프로필, 공고, 지원자 파이프라인, 조건 일치 결과, 운영 홈 | 가입 시 기업과 첫 담당자 하나를 생성하지만 기업별 담당자 수 제약은 없음 |
| 플랫폼 운영자 | 합성 감사 이벤트 조회 | 관리자 역할 한 종류 |
| 컨설턴트 | 승인된 내부용 비식별 snapshot 읽기 | 별도 `dashboard/`; 런타임/AWS 직접 조회 없음 |

기업 고객은 지원자와 별도의 고객 측이다. 다만 조직 멤버십, 초대, 기업 관리자·검토자
역할, 담당자 퇴사·권한 회수, 기업 확인 게이트는 구현되지 않았다. 별도 VPC가 이 애플리케이션
tenant·membership 경계를 대신하지 않는다.
신규 기업은 별도 검토 전환 없이 `Company.status` 모델 기본값 `approved`로 생성된다. 이는 현재
소스 상태의 선언이며, 기업 확인이나 승인 절차가 수행됐다는 뜻이 아니다.

## 2. 서비스 책임

| 배포 단위 | 책임 | 직접 데이터 저장소 | Terraform 대응 |
|---|---|---|---|
| `web` | 지원자·기업·관리자 SPA | 없음 | ECS service와 ECR URI 문자열 배선; 실제 build/push·digest 검증 없음 |
| `api` | 인증·인가, 양측 업무 API, 두 DB 조합, 캐시, matcher·설명 호출 | 회원 DB, 기업 DB, Redis | ECS service와 DB URL 계약; 서비스 발견 등 미배선 |
| `agent` | 결정론적 70/20/10 점수·정렬 | 없음 | ECS service 정의; 공개 ALB 경로가 모델에 남음 |
| `llm-gateway` | 점수와 분리된 설명, 기업 방향 직접 일치 표현, provider adapter, raw prompt 기록 | 로컬에서는 `prompt-logs` volume | ECS service 정의; Fargate 영속 저장소 미모델링 |
| `mlops-exporter` / `mlops-lambda` | DB 옆에서 합성 회원·기업 특징 5개 추출 / 엄격한 S3 snapshot 검증, 소형 challenger 학습, 합성 오프라인 비교 산출 | S3 source·result, DynamoDB run-state adapter | 별도 `terraform/serverless-mlops`; 기본 0-resource, AWS 실행·운영 모델 배선 없음 |
| PostgreSQL | 회원·기업 논리 DB | 아래 데이터 소유 표 참조 | 같은 RDS Primary/Replica; 기업 DB bootstrap 미구현 |
| Redis | 추천 응답 24시간 캐시 | 후보자·기업 추천 payload | ElastiCache 모델; API endpoint 주입 미구현 |

Compose가 호스트에 publish하는 web·API·agent·gateway 포트는 기본값으로 loopback에만
바인딩되고, DB·Redis는 host port가 없다. `WEB_BIND_ADDRESS` override로 web 노출을 넓힐 수
있으나, 내부 `agent`·`llm-gateway` 경로에는 애플리케이션 인증이 없으므로 이 구성을 LAN·
인터넷에 노출하는 실행 계약으로 사용하지 않는다.

## 3. 데이터 소유권

| 논리 DB | 소유 엔터티 | 비고 |
|---|---|---|
| `jcareer_member` | `User`, `ConsentEvent`, `Resume`, `Application`, `AuditEvent` | 지원자와 기업 담당자 identity를 함께 보유 |
| `jcareer_company` | `Company`, `Job` | 기업 방향·선언 가치·profile version 포함 |

로컬 Compose에서는 두 DB가 서로 다른 database와 app role을 사용하고 반대 DB `CONNECT`를
회수한다. 교차 DB foreign key나 ORM relationship은 없다. API의 routing session만 두 engine을
조합한다. 같은 RDS·보안그룹·백업·장애 경계를 공유하며, 두 DB를 건드리는 한 번의 commit은
원자적이지 않다. Terraform은 기업 DB와 전용 role bootstrap을 아직 실행하지 않는다.

기업 담당자의 `User.company_id`와 지원 관계의 `Application.job_id`는 opaque 논리 참조다. 현재
구조가 별도 identity realm이나 조직 membership을 구현했다는 뜻은 아니다.

화이트보드 업무 필드, 현재 물리 column, matcher 입력과 설명 provider 입력의 대응은
[`DB_FIELD_CATALOG.md`](DB_FIELD_CATALOG.md)에 분리해 둔다. 화이트보드 논리 필드가 현재
DB에 구현됐거나 수집·전송이 승인됐다는 뜻은 아니다.

## 4. 외부 업무 API

실행 시 FastAPI가 `/docs`와 `/openapi.json`을 생성한다. 아래 표는 코드 라우트의 역할 경계다.
`contracts/api_surface.json`은 세 서비스의 33개 handler·38개 route tuple, 요청 model 선언,
인증 role source와 선택된 tenant selector, 기업 계정 수명주기·현재 지원자료 참조·추천 audit·
cache payload 검증의 선택된 source state를 AST fingerprint와 대조한다. 상태는
`SOURCE_DECLARATION_NOT_EXECUTION_EVIDENCE`·`AST_PARTIAL`이다. 현재 OpenAPI에는 security scheme과
정밀 response/error model이 없고 operation별 완전한 DB read/write graph도 아니므로 이 inventory를
완전한 wire API 계약이라고 부르지 않는다. operation의 legacy `required_calls` 필드는 handler AST에
선택된 호출 symbol이 존재한다는 뜻일 뿐, cache hit 같은 모든 분기에서 실행된다는 뜻이 아니다.

`contracts/api_effects.json`은 33개 handler 전부에 대해 회원/기업 DB, audit, Redis, agent,
llm-gateway, prompt log 효과와 분기 설명을 별도로 고정한다. 전 handler와 14개 helper의 AST 지문,
기업 가입·양측 추천 cache 순서·기업 overview/pipeline/admin 열람 감사·gateway prompt/provider 순서의
선택된 9개 lexical marker를 검사한다. 이는 CFG dominance, 실제 cardinality, multi-bind commit의
원자성, downstream 수신 또는 실행 trace를 증명하지 않는다.

`contracts/api_wire_shapes.json`은 같은 33개 handler의 직접 `return` 표현식과 handler 안에
직접 적힌 literal `HTTPException`만 AST에서 추출한다. 38개 decorator route는 alias를 포함한
route 수이고 별도 handler로 다시 세지 않는다. literal object의 최상위 key 외에 nested shape를
펼치지 않으며 helper call·local name·cache 반환은 각각 미확장 상태로 둔다. 따라서 빈 직접 오류
목록은 operation이 실패하지 않는다는 뜻이 아니고 dependency·helper·downstream·422·500·header·
serialization을 열거하지 않는다. 직접 detail 문자열도 제품 안정 API code가 아니다. 이 catalog는
response model 강제나 실제 HTTP 응답·Bedrock 호출의 증거가 아니다.

브라우저와 API의 현재 신원 원천은 같지 않다. 브라우저는 시작할 때 `jcareer_token`과
`jcareer_user`를 `localStorage`에서 복원하고, 저장된 `user.role`로 보호 화면과 메뉴를 고른다.
복원 시 role enum 자체를 검증하지 않지만 `Protected`는 경로별 허용 role 목록과 저장된 role을
비교한다. 이 비교의 입력도 서버 재검증 값이 아니라 local storage 값이라는 한계가 있다.
기존 `GET /api/v1/auth/me`를 시작 시 호출하지 않으며 다른 탭의 storage 변경을 동기화하지 않는다.
반면 보호 API는 token의 `sub`로 활성 회원 DB `User`를 다시 조회하고, token의 `role` claim이 아니라
현재 DB `User.role`로 권한을 검사한다. 따라서 stale·변조된 브라우저 user가 잘못된 역할 UI를
보여 줄 수 있다는 source state와 서버 권한 우회가 확인됐다는 주장은 분리한다.

현재 token은 `{sub, role, exp}`를 담는 custom two-part HMAC-SHA256 형식이며 기본 TTL은 43,200초다.
소스에는 고정 합성 signing-key fallback이 있고 `iat`·`jti`, 서버 session registry, refresh,
logout·개별 token revoke route가 없다. 브라우저 logout은 local storage만 지운다. 401 처리 중
미저장 입력 경고를 사용자가 취소하면 local session 제거도 취소된다. `parse_token`은 `exp`를
확인하지만 `sub` 형식을 lookup 전에 검증하지 않아, 유효하게 서명됐지만 `sub`가 없는 payload는
guard 밖의 `KeyError` 경로를 가진다. 이 단락은 함수 fingerprint와 lexical marker로 고정한
source-only 관찰이며 실제 token 악용·브라우저 상태 전이·운영 노출을 실행 검증한 결과가 아니다.

UI는 저장소가 비어 있는 최초 방문과 손상·부분 세션을 구분해 후자에 재로그인 안내를 남기고,
일반 logout 뒤에는 실제 local storage 삭제 성공 여부에 따라 “이 브라우저”의 저장 정보 삭제 또는
삭제 확인 실패를 구분해 표시한다. 안내 live region은 빈 상태부터 유지하고 닫은 뒤 본문 제목으로
focus를 복원한다. 로그인 요청 중에는 form 밖의 polite status와 form `aria-busy`를 갱신하고 데모
계정 중복 요청을 막는다. 지원자·기업 가입 form도 API 입력 길이와 맞는 min/max 경계, email
autocomplete·spellcheck 상태, form `aria-busy`, form 밖 polite status를 source 계약으로 둔다.
브라우저 API client는 401 신호를 body decode보다 먼저 발행하고 body를 text로 한 번 읽은 뒤
JSON·일반 text·204/205·빈 성공 body·malformed JSON을 구분한다. decoder의 7개 순수 `Response`
stub 회귀는 실제 브라우저 navigation, 서버 응답 또는 network 실행 증거가 아니다.
이 피드백은 `/auth/me` 재검증, 서버 token 철회 또는 교차 탭 동기화를 추가하지 않는다.

`/candidate/home`은 이력서·지원 현황·동의 API의 현재 응답을 한 화면에 모으고, 실패한 자료는
나머지 화면과 구분해 표시한다. 프로필 입력률은 다섯 구조화 항목의 입력 여부일 뿐 추천 점수나
품질 지표가 아니다. 최근 지원 흐름도 지원 시점 snapshot, 결과 예측 또는 데이터 정합성 판정이
아니다.

| 역할 | Method / path | 기능 |
|---|---|---|
| 공개 | `GET /health` | 두 논리 DB 연결을 포함한 API health |
| 공개 | `GET /api/v1/runtime` | 합성 runtime·dataset·provider·계약 버전 표시 |
| 공개 | `POST /api/v1/auth/signup` | 지원자 identity 생성 |
| 공개 | `POST /api/v1/auth/signup/recruiter` | 기업과 가입 요청의 첫 담당자를 split write로 생성 |
| 공개 | `POST /api/v1/auth/login` | 역할 포함 세션 token 발급 |
| 인증 | `GET /api/v1/auth/me` | 현재 identity와 기업 연결 조회 |
| 공개 | `GET /api/v1/jobs` | 공개 중인 공고의 제목·요약·요구 기술과 지역 탐색 |
| 공개 | `GET /api/v1/jobs/{job_id}` | ID로 공고 상세 조회; 현재 status 제한 없음 |
| 지원자 | `POST/GET /api/v1/candidates/me/consents` | 동의 이벤트 기록·조회 |
| 지원자 | `DELETE /api/v1/candidates/me/consents/{consent_type}` | 동의 철회 이벤트 기록 |
| 지원자 | `GET/POST /api/v1/candidates/me/resume` | 이력서 조회·저장 |
| 지원자 | `POST /api/v1/jobs/{job_id}/applications` | 공고 지원 |
| 지원자 | `GET /api/v1/candidates/me/applications` | 본인 지원 목록 |
| 지원자 | `GET /api/v1/candidates/me/recommendations` | 공고 점수·분해·별도 설명 |
| 지원자 | `DELETE /api/v1/candidates/me` | 주 DB 탈퇴 처리 시작 |
| 기업 | `GET /api/v1/recruiter/overview` | 자기 회사 공고·지원·단계 집계와 고객·데이터 경계 |
| 기업 | `GET/PUT /api/v1/recruiter/company-profile` | 회사 방향·선언 가치 version 조회·갱신 |
| 기업 | `GET/POST /api/v1/recruiter/jobs` | 자기 회사 공고 목록·생성 |
| 기업 | `PUT /api/v1/recruiter/jobs/{job_id}` | 자기 회사 공고 수정 |
| 기업 | `GET /api/v1/recruiter/jobs/{job_id}/pipeline` | 자기 공고 지원자 파이프라인 |
| 기업 | `PATCH /api/v1/recruiter/applications/{application_id}` | 전형 상태 변경 |
| 기업 | `GET /api/v1/recruiter/jobs/{job_id}/recommendations` | 지원자 점수·분해·별도 설명 |
| 운영자 | `GET /api/v1/admin/audit` | 합성 감사 이벤트 필터 조회 |

기업 경로는 `user.company_id`와 공고의 `company_id`를 대조해 다른 기업 객체 접근을 거부한다.
이는 조직 멤버십·세분 역할·기업 상태 수명주기를 구현했다는 뜻은 아니다.
기업 홈은 이 차이를 숨기지 않도록 담당자와 기업의 논리 연결, 가입 시 첫 담당자 생성,
기업별 담당자 수를 강제하는 DB 제약 부재, 조직 멤버십·역할 수명주기 미구현,
기업 담당자 탈퇴·소유권 이전, 기업 동의, 상태 전환 API·변경 주체가 없다는 사실을 각각의
boolean source state로 표시한다. 가입 시 별도 검토 전환 없이 모델 기본값 `approved`를 사용하는
상태, `Company.status` 원본 문자열, 업무 API 권한 게이트 미적용도 각각 분리한다. 이 미적용은 기업
화면만의 경계가 아니다. 공개 공고 목록·상세, 지원 제출·현황, 지원자 추천도 `Company.status`를 확인하지
않는 현재 source state로 별도 계약에 고정한다. 데이터 경계에는
`Application.job_id`가 교차 DB foreign key 없는 논리 UUID 참조이며,
원자적 커밋과 가입 operation ID·멱등 키·보상·사후 조정·outbox가 구현되지 않았다는 현재
source state를 각각 표시한다.

공고와 이력서 기술 목록은 공백·대소문자·구두점을 제거한 matcher comparison key로 중복을
정리한다. 최초 이력서 생성과 중복 지원의 unique 경쟁은 500 대신 재저장 또는 409 계약으로
수렴한다. 이는 조직 membership이나 기업 상태 게이트를 추가한 것이 아니다.

## 5. 내부 API

| 서비스 | Method / path | 입력과 출력 |
|---|---|---|
| agent | `POST /internal/match/jobs` | 지원자 구조화 항목 + 공고 목록 → 공고 점수·분해·정렬 |
| agent | `POST /internal/match/candidates` | 공고 구조화 항목 + 지원자 목록 → 지원자 점수·분해·정렬 |
| gateway | `POST /internal/explanations` | matcher 결과 + 지원자/기업 context → 설명·직접 일치 표현 |

각 서비스는 prefixed alias(`/agent/internal/*`, `/llm/internal/*`)도 갖는다. 현재 내부 호출 인증은
없다. Terraform ALB에도 agent와 gateway의 공개 경로가 남아 있어, AWS 실행 계약을 설계할 때
내부 전용 경로와 외부 경로를 사람이 먼저 확정해야 한다.

## 6. 지원자 추천 흐름

```text
지원자 세션
  → 최신 privacy_core 동의 확인
  → 회원 DB에서 Resume 조회
  → 기업 DB에서 공개 Job + Company profile 조회
  → Redis cache 조회
  → agent: desired_role / skills / years_experience만 점수 계산
  → llm-gateway: 점수 결과와 추가 context로 설명 생성
  → 점수·score_breakdown·설명을 분리해 응답
```

후보자 cache key에는 이력서 갱신 시점과 열린 공고의 식별자·기업 profile version·제목·본문·
지역·고용형태·요구 기술·최소 경력·상태·갱신 시점의 canonical hash가 들어간다. 이 재료가
바뀌면 새 키를 사용한다. 이 계약은 기업 추천 cache에 그대로 적용되지 않는다. 기업 경로의
지원자 집합·이력서 version 누락과 stale 관찰은 다음 절의 별도 AS-IS 경계다.

## 7. 기업 고객 추천 흐름

```text
기업 담당자 세션
  → 자기 회사 공고인지 확인
  → Redis cache 조회
  ├─ cache hit: 저장된 후보자 payload·score_breakdown·설명을 즉시 응답
  └─ cache miss: 회원 DB에서 해당 공고의 활성 지원자 + Resume 조회
       → agent: 공고 구조화 항목과 각 지원자 구조화 항목으로 점수 계산
       → llm-gateway: 점수 결과와 지원자/기업 context로 설명 생성
       → 후보자 payload·score_breakdown·설명을 분리해 응답
```

기업 추천 경로에는 최신 지원자 동의 확인, 추천 화면 열람 audit, 지원자 집합·이력서 version을
포함한 cache key가 없다. 특히 cache hit는 지원자 활성 상태·탈퇴·이력서 변경을 다시 조회하지
않으므로, 만료 전 저장된 후보자 payload가 그대로 반환될 수 있다. 파이프라인 응답과 펼침 화면은
조회 시점의 현재 연락처·생년월일·
주소·학력·자기소개를 포함한 resume payload를 제공한다. 지원 시점 스냅샷이 아니며 펼침 동작
자체의 별도 audit도 없다. 이 데이터 범위와 기록 단위를 위험 시연으로 보존할지 수정 누락으로
볼지는 사람이 `P1-C04`에서 결정해야 한다.

기업 추천 웹 화면은 이 API 응답을 새 후보자 검색 원천으로 넓히지 않는다. 이미 반환된 지원자만
이름·희망 직무·등록 기술과 최소 표시 점수로 좁혀 보며 원래 서버 순서를 유지한다. 담당자는 최대
3명의 총점과 기술·경력·직무 기여도를 한 표에서 임시 비교할 수 있다. 선택값은 브라우저 메모리에만
있고 서버 저장·공유·shortlist·채용 결정 이벤트를 만들지 않는다. 따라서 이 화면을 플랫폼 전체
인재 소싱이나 기업 적합성 판정 구현으로 읽지 않는다.

## 8. 점수와 설명 계약

```text
총점 = 기술 일치 최대 70 + 경력 조건 최대 20 + 희망 직무 연관 최대 10
```

- 산식 version: `deterministic-70-20-10-v1`
- score breakdown: 기술·경력·직무 원시 기여도와 표시값
- 점수 미사용: 이름, 연락처, 이메일, 생년월일, 주소, 학교/학력, 자격증, 자기소개
- 설명 입력: cache miss의 현재 요청에서는 API가 위 필드와 기업명·방향·선언 가치·공고 요약을
  요청에 준비한다. 명시적인 candidate context는 8개 key이고 현재 field-name counter는 그중
  6개를 표시한다. 그러나 `subject_ref`, score breakdown, matched label에도 지원자 파생 정보가
  포함될 수 있으므로 이 8/6을 전체 LLM02 모수로 읽지 않는다. 정확한 계수 경계는
  [`DB_FIELD_CATALOG.md`](DB_FIELD_CATALOG.md)를 따른다. 빈 추천 집합에는 필드를 준비하지 않는다.
  cache hit는 원본 요청의 준비 필드 집합을 현재 cache envelope만으로 검증할 수 없으므로 빈 배열과
  별도 미검증 상태를 반환한다. 화면은 외부 공급자의 실제 수신을 단정하지 않고 이 상태와 gateway
  확인 상태를 따로 표시한다.
- 기업 방향 결과: 문자열 직접 일치 기반이며 `score_effect=NONE`
- cache miss의 설명 경로 연결·HTTP·JSON·계약 검증 또는 gateway/외부 공급자 경로 unavailable/invalid:
  추천 목록·순서·점수 유지, 설명과 `company_alignment`는 함께 비어 legacy 상태
  `UNAVAILABLE_PROVIDER`로 축약된다. 이 상태만으로 외부 공급자 장애를 주장하지 않는다.
- warm cache hit: 과거 설명을 반환하고 현재 provider 상태는 재확인하지 않는다. 응답은
  `CACHE_HIT_PROVIDER_NOT_REVALIDATED`로 이 한계를 표시한다. 설명 시도 메타의 gateway 상태도
  `CACHE_ENTRY_ACCEPTED_ORIGIN_NOT_VERIFIED`로 두어, 현재의 얕은 cache envelope 검사를 과거
  gateway 응답 검증 증거로 표현하지 않는다. 장애 중 과거 설명을 계속 보여 줄지는 사람의 제품
  결정이 남아 있다.
- 생성 문장 의미 검증: `NOT_IMPLEMENTED_ASIS`

현재 70/20/10은 플랫폼 고정값이지 기업별·공고별 승인 가중치가 아니다. “이 기업이 이 요소를
중시해 가산점을 줬다”는 문구를 만들 근거가 없다. 기업별 정책을 채택하려면 승인자, version,
변경 이력, rollback, 후보자 공개 범위와 평가 데이터를 사람이 먼저 정해야 한다.

## 9. Bedrock 경계

Bedrock Converse adapter는 기존 `llm-gateway` 코드 안에만 있다. 기본 provider는
`local-synthetic-stub`, `ALLOW_BEDROCK_LIVE=false`다. `terraform/asis`에는 Bedrock invoke IAM,
gateway 전용 task role, 내부 호출 인증, 호출량 제한, 승인된 처리 리전 계약이 없다.
API와 gateway는 provider·설명 계약·Bedrock client region·model reference의 canonical 구성 지문을
공유하고 추천 cache key와 gateway 응답 검증에 결속한다. 외부 응답에는 model reference 원문 대신
hash를 쓰며, 이 지문은 실제 호출·수신·처리 리전을 증명하지 않는다.
adapter가 응답을 받더라도 exact `items` object, 요청 subject 집합, 문자열·길이 경계를
통과하지 못하면 gateway는 설명 요청을 실패로 처리한다. 이 형식 검사는 생성 문장의 사실성·
충실도·법적 의미를 검증하는 장치가 아니다.
별도 `terraform/lab`에는 조건부 IAM 정책 초안이 있지만, Docker container가 EC2 profile
자격증명을 받는 경계를 해결하지 못했다. IMDSv2 hop 1에서는 container 자격증명이 실패할 수
있고 hop 2만 적용하면 다른 container로 role 접근면이 넓어질 수 있어, Terraform validation과
배포 스크립트가 live 요청을 차단한다. 따라서 provider와 live flag만 바꾸어 AWS에서 동작한다고
주장하지 않는다.

### 9.1 합성 DB 기반 서버리스 MLOps 경계

`src/mlops`에는 SageMaker 없이 한 번 실행되는 Lambda 호환 학습 경로가 있다. 합성 회원DB의
후보자·이력서·지원 상태와 합성 기업DB의 기업 방향·공고를 읽고, 다음 5개 숫자 특징만 dataset에
기록한다.

- 기술 일치, 경력 조건, 직무 표현 일치
- 자소서와 공고의 토큰 겹침
- 자소서와 기업 방향·선언 가치의 토큰 겹침

뒤의 두 값은 임베딩 의미 유사도가 아닌 토큰 겹침 proxy다. Bedrock은 현재 별도 설명 경로에서만
정성 근거를 문장화하고 이 학습 특징이나 점수·순위를 바꾸지 않는다.

이름·이메일은 source lineage digest 입력일 뿐 feature가 아니다. 연락처·생년·주소·학교·자격과
자소서·기업 방향·공고 원문은 artifact에 기록하지 않는다. 지원 상태는
`pipeline_progression_proxy`로만 사용하며 지원자 품질이나 합격 확률을 뜻하지 않는다. 현재
`privacy_core`의 `ai_recommendation` 목적도 학습 동의로 해석하지 않는다. 따라서
`JCAREER_SYNTHETIC_ONLY` 표식과 예약 이메일·합성 전화가 있는 랩 데이터만 처리한다.

별도 `terraform/serverless-mlops`는 DB URL·DB 비밀번호·VPC 연결 없이
`mlops/sources/{run_id}/`의 정확한 3개 숫자 특징 파일을 읽는 on-demand Lambda, private S3,
DynamoDB run-state, ECR, 로그·IAM만 선언한다. S3 암호화는 현재 SSE-S3이며 KMS는 배선하지 않았다.
기본 `disabled` 계획은 managed resource 0개고,
bootstrap/runtime에는 정확한 사람 활성화 문구가 필요하다. EventBridge schedule과 자동 승격은 없다.
소스 검증·0-resource plan은 통과했지만 AWS apply·이미지 push·Lambda 실호출 증거는 없다.
최종 상태는 `TRAINED_PENDING_HUMAN_REVIEW`이며 운영 `agent`는 이 모델을 읽지 않는다. 현재 AS-IS
Gateway의 원문 prompt 동작도 이 MLOps 특징 최소화로 바뀌지 않는다.

활성화·event·환경 설정 검증과 최초 `RUNNING` 조건부 쓰기는 실패 상태 기록 경계 앞에 있다.
따라서 pre-state 거부·중복 run ID·최초 DynamoDB 쓰기 실패는 `FAILED_SAFE` 없이 끝날 수 있고,
`RUNNING` 이후의 snapshot 검증·학습·저장 실패만 `FAILED_SAFE` 전이를 시도한다.

## 10. 감사·보존·장애 관찰면

다음은 구현 사실을 재현할 수 있는 표면이며, 통제 판정 목록이 아니다.

- 추천 correlation ID는 cache miss 응답에 있으나 prompt 기록은 gateway handler 진입 시에만
  생기며, `match_run` AuditEvent와 연결되지 않음
- cache hit는 이전 correlation ID가 든 응답을 즉시 반환하며 별도 실행·열람 audit를 남기지 않고
  현재 provider 상태도 다시 확인하지 않음
- pipeline 후보자 열람은 기록하지만 기업 추천 후보자 열람은 같은 방식으로 기록하지 않음
- 지원 audit는 공고 ID만 target으로 두고 새 application ID를 detail에 남기지 않음
- 화면은 전형 상태를 임시 선택한 뒤 저장·취소하게 하지만, 저장 API는 즉시 commit하며 이전
  상태·공고 ID·사유·참조한 score version을 남기지 않음
- cache decode는 top-level·상태·items 배열·각 item object를 확인하지만 operation별 필수 item key와
  요청 subject 집합 일치를 확인하지 않으며 동의·정책 snapshot, tenant/customer side, 생성 시각,
  system prompt revision, inference 설정, live flag, content MAC도 결속하지 않음
- 미실행 관찰 스크립트는 합성 cache의 정확한 job UUID·correlation ID로 한 entry를 찾아
  `score_breakdown`을 제거한 뒤 현재 API가 이를 hit로 반환하는지를 기록하도록 계획됨
- raw prompt 기록과 Redis cache가 주 DB 탈퇴 처리와 동시에 제거되지 않음
- 설명 context의 8개 필드 중 6개만 PII 필드명으로 분류해 기록함
- 동의 이벤트의 `policy_version`은 server-side catalog/hash와 연결되지 않은 client 입력이며,
  기록된 수집 항목에는 이후 추천·설명 경로가 처리하는 `skills`, `desired_role`, `self_intro`가 없음.
  `birth_date`↔`birthdate`, `career`↔`years_experience`, `education`↔`school`의 의미 대응은 미승인
  상태이며, 동의 삭제와 회원 탈퇴가 서로 다른 철회 event shape를 기록함
- overclaim 장애 주입 결과를 의미 검증기가 차단하지 않음
- 기업 가입 split write의 operation ID·멱등 키·보상·사후 조정·outbox 계약이 각각 없음
- 신규 기업이 별도 검토 전환 없이 `Company.status=approved` 모델 기본값으로 생성됨
- 공개 공고 목록은 열린 공고만 고르지만 ID 상세는 상태를 제한하지 않아 마감 공고와 기업
  프로필을 계속 반환할 수 있음
- 기업 상태가 `suspended`여도 공개 공고 목록·상세, 지원 제출·현황, 지원자 추천과 기업 업무 경로가
  `Company.status`를 권한 게이트로 사용하지 않음
- 기업 간 객체 접근은 거부하지만 거부 audit의 `company_id`는 행위자 기업이고, 대상 객체 ref와
  별도로 대상 기업 snapshot을 기록하거나 대상 기업 기준으로 필터링하는 필드는 없음
- gateway raw/structured prompt 기록에는 provider 구성 지문과 입력 준비 상태 `PREPARED`가 있으나,
  외부 provider 수신 확인이나 성공·실패 terminal outcome event는 없음. prompt hash도 항목 material
  형식만 묶고 system prompt·provider/model·inference 설정·correlation ID를 포함한 전송 영수증은 아님
- DB·matcher 중단과 provider·Redis 장애의 응답 계약이 서로 다름
- 양면 관찰 스크립트는 실행별 canonical UUID에 한해 두 DB 레코드와 Redis cache key를
  정리하지만 raw prompt log line은 자동 삭제하지 않음. cleanup 뒤 실행별 correlation ID와
  subject ID의 모든 고유 pair에 해당하는 raw prompt 레코드가 각각 정확히 한 건 남는지를 내용
  출력 없이 probe함. 이 관찰은 시작 전에 gateway health의 raw prompt 기록 활성 상태를 확인하며,
  비활성이면 시나리오를 진행하지 않음
- 기존 volume에 일부 seed만 남은 경우 자동 보정하지 않고 결정론 sentinel ID 집합의 누락을
  기동 오류로 드러냄
- 동의 화면은 최신 필수·선택 동의 이벤트와 각 이벤트의 실제 `policy_version`을 복원하며 이미
  기록된 선택 동의를 일반 화면 흐름에서 다시 grant로 기록하지 않음. API의 직접 POST는 동일한
  grant를 계속 append할 수 있으므로 중복 방지나 server-side 동의 catalog·철회 정책을 추가했다는
  뜻은 아님. 이 API 상태를 별도 관찰 시나리오로 채택할지는 사람이 정함
- 이력서 화면은 저장 뒤 API가 정규화해 반환한 값을 form과 변경 감지 baseline에 다시 반영함
- pipeline API는 지원 레코드에 연결된 현재 Resume가 없으면 그 항목을 응답에서 제외함. 화면은
  빈 응답을 지원 레코드 부재로 단정하지 않으며, 제외 건수 자체는 현재 API가 제공하지 않음
- 반복되는 점수·생성 설명·현재 이력서 disclosure에는 공고 또는 지원자 이름을 접근 가능한 이름으로
  덧붙이고, 전형 변경 취소와 hash 이동 뒤 초점을 복원함. 이는 브라우저·스크린리더 실행 증거가 아님
- 감사 화면은 이벤트 시각 원문을 `time[datetime]`에 유지하고 필터 입력 이름을 표시하지만,
  이벤트 수집 범위나 보존의 충분성을 판정하지 않음

승인된 `EXPECTED_FINDINGS`에 없는 항목은 시연용 위험으로 보존할지 기능 누락으로 수정할지
사람이 결정한다.

## 11. Terraform 대조

`terraform/asis`에는 2-AZ VPC, 네 ECS service 정의, RDS/Redis/S3, edge·관측·IAM 모델이 있다.
이번 애플리케이션 계약 보강은 기존 resource block을 추가하지 않았지만, 현재 세션에는
Terraform/OpenTofu CLI가 없어 validate와 mock plan을 다시 실행하지 못했다. 변경 전 마지막
기록은 110 planned resources이며 현재 결과라고 재주장하지 않는다. `terraform apply`는 금지다.

`src/runtime/contracts/application_artifacts.yaml`은 네 앱을 `UNBUILT`·`UNPUBLISHED`로,
`endpoint_test_sample.yaml`은 Windows 3대·macOS 3대의 계획 표본을 `NOT_EXECUTED`로 고정한다.
`risk_observation_plan.yaml`은 16개 관찰을 `DRAFT_NOT_APPROVED`·`NOT_EXECUTED`로 두고 자동 실행·
자동 위험 판정을 금지한다. 이 중 session 관찰은 특정 API 경로에서 같은 token의 재사용과 회원
`active` 게이트만, 기업 논리 연결 관찰은 담당자 `company_id`가 기업 overview에서 해석되는 방식만
기록한다. 브라우저 logout·token 철회/만료·조직 membership 수명주기·교차 저장소 부분 commit
fault injection의 증거가 아니다. 두 관찰의 시험 전용 회원 상태 변경은 현재값을 조건으로 정확히
한 행만 바꾸고 즉시 복구한 뒤 공통 cleanup에서 다시 확인하도록 source 계약에 고정했다.
`lab_run_receipt.schema.json` v2는 향후 redacted receipt의 source/archive/
manifest/API/plan/schema/deploy hash, 네 app digest, 원문을 싣지 않는 cleanup identifier/prompt-pair
집합 hash와 시나리오별 source/result/evidence digest를 정의한다. 시나리오 source digest는 해당 plan
slice와 관찰 script hash를 결속하고, result와 evidence digest는 원문 prompt·객체 ID·request/response를
싣지 않는 요약 record만 결속한다. 순수 instance validator는 전달된 source payload bytes를 전역 hash와
parsed plan에 결속하고, evidence payload를 허용된 비음수 집계 metric으로 제한하며, source assertion
집계를 result 상태·assertion 수에 교차 결속하고,
`COMPLETED* → FAILED → SKIPPED_AFTER_FAILURE*` 순서를 요구한다. 그러나 실제 receipt와 archive 포함관계, archive member hash,
승인 참조, 서명·보관을 읽는 ingestion validator는 없다. Terraform output은 이 계약 경로와 상태를 교차 표시할 뿐 image, endpoint,
receipt 또는 resource를 추가하지 않는다. 전체 가상 inventory 100 Windows + 80 macOS와 실제 시험표본
3+3을 섞지 않는다.
output 객체 이름은 기존 호환성을 위해 `execution_evidence`로 남아 있지만,
`evidence_present=false`와 `evidence_interpretation=source-state-declarations-only`를 함께 고정한다.
이는 경로나 상태 문자열을 실행 증거로 읽지 않게 하는 source 선언이다.

AWS 기동을 주장하려면 최소한 다음 실행 계약이 별도로 필요하다.

1. immutable image digest와 배포 승인 입력
2. API→agent/gateway, API→Redis service discovery
3. 세션 서명키와 두 DB app role 자격증명 주입·회전
4. 기업 DB·role bootstrap 및 migration/seed 단일 실행·rollback
5. gateway 전용 Bedrock role과 내부 경로 인증
6. Fargate에서 raw prompt를 어떻게 보존·접근·삭제할지에 대한 저장 계약

이 여섯 항목은 TO-BE 구현 승인이 아니며, 현재 AS-IS 모델의 실행 간극을 드러내는 목록이다.
Terraform 출력 precondition은 회원·기업 DB 이름과 app role이 서로 다른지만 검사한다. 실제
database·role 생성, 권한 부여, 자격증명 전달이 완료됐다는 뜻은 아니다.

별도 `terraform/lab`은 향후 합성 실증 후보일 뿐 현재 실행 상태가 아니다. 소스 계약은 한 대의
`t3.small`, inbound 0, SSM tunnel, 합성 stub, 실패 시 stop 요청, 20~30 GiB encrypted root,
service별 memory limit을 요구한다. 정적 검사는 이 계약을 확인하지만 t3.small의 실제 build/run,
운영자 tunnel, AWS 외부 상태, Windows/macOS endpoint를 증명하지 않는다. ignored state backup과
saved plan의 보존·폐기는 `P1-C06`의 사람 결정으로 남겨 둔다.

## 12. 사람 결정 대기

- 2026-08-28 조직도가 기존 §3 기준선을 대체하는지, 별개 시점·목적의 조직도인지. 대체할 경우에도
  80명 노드명과 정보보안팀 첫 기능 명칭은 확인 전 확정하지 않음
- 회원DB 14개·기업DB 9개 화이트보드 논리 필드의 canonical 이름, 수집 목적, 현재 column 의미
  매핑과 LLM02 계수에서 score breakdown·matched label·subject ref를 포함할지
- 현재의 담당자-기업 논리 연결에 조직 membership·역할과 기업별 담당자 수 제약을 둘지,
  담당자 탈퇴·소유권 이전·기업 동의·상태 전환 수명주기를 범위에 넣을지, 가입 초기 상태와
  검토 주체를 어떻게 정할지
- 동의 문구, 실제 수집, 기업 열람, provider 전송 목적을 필드별로 어떻게 정렬할지
- 추천·후보자 열람·전형 변경의 어떤 이벤트를 append-only audit 대상으로 둘지
- 기업 추천 cache 무효화와 탈퇴 시 Redis·prompt·backup 처리 계약
- 기업별/공고별 가중치와 자소서 의미 유사도를 점수에 반영할지
- Terraform을 토폴로지-only로 유지할지 승인된 lab 실행 계약까지 확장할지
- 내부용 snapshot에서 외부 preview용 최소 필드 projection을 누가 승인·발급할지
