# J-Career runnable AS-IS runtime

기존 `terraform/asis`가 모델링한 네 배포 단위와 데이터 계층을 로컬 Docker Compose에서
실제로 조작할 수 있도록 구현한 합성 재현환경이다.

이 환경은 실제 J사 서비스가 아니며, AWS 배포 상태 또는 ISMS·ISO/IEC 42001 판단 결과를
나타내지 않는다. 실제 지원자 정보, 실제 기업 정보, 외부 LLM 키를 입력하지 않는다.

- 전체 행위자·서비스·API·데이터·Terraform 대조: [`ASIS_RUNTIME_SPEC.md`](ASIS_RUNTIME_SPEC.md)
- 점수와 설명 상세 흐름: [`AI_MATCHING_FLOW.md`](AI_MATCHING_FLOW.md)
- 실행·정적 검증 기록과 한계: [`VERIFICATION.md`](VERIFICATION.md)
- 미실행 단말·앱 artifact 상태: [`contracts/README.md`](contracts/README.md)
- 8/28 멘토 조직·자산·학습·CEO 보고 경계:
  [`contracts/mentor_feedback_2026_08_28.json`](contracts/mentor_feedback_2026_08_28.json)
- 정보보호시스템·명시적 부재·인접 자산 대장:
  [`INFORMATION_PROTECTION_SYSTEM_INVENTORY.md`](INFORMATION_PROTECTION_SYSTEM_INVENTORY.md)
- 읽기 전용 CEO 브리프: [`mentor-brief/README.md`](mentor-brief/README.md)
- API source surface inventory: [`contracts/api_surface.json`](contracts/api_surface.json)
- API handler 반환·직접 예외 source catalog: [`contracts/api_wire_shapes.json`](contracts/api_wire_shapes.json)
- 미승인·미실행 위험 관찰 plan과 향후 receipt schema: [`contracts/risk_observation_plan.yaml`](contracts/risk_observation_plan.yaml), [`contracts/lab_run_receipt.schema.json`](contracts/lab_run_receipt.schema.json)

## 실행

Docker Desktop이 실행 중인 환경에서 다음 명령을 사용한다.

```powershell
cd src/runtime
docker compose up --build -d
docker compose ps
python tests/smoke.py
python tests/api_boundary_contract.py
python tests/score_contract.py
python tests/database_boundary.py
python tests/security_smoke.py
python tests/resilience_smoke.py
python tests/two_sided_asis_observations.py
```

`two_sided_asis_observations.py`는 합성 계정을 새로 만들고 현재 의도적으로 남긴 기업 상태
게이트 미적용, 별도 검토 전환 없는 `approved` 가입 기본값, 지원 시점 snapshot 부재, 철회 뒤 기업
열람 지속, 클라이언트가 제출한 동의문 버전과 처리 필드 목록의 차이를 관찰한다. 기업 추천 cache
생성 뒤 이력서 수정과 신규
지원자가 이전 응답에 반영되지 않는지도 함께 확인한다. 추천 cache miss/hit의 감사 event delta,
지원·전형 변경 감사 필드 shape, `score_breakdown`이 빠진 중첩 cache item의 반환 여부도 기록한다.
이는 충분성 판정이 아니라 source assertion 관찰이다. 종료 시 생성한 공개 공고를 먼저
마감한 뒤 실행에서 발급된 canonical UUID로 두 DB의 합성 레코드와 해당 Redis cache key만
정리하고 잔존 건수를 다시 확인한다. SQL은 첫 오류에서 중단된다. cleanup 뒤에도 실행별
각 cache miss의 correlation ID와 subject ID에 해당하는 모든 고유 raw prompt JSONL pair가
각각 정확히 한 건 남는지를
내용 출력 없이 확인한다. AS-IS 보존 관찰면인 raw prompt log line은 삭제하지 않으므로 반복
실행 전 보존·폐기 결정을
별도로 해야 한다.
실제 서비스나 실데이터에 실행하는 스크립트가 아니다.

