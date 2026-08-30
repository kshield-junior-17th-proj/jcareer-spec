# J-Career AS-IS runtime 검증 기록

기준일은 2026-08-28이다. 이 문서는 로컬 합성 런타임에서 관찰한 사실과 범위 한계를
기록한다. ISMS 또는 ISO/IEC 42001의 충족 여부, 인증 가능성, 잔여위험 수준을 판정하지
않는다.

## 검증 범위

- 대상: `web`, `api`, `agent`, `llm-gateway`, 두 논리 DB를 가진 PostgreSQL, Redis의 Docker Compose 실행
- 데이터: `demo_not_for_measurement` 합성 seed와 시험마다 생성한 합성 canary
- 네트워크: 호스트 `127.0.0.1` 바인딩
- 제외: AWS 배포, 2-AZ 장애조치, RDS 백업·S3 버전, 실제 Bedrock 운영 연동, 실제 지원자 데이터,
  TRACE 및 그 밖의 신규 AI 서비스

현재 `terraform/asis`에는 API용 회원·기업 DB URL 계약이 추가됐지만 기업 DB·전용 role
bootstrap, Redis·내부 서비스 URL 및 검증된 서비스 디스커버리가 없다. 따라서 아래 결과는
Terraform의 2-AZ AWS 실행을 증명하지 않는다.

## 2026-08-27 이전 버전에서 실행한 시험과 관찰값

| 시험 | 관찰값 |
|---|---|
| `python tests/score_contract.py` | 기술 70·경력 20·직무 10 산식, 다단어 한국어 직무 일치, 빈 희망직무 0점, 반올림 계약, invalid 요구 기술 422, 설명 경로 8개 준비 필드/6개 PII 분류, overclaim 문장 미차단·점수 덮어쓰기 불가 |
| `python tests/smoke.py` | 공개 공고, 세 역할 로그인, 후보자·기업 추천, 파이프라인, 관리자 감사 조회, 내부 health 경로 응답 |
| `python tests/security_smoke.py` | 핵심 동의 전 이력서 저장 409·철회 후 추천 409, 실제 도메인 형식 이메일 및 일반 전화 형식 거부, 변조 토큰 401, 역할 교차 403, 기업 교차 조회·수정 403, 거부 감사기록, 탈퇴 토큰 401 |
| `python tests/api_boundary_contract.py` | 서비스 기동 없이 이메일·동의 version DB 길이, 공고 요구기술 정규화, matcher feature·정렬, 설명 envelope, Redis JSON shape 경계를 확인 |
| `python tests/resilience_smoke.py` | timeout·429·503·malformed 각각 추천 HTTP 200, 점수·순서 유지, 설명만 `UNAVAILABLE_PROVIDER`, 장애 응답 cache miss |
| `python tests/database_boundary.py` | 당시 버전에서 회원 DB 5개·기업 DB 2개 테이블, 두 app role의 반대 DB CONNECT 거부, 양쪽 DB 행 존재와 회사 프로필 조회를 관찰. 현재 가입 응답 UUID와 두 DB 행의 정확한 논리 연결·합성 행 cleanup 보강본은 미실행 |
| Redis+LLM 동시 중단 뒤 API 재기동 | API·공고·matcher 추천 동작, 설명 `UNAVAILABLE_PROVIDER`; Redis DNS 대기와 Nginx의 이전 컨테이너 IP 고정 문제를 발견해 비동기 제한시간·Docker DNS 재해석으로 수정 후 재시험 통과 |
| LLM 복구, Redis 중단 유지 | 설명 즉시 `AVAILABLE`, cache miss |
| Redis 복구 | 첫 호출 cache miss, 다음 호출 cache hit |
| 손상된 Redis JSON | 손상 값을 cache miss로 처리하고 정상 추천 응답으로 교체 |
| matcher 중단 | 공개 공고 조회 200, 캐시를 비운 추천 요청 503; matcher 복구 후 smoke 재통과 |
| PostgreSQL 중단 | API health 500과 일반 오류문 반환; DB 복구 뒤 여섯 서비스 health 복구 |
| 합성 canary 탈퇴 | 주 DB 이력서·지원관계 제거 및 기존 토큰 401; 직전에 생성된 추천 캐시는 hit로 남고 raw prompt 볼륨에서도 canary 1건 관찰 |
| prompt metadata 검사 | 각 레코드의 PII 준비 필드명이 `address,birthdate,email,name,phone,school`과 정확히 일치하고 `certificates,self_intro` 준비 필드 기록 존재. 외부 공급자 수신 증거는 아님 |
| 일반 서비스 로그 문자열 검사 | Bearer 헤더, 데모 비밀번호, DB 비밀번호, seed 이메일 문자열 각각 0건 관찰 |
| 웹 빌드·표면 검사 | Vite production build, 16개 SPA 경로 200, 공개 공고 12건, CSP·Permissions-Policy 응답 헤더, 500px 모바일 렌더 확인 |