기존 volume이 있으면 API는 결정론 seed의 기업·계정·이력서·동의·공고·지원·감사 sentinel을
확인한다. 일부만 남은 volume을 자동 복구하거나 덮어쓰지 않고 기동 오류로 드러내므로,
합성 volume 보존·초기화는 운영자가 별도로 결정한다.

브라우저에서 `http://localhost:3000/jobs`를 연다. 호스트에 publish하는 포트는 기본값으로
`127.0.0.1`에만 바인딩된다. `WEB_BIND_ADDRESS`를 바꾸면 web 노출 범위가 넓어지므로 이
로컬 계약을 LAN·인터넷 공개 구성으로 사용하지 않는다.

서비스를 실행하면 FastAPI 문서는 `http://localhost:8000/docs`와
`http://localhost:8000/openapi.json`에서 확인할 수 있다. 현재 source inventory는
`contracts/api_surface.json`이며 route·요청 model 선언·역할·선택된 tenant marker와 기업 계정,
현재 지원자료, 추천 audit, cache 검증, 동의/설명 필드 matrix의 선택된 source state drift를 정적으로
잡는다. legacy `required_calls`는 handler AST의 선택된 symbol 존재 목록이며 분기 실행 증거가 아니다.
완전한 DB read/write graph는 아니다. OpenAPI security scheme, 완전한 response schema,
dependency/downstream의 전체 오류 조건은 아직 제품 wire 계약으로 고정하지 않았다.
`contracts/api_effects.json`은 33개 handler 전부의 양 DB·감사·Redis·agent·gateway·prompt-log
효과와 주요 분기를 별도로 선언하고 함수 지문과 선택된 lexical 순서를 검사한다. 이 역시 완전한
CFG 또는 실행 trace가 아니다.
`contracts/api_wire_shapes.json`은 같은 33개 handler의 직접 `return` 표현식과 handler 본문에
직접 적힌 literal `HTTPException`만 source에서 추출해 38개 route의 성공 status와 나란히 둔다.
literal object의 최상위 key만 기록하며 helper·local name·cache 반환을 펼치지 않는다. 빈 오류
목록은 dependency·helper·downstream·FastAPI/Pydantic 422·500 오류가 없다는 뜻이 아니고,
응답 model이나 제품 wire schema가 강제된다는 증거도 아니다.

AWS·Docker를 시작하지 않는 웹 정적 회귀 검사는 다음처럼 실행한다.

```powershell
npm run verify --prefix src/runtime/web
npm run build --prefix src/runtime/web
python -B src/runtime/tests/api_boundary_contract.py
python -B scripts/check_runtime_infra_contract.py .
python -B tests/test_runtime_infra_contract.py
python -B scripts/check_runtime_manifests.py --root .
python -B tests/test_runtime_manifests.py
python -B scripts/check_api_surface_contract.py --root .
python -B tests/test_api_surface_contract.py
python -B scripts/check_api_effects_contract.py --root .
python -B tests/test_api_effects_contract.py
python -B scripts/check_api_wire_shapes.py --root .
python -B tests/test_api_wire_shapes.py
python -B scripts/check_runtime_evidence_contracts.py --root .
python -B tests/test_runtime_evidence_contracts.py
node src/runtime/web/tests/contrast-contract.mjs
python -m unittest src/runtime/tests/mentor_feedback_contract.py
node --check src/runtime/mentor-brief/app.js
```

종료:

```powershell
docker compose down
```

합성 데이터까지 초기화:

```powershell
docker compose down --volumes
```

`--volumes`는 이 Compose 프로젝트의 `postgres-split-data`, `redis-data`, `prompt-logs`
볼륨만 삭제한다.

## 데모 계정

공통 비밀번호는 `Demo123!`이다.

| 역할 | 이메일 |
|---|---|
| 구직자 | `candidate@jcareer.test` |
| 채용담당자 | `recruiter@jcareer.test` |
| 다른 합성기업 담당자 | `recruiter-beta@jcareer.test` |
| 운영자 | `admin@jcareer.test` |

## 서비스 대응

| Terraform AS-IS 단위 | 로컬 런타임 | 포트 |
|---|---|---:|
| `web` | React 정적 빌드 + Nginx | 3000 |
| `api` | FastAPI 업무·인증·감사 API | 8000 |
| `agent` | 결정론적 matcher | 8100 |
| `llm-gateway` | 로컬 합성 provider stub, 기본 비활성 Bedrock adapter, prompt log | 8200 |
| RDS PostgreSQL | PostgreSQL 16 컨테이너, 회원·기업 논리 DB | 내부 5432 |
| ElastiCache Redis | Redis 7 컨테이너, 추천 캐시 24시간 | 내부 6379 |

서비스 발견은 Compose DNS 이름 `api`, `agent`, `llm-gateway`, `postgres`, `redis`로 한다.
이는 현재 `terraform/asis`에 없는 런타임 계약이며, 그대로 ECS가 동작한다는 의미가 아니다.

## 회원 DB와 기업 DB 경계

사용자가 제공한 `기업db_회원db.jpg`를 참고해 같은 PostgreSQL 서버 안에 두 개의 별도
database와 전용 role을 둔다. 이는 물리 RDS 두 대나 독립 장애 경계를 뜻하지 않는다.

| 논리 DB | 소유 데이터 |
|---|---|
| `jcareer_member` | 통합 로그인 identity, 동의, 이력서, 지원관계, 감사 이벤트 |
| `jcareer_company` | 기업, 기업 방향·핵심가치 프로필, 채용공고 |

기업 담당자도 플랫폼 계정이므로 인증 identity는 회원 DB에 두고, `company_id`로 기업 DB의
고객 조직을 논리 참조한다. 이는 현재 구현 가정이다. 기업 담당자의 인증정보까지 기업 DB로
옮기는 별도 identity realm은 아직 승인된 요구사항이 아니다.

두 DB 사이에는 foreign key나 ORM relationship이 없다. 로컬 init은 반대 DB에 대한 role의
`CONNECT` 권한을 회수한다. 다만 API 프로세스는 업무 조합을 위해 두 DSN을 모두 가지며,
같은 RDS·보안그룹·백업·읽기 복제본을 공유한다. 교차 DB 쓰기는 원자적이지 않고 현재
개발용 `create_all`·자동 seed는 배포용 migration 방식이 아니다.

## 구현된 P0 경로

- 공개: `/jobs`, `/jobs/:id`
- 구직자: `/signup`, `/signup/consent`, `/login`, `/candidate/resume`,
  `/candidate/home`, `/candidate/applications`, `/candidate/recommendations`, `/candidate/withdraw`
- 기업: `/recruiter/signup`, `/recruiter/overview`, `/recruiter/jobs`, `/recruiter/jobs/:id/pipeline`,
  `/recruiter/jobs/:id/recommendations`
- 운영자: `/admin/audit`
- 정적 안내: `/privacy`, `/terms`

## AS-IS 관찰 동작

- 기업 고객 홈은 자기 회사의 공개·마감 공고 수, 지원관계 수, 전형 단계 분포와 최근 공고를
  보여 준다. API가 회원 DB의 지원관계와 기업 DB의 공고를 회사 범위로 조합하며, 화면은 이
  집계를 채용 판단이나 규제 판정으로 표현하지 않는다.
- 기업 가입 한 번은 기업과 첫 담당자 하나를 생성하지만, DB가 기업별 담당자 수를 하나로
  제한하지는 않는다. 기업 홈은 이 논리 연결과 제약 부재를 나누어 표시하고 조직 멤버십·초대·세분 역할,
  담당자 탈퇴, 기업 소유권 이전, 기업 동의, 상태 전환 경로가 없고 `Company.status`가 기업 업무
  API뿐 아니라 공개 공고 목록·상세, 지원 제출·현황, 지원자 추천의 게이트에도 쓰이지 않는 사실을
  서로 분리된 source state로 표시한다. 신규 기업이 별도 검토 전환 없이 모델 기본값 `approved`로
  생성되는 상태도 별도 필드로 표시하며, 이를 기업 확인이나 승인 절차의 수행으로 표현하지 않는다.
  같은 관찰면은 지원관계가
  공고 UUID를 논리 참조하며 교차 DB 원자적 커밋, 가입 operation ID·멱등 키, 보상·사후 조정·outbox가
  없다는 source state도 각각 표시한다.