보안 시험의 합성 분류 강제는 이메일 예약 도메인과 전화번호 예약 패턴까지다. 이름·주소·
학교·자기소개 자유 입력값은 운영자 선언에 의존하므로 실제 정보가 아님을 자동 증명하지
않는다. raw prompt 레코드는 이 한계를 `classification_enforcement`로 함께 표시한다.

검증 스크립트의 `PASS`는 해당 HTTP 계약의 assertion이 통과했다는 뜻일 뿐, 관리체계나
법적 요구사항에 대한 판정이 아니다.

## 재현 명령

정상·인가·장애 모드 시험:

```powershell
python tests/smoke.py
python tests/api_boundary_contract.py
python tests/score_contract.py
python tests/database_boundary.py
python tests/security_smoke.py
python tests/resilience_smoke.py
python tests/two_sided_asis_observations.py
```

마지막 스크립트는 2026-08-28에 추가했지만 이번 AWS·Docker 중지 세션에서는 실행하지 않았다.
이는 기업 상태 게이트 미적용, 지원 시점 snapshot 부재, 동의 철회 후 기업 열람 지속,
client가 제출한 동의문 version과 기록된 처리 필드 차이, 기업 추천 cache의 이력서·지원자 집합
누락, 추천 miss/hit 감사 delta, 지원·전형 변경 감사 shape, 중첩 cache item 검증 공백을 없애지
않고 합성 데이터로 재현하기 위한 후속 관찰 계약이다. 특정 API 경로의 token 재사용/회원
`active` 게이트와 담당자 `company_id` 논리 연결 관찰도 추가했지만 브라우저 상태 전이, token
만료·철회, 조직 membership·role 수명주기, 교차 저장소 부분 commit fault injection은 다루지 않는다.
실행 뒤 합성 공고를 마감하고 실행별 UUID의 두 DB 레코드와 Redis cache key를 정리한다. 시험 전용
회원 상태 변경은 기대한 현재값을 조건으로 정확히 한 행만 갱신하고 즉시 복구하며 공통 cleanup에서
재시도한다. SQL 오류 즉시 중단·잔존 건수 재확인도 소스 계약에 포함한다. cleanup 뒤 각 cache
miss의 correlation ID와 subject ID로 구성된 모든 고유 pair의 raw prompt 레코드가 각각 정확히 한
건 남는지를 내용 출력 없이 확인하는 probe도 추가했지만 이번에는 실행하지 않았다. raw prompt log
line은 삭제하지 않는다. 이 문장은 실제 실행 성공을 주장하지 않는다.

Redis와 LLM Gateway를 동시에 내린 cold-start 시험:

```powershell
docker compose exec -T redis redis-cli FLUSHDB
docker compose stop redis llm-gateway
docker compose restart api
python tests/outage_probe.py --explanation UNAVAILABLE_PROVIDER --cache miss
docker compose up -d --wait llm-gateway
python tests/outage_probe.py --explanation AVAILABLE --cache miss
docker compose up -d --wait redis
python tests/outage_probe.py --explanation AVAILABLE --cache miss
python tests/outage_probe.py --explanation AVAILABLE --cache hit
```

`FLUSHDB`는 이 로컬 합성 Redis의 추천 캐시만 비운다. 실제 시스템이나 공유 Redis에서
실행하는 절차가 아니다.

## 남아 있는 기술·운영 결정