- 파이프라인은 조회 시점의 현재 이력서를 펼쳐 보여 준다. 지원 시점 스냅샷이 아니며, 펼침
  동작 자체의 별도 감사 이벤트도 없다. 전형 상태는 화면에서 저장·취소를 구분하지만 서버는
  저장 시 즉시 commit하고 이전 상태·변경 사유를 감사 상세에 남기지 않는다.
- 기업 추천 화면은 API가 반환한 지원자 안에서 이름·희망 직무·등록 기술과 최소 표시 점수로
  목록을 좁히고, 최대 3명의 기존 score breakdown을 나란히 보는 임시 비교를 제공한다. 화면
  필터는 서버 순서를 바꾸거나 점수를 다시 계산하지 않는다. 비교 선택은 브라우저 메모리에만
  있고 서버에 저장하지 않으며, 전체 인재 검색·shortlist·채용 판정 기능이 아니다.
- 동의 이벤트의 `policy_version`은 server-side 동의문 catalog나 hash에서 선택되지 않고 client가
  보낸 문자열을 기록한다. 기록된 수집 항목에는 `skills`, `desired_role`, `self_intro`가 없지만
  현재 추천·설명 경로는 이 필드를 처리한다. `birth_date`↔`birthdate`, `career`↔`years_experience`,
  `education`↔`school`도 이름이 다르며 의미상 같은 항목인지는 사람이 정한다. 동의 삭제 경로는
  기존 catalog를 다시 기록하지만 회원 탈퇴 경로는 빈 수집 항목·목적 배열을 기록한다. 어느
  형태가 맞는지와 문구의 적절성은 이 런타임이 판정하지 않는다.
- matcher는 기술·직무·경력 구조화 항목만 사용하며 동일 입력에 동일 점수를 반환한다.
- 설명 생성은 `llm-gateway`로 분리한다. cache miss의 설명 경로 연결·HTTP·JSON·계약 검증 또는
  gateway/외부 공급자 경로가 unavailable/invalid이면 추천 목록과 점수는 유지되지만 설명과
  `company_alignment`는 함께 비고 legacy 상태 `UNAVAILABLE_PROVIDER`로 축약된다. 이 상태만으로
  외부 공급자 장애를 주장하지 않는다. warm
  cache hit는 과거 설명을 반환하며 현재 Provider 상태를 재확인하지 않으므로 화면에 별도 경계를
  표시한다.
- matcher는 `기술 70 + 경력 20 + 희망 직무 연관 10`의 버전 고정 산식과 요인별 원시
  기여도·표시값을 반환한다. 화면은 이를 그대로 표시하며 브라우저에서 점수를 재계산하지
  않는다. 상세 계약과 시연 항목은 `AI_MATCHING_FLOW.md`에 있다.
- Bedrock Converse adapter는 기존 `llm-gateway` 안에 포함되지만 기본 provider는 합성
  stub이고 `ALLOW_BEDROCK_LIVE=false`다. 별도 서비스는 추가하지 않았다.
- 기업 담당자는 회사 방향과 핵심가치를 버전이 붙은 프로필로 입력할 수 있다. 설명 경로는
  자소서의 직접 일치 표현을 별도 `company_alignment`로 반환하며 현재 점수에는 합산하지
  않는다.
- 설명 경로가 받은 합성 원문은 별도 `prompt-logs` 볼륨에 기록된다. 일반 애플리케이션
  로그에는 원문과 토큰을 쓰지 않는다.