- 외부 preview에 이 런타임을 직접 공개할지 여부: 현재 구성은 로컬 재현용이며, 기존
  결정대로 외부 팀에는 승인된 redacted snapshot만 제공해야 한다.
- 배포용 세션 서명키·DB 비밀번호의 생성, 회전, 보관 방식
- 브라우저 시작 시 `/auth/me` 재검증·교차 탭 동기화와 local storage 사용 정책
- 서버 session 철회·refresh·logout 모델과 malformed signed token의 오류 정규화
- 스키마 마이그레이션 도구와 롤백 절차
- 회원·기업 DB 교차 쓰기의 operation ID·멱등 키·보상·사후 조정·outbox 설계
- 통합 identity를 회원 DB에 둘지 기업 담당자 identity realm을 별도로 둘지에 대한 사람 결정
- 기업 추천의 지원자 집합·이력서 변경 시 cache 무효화 정책
- 탈퇴 시 Redis·raw prompt·백업 등 각 저장면의 처리 정책과 검증 주체
- LLM Gateway 자체가 도달 불가능할 때 호출 시도를 어느 계층에서 기록할지 여부
- ECS용 DB·Redis·agent·gateway 주소 주입 및 서비스 디스커버리 설계
- 내부 agent/gateway 호출 인증 또는 네트워크 정책과 외부 노출 차단 방식
- 실제 matcher/model 및 승인된 평가 데이터로 수행할 품질·편향·설명 충실도 시험
- 참고 화면의 장애·보훈·군경력·한부모 항목을 수집·사용할지 여부와 별도 사람 검토
- Bedrock 처리 리전, 모델/profile, 전용 task role, 내부 호출 인증, 과금 제한 승인 여부
- `match_run` 감사 이벤트와 `match_results`·`ai_explanations` 영속 모델의 채택 여부
- PostgreSQL 16 로컬 런타임과 Terraform RDS 15.7 가정값의 호환 버전 결정
- 복수 ECS replica에서 사용할 스키마 마이그레이션·seed 단일 실행 방식과 prompt 저장소
- 합성 데이터 분포 명세 승인 전에는 현재 seed를 FAIR-01 또는 정량 비교에 사용하지 않음

이 항목들의 채택 및 통제 해석은 사람이 결정한다.

## 2026-08-28 변경분 정적 검증

기업 고객 운영 홈, 파이프라인과 점수 설명 UI 보강 뒤 AWS·Docker 서비스를 켜지 않은 상태에서
다음을 확인했다.

| 검사 | 관찰값 |
|---|---|
| 최신 JSX·bundle 정적 빌드 | `App.jsx` esbuild JSX transform과 Vite production build 완료(40 modules). browser render·container image·배포 증거는 아님 |
| 웹·관찰 시나리오 정적 계약 | 필수 82개·금지 회귀 13개 검사 완료; 플랫폼 공통 우선요인과 기업별 가중치 미적용 문구, 기업 프로필 출처, cache 원본 필드 미검증 표시, 필수·선택 동의와 실제 정책 버전 복원 및 선택 grant 중복 방지, 저장 응답 기반 이력서 정규화, 반복 disclosure 고유 이름, pipeline 취소 focus·Resume 없는 지원 제외 경계, 감사 필터 이름·machine-readable time, 구직자/기업 계정 수명주기 안내 분리, 재시도 button type, 지원·공고상태 변경 뒤 focus 복원, 모바일 실제정보 금지 문구, 늦은 GET 응답 무시, 추천 완료·저하 상태 1회 접근성 알림, 요청 중 새로고침 잠금, 긴 고객 문자열 협폭 줄바꿈, 검증 미적용 생성 설명 기본 접기, token·user 부분 세션 및 storage 예외 처리, 손상 세션과 local storage 삭제 성공/확인 실패 안내, 빈 상태부터 유지되는 polite status와 닫기 뒤 focus 복원, 로그인·양측 가입 form의 form 밖 진행 status·`aria-busy`·API 입력 길이 경계·중복 요청 방지, 401 원인 단정 금지와 초안 확인, 현재 token과 일치하는 401만 세션 신호로 처리, 요청 timeout·취소·network 오류 구분, 양면 관찰 스크립트의 stub-only gateway 가드 포함 |
| 브라우저 API response decoder | 순수 Node `Response`·fetch stub 11/11: JSON, text, 204, 빈 200, malformed JSON, body read 실패, 현재 token의 401 신호-before-decode와 Authorization header, 이전 token의 늦은 401 무시, 요청 timeout·caller 취소·정제된 network 오류 분류를 검사. 실제 browser navigation·network·server 응답 증거는 아님 |
| Python AST | API와 API 경계·security smoke·양면 AS-IS 관찰·runtime/Terraform 검사기 소스 구문 분석 완료 |
| Python import | FastAPI route 등록 완료: API 31, agent 10, llm-gateway 8 |
| PostgreSQL 검색 쿼리 컴파일 | 공개 공고의 `required_skills` 검색과 `open` 상태 조건 포함 |
| API 경계 계약 | 서비스 기동 없이 입력 길이·공백, 공고·이력서 기술의 동일 comparison key 정규화, 공고·기업 프로필 변경에 따른 후보자 추천 cache key 교체, 빈 설명 요청 단락, matcher 표시 metadata/순서, 설명 field/hash/alignment envelope, Redis JSON shape, 결정론 seed sentinel 회귀 통과 |
| 합성 DB 서버리스 MLOps | MLOps 단위 14개와 서버리스 경계 12개 시험 통과. attestation·두 DB 분리·5개 feature allowlist·엄격한 특징 snapshot 검증·원문 canary 미잔존·`RUNNING → TRAINED_PENDING_HUMAN_REVIEW`·자동 활성화 차단을 검사한다. `RUNNING` 기록 뒤 오류는 `FAILED_SAFE` 기록을 시도하지만, enablement·attestation·event·run ID·source mode·config 검증이나 최초 `RUNNING` 쓰기에서 거부되면 `FAILED_SAFE` 기록 전 종료될 수 있다. 실제 plan JSON의 stage별 exact address는 disabled 0, bootstrap 13, runtime 14로 검사하며 현재 암호화 배선은 SSE-S3(AES256)뿐이고 KMS·DB URL·VPC·SageMaker·EventBridge·자동 활성화는 없다. AWS-free disabled plan 0건과 `terraform validate`는 통과했다. 실제 runtime ORM seed를 별도 임시 SQLite에 생성한 일회성 교차검증은 53행·28명·6산출물, `TRAINED_SYNTHETIC_RUNTIME_DATA_NOT_APPROVED`, `runtime_wired=false`, 임시정리 성공. AWS apply·이미지 push·Lambda 호출·Docker 실행 증거는 아님 |
| API source surface | 33개 handler·38개 decorator route, request model·역할·선택 tenant marker와 기업 담당자 탈퇴/소유권/동의/상태전환 부재, 현재 지원자료 참조, 추천·cache-hit 감사 부재, cache provenance 공백, 동의 catalog·matcher·gateway field matrix와 상이한 철회 event shape를 source state와 함수 fingerprint로 대조. 브라우저 `localStorage` token/user 복원, 시작 시 role schema 검증 부재와 `Protected` 경로별 role allowlist 비교 존재, `/auth/me` 시작 재검증과 cross-tab sync 부재를 구분한다. API의 token `sub`→활성 회원 DB 사용자 및 DB role 권한원, 고정 합성 signing-key fallback·43,200초 TTL·`iat`/`jti`/server session/logout/revoke/refresh 부재·missing `sub` guard 공백도 분리해 고정하며 회귀 44개 통과. 브라우저 UI 신뢰 공백은 서버 BOLA 성공 증거가 아니다. legacy `required_calls`는 AST symbol 존재일 뿐 분기 실행 증거가 아니며, 실행 API·완전한 DB read/write graph·wire response/error 계약도 아님 |
| API source effects | 같은 33개 handler의 회원/기업 DB·감사·Redis·agent·gateway·prompt-log 효과와 주요 분기를 source review 선언으로 고정. 전 handler·14개 helper AST 지문과 기업 가입·양측 추천 cache 순서·overview/pipeline/admin 감사·gateway prompt/provider의 선택된 9개 lexical path를 검사하며 회귀 17개 통과. CFG dominance, 실행 cardinality, 원자성, downstream 수신 또는 실행 trace는 아님 |
| API source 반환·직접 예외 | 같은 33개 handler·38개 route의 직접 `return` 표현식, route 성공 status, handler 본문 literal `HTTPException`을 AST와 upstream contract hash에 결속하고 부정 회귀 14/14 통과. literal object 최상위 key만 기록하며 cache는 `CACHED_OBJECT_VALIDATED_SUBSET`, helper/local name은 미확장이다. dependency·helper·downstream·422·500·header·serialization·nested schema와 실행 응답은 범위 밖 |
| runtime/Terraform 소스 계약 | 지원자·기업 API method/path, 기업 홈 필수 route, DB engine bind·로컬 전용 role/DB 초기화, 데이터 소유, Compose/Terraform 서비스별 배선과 두 DB 이름·role 분리 선언 대조 및 검사기 단위 회귀 통과; Terraform output과 기업 홈 API는 조직 멤버십·담당자 탈퇴·소유권 이전·기업 동의·상태 전환·상태 행위자·상태 게이트, 공고 UUID 논리 참조·교차 DB 원자성·operation ID·멱등 키·보상·사후 조정·outbox 공백을 같은 source state로 드러내며 resource block은 추가하지 않음. `/recruiter/overview` 화면 상한 예외, Terraform S3·DB-only runtime 간극, raw prompt 보존 정책은 사람 결정 경고로 남김 |
| 양면 고객 정적 계약 | API·기업 홈·Terraform 출력에 담당자-기업 논리 연결, 가입 시 첫 담당자 생성, 기업별 담당자 수 제약 부재, 조직 멤버십 미구현, 기업 상태 게이트 미적용 표현 존재 |
| 독립 변경분 재검토 | 현재 이력서 경계, 상태 저장 피드백·포커스 복원, 모바일 로그인·DOM 순서, 동의 복구 경로, 설명 검증상태 fail-closed 표시, 기업 프로필 provenance, 기업 lifecycle source-state 비과장 표현, 양측 공동 관찰의 단일 ID·다중 lane 투영 반영 확인 |
| `git diff --check` | 추적 파일 공백 오류 없음 |
| `scripts/check_asis_contract.py` | `.tf` 38개, 금지 data source 없음, mock provider 플래그 확인 |
| 컨설턴트 dashboard | snapshot validator·view-model 23개 통과, 한 관찰의 양측 metadata 투영과 고유 건수 유지, CSP `connect-src 'none'`, network API·browser persistence·판정 계산 심볼 없음, `EXTERNAL_PREVIEW` fail-closed, loaded/error 제목 focus는 모바일에서 화면 밖에 숨지 않도록 스크롤 허용 |
| dashboard 빈 상태 브라우저 확인 | loopback 요청만 관찰, console 오류 없음, 승인 입력 부재를 숫자 없이 표시; 확인 뒤 임시 서버 종료 |
| AWS 다이어그램 원본 | `.drawio` XML의 공식 icon allowlist·필수 고객/서비스/DB cell·9개 flow·중복 ID·edge 결속·group container·범위 경계 문구를 저장소 validator로 확인; draw.io CLI 부재로 PNG export·시각 렌더는 미실행 |
| 미래 lab 정적 경계 | 전체 validator runner에 source checker와 23개 회귀를 포함: EC2 1대·`t3.small`·exact resource inventory·inbound 0·SSM loopback·Bedrock live 차단, user-data unit write 전 실패 trap과 direct shutdown fallback, 정확한 SSM policy/profile-name 결속, lab nginx 내부경로 deny·보안 header, 두 DB role probe·memory limit·로컬 state/plan/lock/crash 무내용 inventory. 실행 증거는 아님 |
| 미실행 runtime manifest | 전체 100 Windows + 80 macOS와 분리한 3+3 합성 시험 profile은 `NOT_EXECUTED`·Terraform 비관리, 네 앱은 `UNBUILT`·`UNPUBLISHED`로 검사; unknown field·중복 YAML key·경로 이탈·조기 evidence/digest·사람 승인 없는 이미지 출처·approval source 불일치·Terraform comment decoy 등 21개 회귀 통과 |
| 미실행 위험 관찰·lab receipt 계약 | 16개 시나리오는 `DRAFT_NOT_APPROVED`·`NOT_EXECUTED`, 합성 stub·성공 mode·raw prompt 기록 활성·Bedrock 비활성 전용, 자동 실행·자동 위험 판정 금지로 검사. API token/회원 `active` 게이트와 담당자-기업 논리 연결 관찰은 조건부 정확히 한 행 변경·즉시 복구를 요구하고, 브라우저 저장 상태·token 만료·조직 membership/role 수명주기·교차 저장소 부분 commit fault injection은 미관찰로 고정한다. receipt v2 schema는 네 app과 열여섯 scenario를 canonical 순서로 각각 정확히 한 번, source/archive/manifest/API surface/API effect/plan/schema/deploy hash, 원문 없는 cleanup identifier/prompt-pair 집합 hash, provider 모순 금지, Bedrock mode에서 위험 관찰 `NOT_RUN`, 비판정 관찰 상태·사람 검토를 요구한다. 시나리오별 source/result/evidence digest, source payload bytes·parsed plan 결속, 허용된 집계 evidence payload와 result 의미, 전체 완료 또는 `COMPLETED* → FAILED → SKIPPED_AFTER_FAILURE*` 관계를 순수 instance validator로 검사한다. `AuditEvent.detail` JSON key 조회가 두 위치 모두 `detail::jsonb ? ...`를 쓰는 정적 회귀를 포함해 74개가 통과하며, 선택적 `jsonschema`가 없어도 같은 순수·구조 회귀가 실행된다. schema·validator만 있고 실제 receipt·archive member hash·승인 참조 ingestion·서명·실행 증거는 없음 |
| lab 비용 plan fixture | 정상 1건과 실패 16건의 예상 exit code 일치; 관리형 SSM parameter·key/local file/ingress 계열을 현재 lab resource allowlist에서 제거 |
| lab 스크립트 구문 | PowerShell parser 오류 0건, Python AST 3개 오류 0건; 실제 AWS CLI·SSM·Docker 실행은 하지 않음 |
| 로컬 Terraform artifact inventory | ignored backup에 과거 managed instance record 18건, 추가 state artifact 1건, lock 1건, saved plan/JSON 4건, provider cache 약 838 MiB 관찰; 값은 출력하지 않았고 보관·폐기는 사람 결정 |
| 저장소 가드레일 회귀 | `tests/run_all_tests.sh` PASS 94·FAIL 0·exit 0. A 8, B 2, C 5, D 7, E 3, F 4, G 2, H 9, I 8, L 4, M 2, J 2, K 8, N 30건이다. N에는 API decoder·반환/직접 예외·OpenDART adapter/API/worker·API 경계·8/28 멘토 요구사항·합성 MLOps·서버리스 Terraform exact-plan 계약이 포함된다. 이는 source/static/fixture 기대 exit 일치이며 live runtime 94건이 아님 |
| 비밀값 패턴 검사 | 저장소 파일 전체 검사에서 탐지 0건; 실제 credential 유효성이나 외부 저장소 상태를 뜻하지 않음 |

Docker 런타임 smoke·DB 경계 시험은 이번 변경 뒤 다시 실행하지 않았다. 위의 2026-08-27
런타임 관찰값은 이전 실행 기록이며 신규 기업 홈·파이프라인 동작을 증명하지 않는다.
Terraform 1.15.9로 독립 `terraform/serverless-mlops` root의 `terraform validate`와
AWS-free disabled stage 실제 plan 0건을 확인했다. `terraform/asis`의 110개 mock plan과
`terraform/lab` AWS plan은 이번에 다시 실행하지 않았고 AWS apply도 수행하지 않았다.

AWS 공식 문서는 container 환경에서 IMDSv2 hop limit 1이면 응답을 받지 못할 수 있다고
설명한다. 현재 lab은 다른 container까지 instance role에 접근시키는 단순 hop 2 변경을 하지
않고 Bedrock live를 fail-closed로 막았다. gateway 전용 credential 전달 경계는 미구현이며,
따라서 Bedrock 실행 검증 결과는 없다.