- cache miss의 현재 설명 요청에는 시나리오상 준비되는 여섯 필드(`name`, `phone`, `email`,
  `birthdate`, `address`, `school`)와 `certificates`, `self_intro`가 포함된다. Gateway는 여섯
  필드와 전체 준비 필드명을 구분해 `PREPARED`로 기록하지만, 값이 실제 개인정보인지 자동
  판정하지 않는다. 현재 요청의 실패 응답도 준비 필드를 반환하되 gateway나 외부 공급자의 실제
  수신은 주장하지 않는다. 빈 추천 집합은 필드를 준비하지 않는다. cache hit는 원본 요청에서
  준비된 필드 집합을 현재 cache 응답 구조로 검증할 수 없으므로 준비 필드 배열을 비우고
  `CACHE_ORIGIN_FIELD_SET_NOT_VERIFIED`를 표시한다.
- 추천 캐시는 Redis에 24시간 저장한다.
- 후보자 추천 캐시 키는 이력서 갱신 시점과 열린 공고의 식별자·회사 프로필 버전·제목·본문·
  지역·고용형태·요구 기술·최소 경력·상태·갱신 시점을 canonical hash로 묶는다. 이 재료가
  바뀌면 새 키를 사용한다. 양쪽 cache key는 provider·설명 계약·Bedrock client region·model
  reference의 구성 지문도 포함해 구성이 바뀐 과거 설명을 재사용하지 않는다. 이 지문은 실제
  공급자 호출이나 처리 위치의 증거가 아니다. 반면 기업 추천 캐시는 지원자 집합·이력서 version을 키에 포함하지
  않아, 그 stale 동작은 별도 AS-IS 관찰 시나리오로 남아 있다.
  cache envelope에는 동의·정책 snapshot, tenant/customer side, 생성 시각, system prompt revision,
  inference 설정, live flag 또는 content MAC도 결속되지 않는다.
- 회원 탈퇴는 주 데이터베이스 처리를 수행하지만 화면에서 모든 저장면의 완전 삭제를
  주장하지 않는다. 합성 canary 시험에서는 주 DB의 이력서·지원관계 제거 뒤에도 이미
  생성된 추천 캐시와 raw prompt 기록이 즉시 함께 제거되지 않는 동작을 관찰했다.
- 기업 간 객체 접근은 차단한다. 알려진 취약점을 새 코드에 의도적으로 심지 않으며,
  AUTH-01 재현 여부는 별도 관찰 결과로 남겨야 한다.
- 공개 공고 목록은 열린 공고만 반환하지만 ID 상세는 마감 상태를 제한하지 않고 기업 프로필도
  포함한다. 계속 공개할지는 사람이 정하며, 현재 source 계약은 이 차이를 숨기지 않는다.
- 기업 간 접근 거부 audit는 행위자 기업과 대상 객체 ref를 남기지만 대상 기업 snapshot은 별도
  필드로 남기지 않는다. 관리자 회사 필터도 현재는 행위자 기업 기준이다.

초기 seed는 `demo_not_for_measurement` 프로파일이다. 합성 데이터 명세의 분포가 사람 승인
전이므로 FAIR-01 측정 또는 AS-IS/TO-BE 정량 비교에 사용하면 안 된다.

## 이 런타임이 증명하지 않는 것

- 로컬 matcher는 결정론적 계약 stub이다. 실제 모델의 품질·편향·설명 충실도 또는
  AI-V02/AI-V03 실증 결과를 대신하지 않는다.
- cache miss 응답에는 correlation ID가 있지만 raw prompt 기록은 gateway handler가 요청 검증을
  마치고 진입한 경우에만 생성된다. gateway 연결 실패나 handler 전 Pydantic 거부에는 그 기록이
  없다. prompt hash는 항목 material 형식용 hash이며 system prompt·provider/model·inference 설정·
  correlation ID를 포함한 전송 또는 무결성 영수증이 아니다. AS-IS 시나리오대로 AI 호출 자체를
  `AuditEvent`에 남기는 `match_run` 감사 이벤트도 구현하지 않았다.
- `match_results`, `ai_explanations`, `pii_purged_at` 전용 영속 모델과 전 저장면 삭제
  오케스트레이션은 이번 P0 재현 범위에 없다.
- 이메일은 예약 도메인, 전화번호는 `010-0000-XXXX` 형식을 강제하지만 이름·주소·학교·
  자기소개 같은 자유 입력값의 합성 여부는 기술적으로 검증하지 않는다. 실제 정보 입력은
  금지된다.
- `/agent/internal/*`와 `/llm/internal/*`는 컨테이너 내부 인증이 없는 로컬 계약이다.
  호스트에서는 loopback에만 열리며 외부 또는 LAN에 공개하면 안 된다.
- Terraform AS-IS에는 Bedrock 호출 IAM 권한이 없다. public `/llm` 경로와 공유 task role이
  남아 있으므로 provider와 live flag만 바꿔 AWS 실행이 준비됐다고 주장하지 않는다.
- 장애 주입 파라미터는 애플리케이션 기본값이 비활성화이고 이 로컬 Compose에서만
  명시적으로 활성화한다.

## Terraform과의 런타임 간극

`contracts/application_artifacts.yaml`은 네 앱을 `UNBUILT`·`UNPUBLISHED`로,
`contracts/endpoint_test_sample.yaml`은 Windows 3대·macOS 3대 시험표본을 `NOT_EXECUTED`·
Terraform 비관리로 기록한다. Terraform output도 같은 상태와 manifest 경로만 표시한다.
이는 image, endpoint 또는 배포가 존재한다는 뜻이 아니다.

`contracts/risk_observation_plan.yaml`은 16개 시나리오를 `DRAFT_NOT_APPROVED`·`NOT_EXECUTED`로,
`contracts/lab_run_receipt.schema.json`은 향후 redacted receipt의 형식만 기록한다. 추가된 두
시나리오는 특정 `/api/v1/auth/me`·`/api/v1/auth/logout` 경로와 회원 `active` 게이트, 담당자의
`company_id` 논리 연결이 기업 overview에서 해석되는 방식만 관찰하도록 제한한다. 브라우저
`localStorage` 상태 전이, token 만료, 조직 membership·role 수명주기, 교차 저장소 부분 commit
fault injection은 관찰하지 않는다. 시험 harness의 회원 상태 변경은 기대한 현재값을 조건으로
정확히 한 행만 바꾸고 즉시 복구하며 공통 cleanup에서도 재시도하도록 계약했지만 실행하지 않았다.
실제 receipt, source archive 포함관계 validator, 승인·서명·보관 증거는 없다. Terraform output은
이 경계도 source-state 문자열로만 표시한다.

- Compose의 PostgreSQL 16은 로컬 실행 기준이다. `terraform/asis`의 RDS 15.7 값은
  가정값이며 이 시험에서 호환성을 검증하지 않았다.
- 현재 ECS 정의에는 회원·기업 DB URL 계약을 배선했지만, 기업 DB와 전용 role을 실제로
  생성하는 승인된 bootstrap, Redis·agent·gateway 주소, 세션 키와 데이터셋 프로파일,
  검증된 서비스 디스커버리가 없다. 원하는 태스크 수가 2여도 이 코드가 그대로 AWS에서
  안전하게 기동한다는 의미가 아니다.
- 개발용 `create_all`과 자동 seed는 복수 replica 마이그레이션 방식이 아니며,
  `prompt-logs` 로컬 볼륨은 Fargate 영속 저장 설계가 아니다.

## 장애 주입

Gateway 직접 계약은 요청 body의 `mode`를 사용해 시험할 수 있다.

```json
{
  "mode": "rate_limit",
  "items": []
}
```

지원 값은 `success`, `timeout`, `rate_limit`, `provider_error`, `malformed`다. API 수준의
component degradation은 smoke test에서 확인한다.

`tests/outage_probe.py`는 서비스 중단·복구를 사람이 명시적으로 수행한 뒤의 계약을
검사한다. 검증 절차와 최신 관찰 결과는 `VERIFICATION.md`에 기록한다.
