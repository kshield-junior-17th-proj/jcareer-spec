# J-Career AS-IS runtime 검증 기록

기준일은 2026-08-30이다. 이 문서는 로컬 합성 런타임에서 관찰한 사실과 범위 한계를
기록한다. ISMS 또는 ISO/IEC 42001의 충족 여부, 인증 가능성, 잔여위험 수준을 판정하지
않는다.

## 2026-08-30 현재 경계

- 최신 source/static/fixture 전체 runner는 `PASS=115`, `FAIL=0`, exit 0이다. 별도 Python
  `tests/` unittest discovery는 257/257, MLOps unittest는 22/22, 운영 범위 PowerShell
  parser는 14/14를 통과했다.
  저장소 전체 15개를 확장 검사하면 이번 변경에 포함되지 않은 `migration/`의 기존 스크립트
  2개에서 parser 진단 6건이 남는다. 이는 live runtime이나 통제 충족 건수가 아니다.
- 이번 보강 중 별도 세션에서 공유된 격리 Compose 재검증 기록은 여섯 서비스 healthy,
  smoke·API 경계·점수·DB 경계·보안·복원력·양면 관찰 스크립트 PASS, cleanup exit 0과
  container·volume·network·image 잔존 0이었다. 그 뒤 OpenDART·MLOps·Bedrock broker·승인형
  wrapper 소스가 바뀌었으므로 이 기록을 현재 소스의 실행 증거로 사용하지 않는다.
- `terraform/asis`는 적용하지 않았다. AWS Lab 관찰은 아래처럼 서로 다른 시점의 기록이다.

| 관찰 시각 | 계획·상태 | 실행 결과 |
|---|---|---|
| 2026-08-28 19:04 KST~2026-08-29 | 당시 HTTPS Lab 관리 자원 17개 | 여섯 서비스와 합성 시험을 관찰한 뒤 저장된 삭제 계획으로 지워 0개를 확인했다. 이후 소스 변경분의 실행 증거로 쓰지 않는다. |
| 2026-08-30, 1차 최종 확인 20:08 KST | 새 계정에서 생성 24·변경 0·삭제 0 계획 | IAM 역할 생성 권한 부족으로 중단됐다. 부분 생성된 16개만 저장된 삭제 계획으로 지우고 관련 조회와 상태에서 0개를 확인했다. |
| 2026-08-30, 재시도 최종 확인 21:17 KST | 새 토큰으로 다시 만든 생성 24·변경 0·삭제 0 계획 | 같은 권한에서 다시 중단됐다. 허용된 그래프의 부분집합 16개만 지운 뒤 VPC·서브넷·NAT·탄력적 IP·실행 인스턴스·CloudFront 함수/배포·Lab IAM 역할·Lab 예산·Terraform 상태가 모두 0임을 확인했다. 전체 애플리케이션은 기동하지 못했다. |

- 이후 소스 변경 뒤 Docker·원격 runtime smoke는 다시 실행하지 않았다. 아래 런타임 관찰은
  최신 source의 실행 증거가 아니라 각 표에 적힌 시점의 기록이다.
- 20:08의 1차 기록과 21:17의 재시도 기록은 서로 다른 실행이다. 계획 24개와 부분 생성
  16개를 합산한 수치로 읽지 않는다.
- 2026-08-28 실행과 2026-08-29 제거 기록은 원본 작업 트리의
  `context/findings/AWS_LAB_RUNTIME_OBSERVATION_2026-08-28.md`에 두었다. 공개 저장소에서는
  2026-08-30 기록을 `terraform/lab/DEPLOYMENT_OBSERVATION_2026-08-30.md`로 제공한다.

## 검증 범위

- 대상: `web`, `api`, `agent`, `llm-gateway`, 세 논리 DB를 가진 PostgreSQL, Redis의 Docker Compose 실행
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
| `python tests/score_contract.py` | 기술 70·경력 20·직무 10 산식, 다단어 한국어 직무 일치, 빈 희망직무 0점, 반올림 계약, invalid 요구 기술 422, 설명 경로 9개 준비 필드/6개 PII 분류, overclaim 문장 미차단·점수 덮어쓰기 불가 |
| `python tests/smoke.py` | 공개 공고, 세 역할 로그인, 후보자·기업 추천, 파이프라인, 관리자 감사 조회, 내부 health 경로 응답 |
| `python tests/security_smoke.py` | 핵심 동의 전 이력서 저장 409·철회 후 추천 409, 실제 도메인 형식 이메일 및 일반 전화 형식 거부, 변조 토큰 401, 역할 교차 403, 기업 교차 조회·수정 403, 거부 감사기록, 탈퇴 토큰 401 |
| `python tests/api_boundary_contract.py` | 서비스 기동 없이 이메일·동의 version DB 길이, 공고 요구기술 정규화, matcher feature·정렬, 설명 envelope, Redis JSON shape 경계를 확인 |
| `python tests/resilience_smoke.py` | timeout·429·503·malformed 각각 추천 HTTP 200, 점수·순서 유지, 설명만 `UNAVAILABLE_PROVIDER`, 장애 응답 cache miss |
| `python tests/database_boundary.py` | 당시 버전에서 회원 DB 5개·기업 DB 2개 테이블, 두 app role의 반대 DB CONNECT 거부, 양쪽 DB 행 존재와 회사 프로필 조회를 관찰. 현재 소스는 가입 응답 UUID와 두 DB 행의 정확한 논리 연결·합성 행 cleanup에 더해 합성결과 DB 2개 테이블과 세 role의 자기 DB 외 여섯 연결 조합 거부까지 검사하지만 이 보강본은 미실행 |
| Redis+LLM 동시 중단 뒤 API 재기동 | API·공고·matcher 추천 동작, 설명 `UNAVAILABLE_PROVIDER`; Redis DNS 대기와 Nginx의 이전 컨테이너 IP 고정 문제를 발견해 비동기 제한시간·Docker DNS 재해석으로 수정 후 재시험 통과 |
| LLM 복구, Redis 중단 유지 | 설명 즉시 `AVAILABLE`, cache miss |
| Redis 복구 | 첫 호출 cache miss, 다음 호출 cache hit |
| 손상된 Redis JSON | 손상 값을 cache miss로 처리하고 정상 추천 응답으로 교체 |
| matcher 중단 | 공개 공고 조회 200, 캐시를 비운 추천 요청 503; matcher 복구 후 smoke 재통과 |
| PostgreSQL 중단 | API health 500과 일반 오류문 반환; DB 복구 뒤 여섯 서비스 health 복구 |
| 합성 canary 탈퇴 | 주 DB 이력서·지원관계 제거 및 기존 토큰 401; 직전에 생성된 추천 캐시는 hit로 남고 raw prompt 볼륨에서도 canary 1건 관찰 |
| prompt metadata 검사 | 각 레코드의 PII 준비 필드명이 `address,birthdate,email,name,phone,school`과 정확히 일치하고 `certificates,projects,self_intro` 준비 필드 기록 존재. 외부 공급자 수신 증거는 아님 |
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

마지막 스크립트는 이번 보강 중 공유된 격리 Compose 통합 재검증에서 실행되어 PASS했다.
다만 이는 승인된 위험 관찰 plan이나 receipt ingestion 실행이 아니므로
`risk_observation_plan.yaml`의 `DRAFT_NOT_APPROVED`·`NOT_EXECUTED` 상태는 유지한다.
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
건 남는지를 내용 출력 없이 확인하는 probe도 해당 스크립트 assertion으로 통과했다. raw prompt
log line은 삭제하지 않았다. 이 사실은 assertion 통과만 뜻하며 승인된 증거 package, 취약점 판정,
관리체계 또는 법적 요구 충족을 뜻하지 않는다.

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

## 2026-08-28~30 변경분 정적 검증

기업 고객 운영 홈, 파이프라인과 점수 설명 UI 보강 뒤 AWS·Docker 서비스를 켜지 않은 상태에서
다음을 확인했다.

| 검사 | 관찰값 |
|---|---|
| 최신 JSX·bundle 정적 빌드 | `App.jsx` esbuild JSX transform과 Vite production build 완료(40 modules). browser render·container image·배포 증거는 아님 |
| 웹·관찰 시나리오 정적 계약 | 필수 84개·금지 회귀 13개 검사와 기업 직접문구 근거 validator 8/8 완료; 플랫폼 공통 우선요인과 기업별 가중치 미적용 문구, 기업 프로필 출처, 기업용 직접 문구 근거의 점수·순위 무영향 및 cache snapshot 경계, cache 원본 필드 미검증 표시, 필수·선택 동의와 실제 정책 버전 복원 및 선택 grant 중복 방지, 저장 응답 기반 이력서 정규화, 반복 disclosure 고유 이름, pipeline 취소 focus·Resume 없는 지원 제외 경계, 감사 필터 이름·machine-readable time, 구직자/기업 계정 수명주기 안내 분리, 재시도 button type, 지원·공고상태 변경 뒤 focus 복원, 모바일 실제정보 금지 문구, 늦은 GET 응답 무시, 추천 완료·저하 상태 1회 접근성 알림, 요청 중 새로고침 잠금, 긴 고객 문자열 협폭 줄바꿈, 검증 미적용 생성 설명 기본 접기, token·user 부분 세션 및 storage 예외 처리, 손상 세션과 local storage 삭제 성공/확인 실패 안내, 빈 상태부터 유지되는 polite status와 닫기 뒤 focus 복원, 로그인·양측 가입 form의 form 밖 진행 status·`aria-busy`·API 입력 길이 경계·중복 요청 방지, 401 원인 단정 금지와 초안 확인, 현재 token과 일치하는 401만 세션 신호로 처리, 요청 timeout·취소·network 오류 구분, 양면 관찰 스크립트의 stub-only gateway 가드 포함 |
| 브라우저 API response decoder | 순수 Node `Response`·fetch stub 11/11: JSON, text, 204, 빈 200, malformed JSON, body read 실패, 현재 token의 401 신호-before-decode와 Authorization header, 이전 token의 늦은 401 무시, 요청 timeout·caller 취소·정제된 network 오류 분류를 검사. 실제 browser navigation·network·server 응답 증거는 아님 |
| Python AST | API와 API 경계·security smoke·양면 AS-IS 관찰·runtime/Terraform 검사기 소스 구문 분석 완료 |
| Python import | FastAPI route 등록 완료: API 34, agent 10, llm-gateway 8 |
| PostgreSQL 검색 쿼리 컴파일 | 공개 공고의 `required_skills` 검색과 `open` 상태 조건 포함 |
| API 경계 계약 | 서비스 기동 없이 입력 길이·공백, 공고·이력서 기술의 동일 comparison key 정규화, 공고·기업 프로필 변경에 따른 후보자 추천 cache key 교체, 빈 설명 요청 단락, matcher 표시 metadata/순서, 설명 field/hash/alignment envelope, Redis JSON shape, 결정론 seed sentinel을 확인했다. 기업용 `recruiter_review_support`는 직접 문구 근거와 source version만 반환하고 점수·순위·자동판정 무효화 boolean을 고정하는 순수 helper 회귀를 통과했다. 실제 API 실행 증거는 아니다. |
| 합성 DB 서버리스 MLOps | MLOps 단위 22개와 서버리스 경계 19개 시험 통과. attestation·두 DB 분리·전체 candidate read set의 합성 연락처 표식·전체 company/job join의 exact seed profile 표식·미해결 참조 거부·5개 feature allowlist·자소서와 검토된 프로젝트 필드의 토큰 겹침 특징·엄격한 snapshot 검증·원문 canary 미잔존·조건부 `RUNNING → TRAINED_PENDING_HUMAN_REVIEW`·자동 활성화 차단을 검사한다. 6개 결과 객체는 create-only 업로드와 S3 key·SHA-256·VersionId 결속을 요구하며, 별도 사람 입력은 결속이 일치할 때만 `HUMAN_INPUT_RECORDED`와 `APPROVED|REJECTED`를 기록하고 `release_authorized=false`를 유지한다. 객체 일부만 남은 경우는 완료 신호가 아니다. `RUNNING` 상태·사람 입력 미기록·합성/source mode·비활성 invariant가 모두 유지될 때만 pending으로 전이한다. `RUNNING` 기록 뒤 오류는 `FAILED_SAFE` 기록을 시도하지만, enablement·attestation·event·run ID·source mode·config 검증이나 최초 `RUNNING` 쓰기에서 거부되면 `FAILED_SAFE` 기록 전 종료될 수 있다. 별도 합성결과 DB의 `passed/not_passed`는 label로 사용하지 않고 여러 합성 회사 행은 platform-wide challenger에 합쳐지며 token-overlap 특징은 문구 복사로 게이밍될 수 있다. exporter는 application-time snapshot이나 공통 transaction/watermark 없이 현재 resume/job/company와 현재 지원 상태를 결합한다. `privacy_core`는 학습 동의가 아니고 이후 철회·탈퇴가 기존 파생물을 무효화하지 않는다. S3 lifecycle 뒤에도 TTL 없는 run state가 남을 수 있으며 review path는 bound VersionId의 현재 존재를 다시 확인하지 않는다. 보호된 operator 흐름은 pending에서 끝나고 runtime UI·dashboard review 연계는 없다. MLOps operator는 승인된 provider account digest를 단계마다 재검증하고 absolute executable·shadow/reparse 거부·plan/JSON read-lock·SHA 재확인을 source로 요구하지만 remote state와 purge/destroy는 없다. seed profile 표식은 DB 직접 공고 본문 덮어쓰기를 암호학적으로 증명하지 않는다. 실제 plan JSON의 stage별 exact address는 disabled 0, bootstrap 13, runtime 14로 검사하며 현재 암호화 배선은 SSE-S3(AES256)뿐이고 KMS·DB URL·VPC·SageMaker·EventBridge·자동 활성화는 없다. AWS-free disabled plan 0건과 `terraform validate`는 과거 확인 기록이며 이번 보강에서는 Terraform을 실행하지 않았다. 실제 runtime ORM seed를 별도 임시 SQLite에 생성한 과거 일회성 교차검증은 53행·28명·6산출물, `TRAINED_SYNTHETIC_RUNTIME_DATA_NOT_APPROVED`, `runtime_wired=false`, 임시정리 성공이었다. AWS apply·이미지 push·Lambda 호출·Docker 실행 증거는 아님 |
| OpenDART 서버리스 배선 | OpenDART 계약 36, API 경계 16, 작업자 12, durable 결과함 9개 계약, Terraform 경계 9개와 worker 게시기 13개 회귀를 통과했다. API→SQS FIFO→VPC 밖 Lambda→OpenDART→DynamoDB TTL 결과함→인증 API 회수 구조이며 worker source에서 과거 PostgreSQL 직접쓰기 경로를 제거했다. 공개 snapshot은 self hash와 source kind·합성 여부의 일관성을 검사하지만 DB writer가 hash를 다시 계산할 수 있으므로 서명된 공급자 receipt는 아니다. API는 DynamoDB의 지연 삭제와 별개로 만료시각을 직접 검사하고, 중복 요청 억제·timeout·expiry·result 반영을 현재 pending request의 DB CAS로 제한한다. `OPENDART_AWS_BROKER_SOCKET`이 비어 있고 queue URL만 있으면 API가 direct boto3 SQS client로 fallback하므로 lab broker 강제와 비-lab 실행 호환성 중 어느 경계를 채택할지는 사람 결정이다. source 단계 계약은 기본 0·bootstrap 8·runtime 11개 address를 검사한다. 빈 상태에서는 최종 HTTPS 형태의 OpenDART-off lab→OpenDART root→OpenDART-on lab의 세 별도 승인 단계와 역순 제거를 요구한다. 게시기는 고정 저장소 경로·보호 입력 snapshot·PowerShell/외부 checker 이중 승인 검사, tool/checker/backend hash, 실제 ECR immutable/scan-on-push/AES256 구성, Docker push/ECR digest, 전용 Docker 인증 정리를 결속하고 `Prepare`와 `Review`는 push할 수 없게 한다. 예시와 Review 산출물은 pending이다. 별도 서명·신뢰 승인 저장소·cross-host mutex는 없으며 backend 변경 뒤 승인 backend의 current plan/validate, image build·scan·push, AWS apply·OpenDART 실호출·외부 응답 receipt는 없음 |
| 업무망 단말 이미지·배치 | Windows Server 2022 Desktop simulation의 Image Builder source는 definition 12개, 별도 endpoint root는 t3.small Windows 3대 stage 9개를 계약하고 둘 다 기본 disabled 0개다. 이미지는 version-pinned parent·IMDSv2를 요구하고 Firewall/Defender 부재 또는 RDP 허용 policy·TCP 3389 listener·enabled inbound Windows Firewall rule 부재 시 build test를 실패시키며 사용자·AWS·SaaS·OpenDART·preview credential을 넣지 않는다. 이는 endpoint SG inbound를 여는 것이 아니며 실제 접속은 승인된 SSM tunnel 경로다. 임시 build/test 인스턴스에도 build lineage tag를 전파하고, 별도 lifecycle 역할은 사람 승인형 AMI·snapshot cleanup에만 사용한다. 단일 build·관찰·artifact cleanup 승인 계약 5개와 네 PowerShell wrapper parser 오류 0건을 확인했다. endpoint image receipt v2는 AMI·build ref·source hash와 private/encrypted/tested build observation SHA를 saved plan에 결속한다. Windows·macOS 모두 Slack/OpenDART 바로가기와 credential-free preview 세션 source를 갖지만 macOS는 물리 Mac+MDM source뿐이고 EC2 Mac 자원은 0개다. 실제 image build·AMI·단말·로그인·posture 관찰은 없음 |
| 합성 시연 readiness preflight | source-only/read-only checker와 10개 회귀가 네 app digest·clean HTTPS URL hash, Windows 3대의 image/build/endpoint/session 결속, 로컬 도구 경로, macOS 물리/MDM 사람 관찰 record의 구조를 fail-closed로 검사한다. 저장소 example은 `NOT_READY`이고 실제 operator-private observation은 공급되지 않았다. 최대 출력인 `READY_FOR_HUMAN_RUN`도 승인·live·사용성·적합성 판단이 아님 |
| saved-plan 배포·제거 승인 gate | deployment approval 단위 회귀 20개와 PowerShell wrapper 2개의 parser 오류 0건. 승인 record schema v3는 비어 있거나 placeholder 형태가 아닌 provider account SHA-256을 요구한다. plan-only는 account 원문을 메모리에서만 해시하고 digest만 출력·보호 binding에 저장하며, apply와 teardown은 실행 직전·완료 기록 전에 digest를 재확인한다. 생성은 암호화 S3 remote state·lockfile·root별 state key, exact saved-plan SHA-256, backend config SHA-256, OpenDART runtime plan image digest 또는 Windows AMI receipt를 결속한다. OpenDART bootstrap 승인은 Lambda digest를 금지한다. 정상 제거는 bootstrap/runtime 등 stage별 exact address set만, 부분 apply 실패 복구는 별도 recovery scope와 별도 사람 승인으로 non-empty allowlisted delete-only subset만 허용한다. pending example은 apply를 승인하지 않고 checker도 승인 결정을 만들지 않는다. 생성·제거 apply 명령은 이번 검증에서 실행하지 않음 |
| API source surface | 35개 handler·40개 decorator route, request model·역할·선택 tenant marker와 기업 담당자 탈퇴/소유권/동의/상태전환 부재, 현재 지원자료 참조, 추천·cache-hit 감사 부재, cache provenance 공백, 동의 catalog·matcher·gateway field matrix와 상이한 철회 event shape를 source state와 함수 fingerprint로 대조. 새 OpenDART result collect route는 recruiter의 연결 기업과 pending request를 기준으로 결과를 검증한다. 관리자 전용 AI 운영 스냅샷은 strict response model, admin role dependency, 성공 조회 감사, `no-store`와 1초·streaming 16KiB 내부 health probe를 선언하고 UI는 브라우저 수신 후 30초 timer로 stale 전환하되 외부 호출·AWS 배포 증거로 표시하지 않는다. API middleware는 `/api/` 응답 전체에 `Cache-Control: no-store, private`와 `Pragma: no-cache`를 붙이므로 admin audit도 source상 포함하지만 proxy 전달·browser bfcache·logout 뒤 복원은 실행하지 않았다. 서버측 요청 제한과 실패 조회 audit은 없다. 브라우저 `localStorage` token/user 복원, 시작 시 role schema 검증 부재와 `Protected` 경로별 role allowlist 비교 존재, `/auth/me` 시작 재검증과 cross-tab sync 부재를 구분한다. API의 token `sub`→활성 회원 DB 사용자 및 DB role 권한원, 고정 합성 signing-key fallback·43,200초 TTL·`iat`/`jti`/server session/logout/revoke/refresh 부재·missing `sub` guard 공백도 분리해 고정하며 회귀 44개 통과. 브라우저 UI 신뢰 공백은 서버 BOLA 성공 증거가 아니다. legacy `required_calls`는 AST symbol 존재일 뿐 분기 실행 증거가 아니며, 실행 API·완전한 DB read/write graph·wire response/error 계약도 아님 |
| API source effects | 같은 35개 handler의 회원/기업/outcome DB·감사·Redis·agent·gateway·prompt-log·SQS·DynamoDB 결과함 효과와 주요 분기를 source review 선언으로 고정. 전 handler·20개 helper AST 지문과 기업 가입·양측 추천 cache 순서·기업 원문 근거 생성·overview/pipeline/admin 감사·gateway prompt/provider의 선택된 9개 lexical path를 검사하며 회귀 17개 통과. CFG dominance, 실행 cardinality, 원자성, downstream 수신 또는 실행 trace는 아님 |
| API source 반환·직접 예외 | 같은 35개 handler·40개 route의 직접 `return` 표현식, route 성공 status, handler 본문 literal `HTTPException`을 AST와 upstream contract hash에 결속하고 부정 회귀 14/14 통과. literal object 최상위 key만 기록하며 cache는 `CACHED_OBJECT_VALIDATED_SUBSET`, helper/local name은 미확장이다. dependency·helper·downstream·422·500·header·serialization·nested schema와 실행 응답은 범위 밖 |
| runtime/Terraform 소스 계약 | 지원자·기업 API method/path, 기업 홈 필수 route, 세 DB engine bind·로컬 전용 role/DB 초기화, 데이터 소유, Compose 서비스별 배선과 회원·기업·합성결과 DB 이름·role 분리 선언 대조 및 검사기 단위 회귀 통과. Terraform AS-IS는 회원·기업 DB URL까지만 모델링하고 합성결과 DB는 미배선이다. Terraform output과 기업 홈 API는 조직 멤버십·담당자 탈퇴·소유권 이전·기업 동의·상태 전환·상태 행위자·상태 게이트, 공고 UUID 논리 참조·교차 DB 원자성·operation ID·멱등 키·보상·사후 조정·outbox 공백을 같은 source state로 드러내며 resource block은 추가하지 않음. `/recruiter/overview` 화면 상한 예외, Terraform S3·DB-only runtime 간극, raw prompt 보존 정책은 사람 결정 경고로 남김 |
| 양면 고객 정적 계약 | API·기업 홈·Terraform 출력에 담당자-기업 논리 연결, 가입 시 첫 담당자 생성, 기업별 담당자 수 제약 부재, 조직 멤버십 미구현, 기업 상태 게이트 미적용 표현 존재 |
| 독립 변경분 재검토 | 현재 이력서 경계, 상태 저장 피드백·포커스 복원, 모바일 로그인·DOM 순서, 동의 복구 경로, 설명 검증상태 fail-closed 표시, 기업 프로필 provenance, 기업 lifecycle source-state 비과장 표현, 양측 공동 관찰의 단일 ID·다중 lane 투영 반영 확인 |
| `git diff --check` | 추적 파일 공백 오류 없음 |
| `scripts/check_asis_contract.py` | `.tf` 38개, 금지 data source 없음, mock provider 플래그 확인 |
| 컨설턴트 dashboard | snapshot validator·view-model·source artifact 결속 28개 통과. 한 관찰의 양측 metadata 투영과 고유 건수 유지, 보이지 않는 문자·양방향 표시 제어문자 거부, CSP `connect-src 'none'`, network API·browser persistence·판정 계산 심볼 없음, `EXTERNAL_PREVIEW` fail-closed, loaded/error 제목 focus는 모바일에서 화면 밖에 숨지 않도록 스크롤 허용. packager는 이미 승인된 snapshot의 source SHA-256만 확인하고 판단을 생성하지 않으며 실제 승인 입력·package 실행 증거는 없음 |
| dashboard 빈 상태 브라우저 확인 | loopback 요청만 관찰, console 오류 없음, 승인 입력 부재를 숫자 없이 표시; 확인 뒤 임시 서버 종료 |
| AWS 다이어그램 원본·PNG | 공개 기준 도면 `terraform/asis/JCAREER_ASIS_FLOW.drawio`는 58개 셀·14개 연결이며 같은 이름의 2400×1400 PNG와 함께 검사한다. 77개 셀·23개 연결은 원본 작업 트리의 별도 상세 도면 기록으로, 공개 기준 도면 검사 수에 합치지 않는다. 공개 도면은 6단계 기준 AWS 흐름, 기준 110개와 분리된 default-off MLOps 흐름, 업무망 선언과 AWS 흐름선이 없는 Slack 외부 SaaS 경계를 보여 준다. MLOps의 추가 여섯 연결은 별도 0/13/14 계획을 설명하며 AWS 실행 증거가 아니다. |
| 미래 lab 정적 경계 | lab static 단위 회귀 100개를 포함: EC2 1대·`t3.small`·기본 13/Bedrock 포함 14/HTTPS 프리뷰 23/HTTPS+Bedrock 24 exact resource inventory·기본 inbound 0·승인 모드 CloudFront 관리형 prefix-list TCP/3000만 허용·직접 CIDR 금지·SSM loopback·Bedrock 기본 비활성·승인 전 차단, OpenDART clean-state 3단계/역순 제거와 Prepare→Review→사람 결정→Publish 문서 순서, deploy-broker 이름 경계, user-data unit write 전 실패 trap과 direct shutdown fallback, 정확한 SSM policy/profile-name 결속, lab nginx 내부경로 deny·보안 header, 회원/기업 role probe와 outcome 연결·memory limit·saved plan/JSON lock·SHA·provider account digest 재확인. 생성·제거 plan-only는 provider account, exact binary plan, 최상위 timestamp를 제외한 normalized JSON projection digest를 출력한다. apply는 재계획하지 않고 보존된 binary plan·JSON과 세 digest를 확인한다. provider/모든 Terraform 명령 전에 공통 경로 mutex와 same-worktree exclusive file lock·pending marker 검사를 수행하고, stable plan을 GUID operation path로 이동해 durable marker를 만든 뒤 그 binary만 소비한다. marker 생성부터 apply·계정 재검사·artifact cleanup까지 중단·실패하면 marker와 operation artifact를 남겨 후속 wrapper를 막고 사람의 state 확인·처분을 요구한다. marker는 runtime upload/remote check 및 destroy 후 state inventory 전에 제거되므로 그 이후 검증 실패의 표식은 아니며, 직렬화는 복제 worktree나 다른 host까지 확장되지 않는다. Terraform 변수인 runtime mode·승인문·HTTPS token digest도 대조한다. HTTPS token은 같은 operator-retained SecureString을 요구하고 1~32자 period와 최소 다양성 placeholder를 거부하지만 CSPRNG 사용 자체를 증명하지 않는다. JSON projection은 정식 canonical JSON으로 주장하지 않으며, OpenDART 실호출·browser open·backend/receipt 경로 같은 post-apply 실행 의도는 plan digest에 포함되지 않는다. auto-stop output은 기존 host의 실제 timer 관찰값이 아니라 구성 입력값임을 명시한다. source 계약이며 최신 runtime 실행 증거는 아님 |
| 미실행 runtime manifest | 전체 100 Windows + 80 macOS와 분리한 3+3 합성 시험 profile은 `NOT_EXECUTED`·Terraform 비관리, 네 앱은 `UNBUILT`·`UNPUBLISHED`로 검사; 상류 manifest 21개 회귀와 별도 endpoint review pack의 37개 fail-closed 회귀가 중복 YAML key 거부, profile 결속·가명 asset ID·`devices_exist=false`·`NOT_PROCURED`·posture 전량 `NOT_OBSERVED`를 확인한다. 실제 단말·이미지·직원 신원·office network 증거는 아님 |
| 미실행 위험 관찰·lab receipt 계약 | 16개 시나리오는 `DRAFT_NOT_APPROVED`·`NOT_EXECUTED`, 합성 stub·성공 mode·raw prompt 기록 활성·Bedrock 비활성 전용, 자동 실행·자동 위험 판정 금지로 검사. API token/회원 `active` 게이트와 담당자-기업 논리 연결 관찰은 조건부 정확히 한 행 변경·즉시 복구를 요구하고, 브라우저 저장 상태·token 만료·조직 membership/role 수명주기·교차 저장소 부분 commit fault injection은 미관찰로 고정한다. receipt v2 schema는 네 app과 열여섯 scenario를 canonical 순서로 각각 정확히 한 번, source/archive/manifest/API surface/API effect/plan/schema/deploy hash, 원문 없는 cleanup identifier/prompt-pair 집합 hash, provider 모순 금지, Bedrock mode에서 위험 관찰 `NOT_RUN`, 비판정 관찰 상태·사람 검토를 요구한다. 시나리오별 source/result/evidence digest, source payload bytes·parsed plan 결속, 허용된 집계 evidence payload와 result 의미, 전체 완료 또는 `COMPLETED* → FAILED → SKIPPED_AFTER_FAILURE*` 관계를 순수 instance validator로 검사한다. `AuditEvent.detail` JSON key 조회가 두 위치 모두 `detail::jsonb ? ...`를 쓰는 정적 회귀를 포함해 74개가 통과하며, 선택적 `jsonschema`가 없어도 같은 순수·구조 회귀가 실행된다. schema·validator만 있고 실제 receipt·archive member hash·승인 참조 ingestion·서명·실행 증거는 없음 |
| lab 비용 plan fixture | 정상 1건과 실패 16건의 예상 exit code 일치; 관리형 SSM parameter·key/local file/ingress 계열을 현재 lab resource allowlist에서 제거 |
| lab 스크립트 구문 | 운영 범위 PowerShell 14/14 parser 오류 0건, Python AST 3개 오류 0건; 실제 AWS CLI·SSM·Docker 실행은 하지 않음 |
| 로컬 Terraform artifact inventory | 2026-08-30 확인 시 ignored backup 1개에 과거 managed instance record 21건, 추가 state artifact 1건, lock 1건, saved plan/JSON 9건, provider cache 약 1,691 MiB를 관찰; 값은 출력하지 않았고 보관·폐기는 사람 결정 |
| 저장소 가드레일 회귀 | 2026-08-30 Git Bash에서 `tests/run_all_tests.sh` 전체를 실행해 PASS 115·FAIL 0·exit 0을 확인했다. 범용 fixture 검사는 Git Bash Python을 유지하고 FastAPI·SQLAlchemy·boto3 등이 필요한 7개 계약만 의존성을 import할 수 있는 UTF-8 Python을 선택한다. 중간 114건 실행의 단일 declaration-only import 실패는 순수 validator 시험 분리 후 해소했으며 최종값에 포함하지 않았다. 별도 `tests/` unittest discovery 257/257, MLOps unittest 22/22, 운영 범위 PowerShell parser 14/14도 통과했다. 저장소 전체 15개 검사에서는 현재 diff 밖의 legacy `migration/` 2개 파일에 기존 parser 진단 6건이 있다. 모두 source/static/fixture 기대 exit 일치이며 live runtime 115건이 아님 |
| 비밀값 패턴 검사 | 추적·비추적 저장소 파일 503개에 대한 제한된 패턴 검사에서 탐지 0건. 유효 credential 탐지나 외부 저장소·과거 Git 객체의 무비밀성을 증명하지 않음 |

별도 격리 Compose 통합 재검증에서는 여섯 서비스와 일곱 스크립트가 통과하고 cleanup 잔존이
0으로 공유됐다. 이후 OpenDART·MLOps·Bedrock broker·승인형 wrapper 변경 뒤에는 Docker runtime을
다시 실행하지 않았으므로, 그 결과는 현재 source나 신규 기업 홈·파이프라인의 실행 증거가 아니다.
Terraform 1.15.9로 독립 `terraform/serverless-mlops` root의 `terraform validate`와
AWS-free disabled stage 실제 plan 0건을 확인했다. `terraform/asis`의 110개 mock plan은
이번에 다시 실행하지 않았다. `terraform/lab`에서는 신규 생성이 아니라 기존 단기 lab을
제거하기 위한 17개 delete-only 저장 계획과 apply만 수행했고 현재 state는 0이다.

현재 lab source는 IMDSv2 hop limit을 1로 유지하고, 일반 API·gateway container의 metadata
접근을 끈 채 host-network capability broker만 EC2 instance role을 사용하도록 분리한다. 고정
UID와 `SO_PEERCRED`를 검사하는 서로 다른 Unix socket이 Bedrock 설명 호출과 OpenDART
dispatch/result 연산만 노출한다. 두 broker는 같은 instance role을 공유하므로 이는 process
분리이지 IAM 격리가 아니며, 기본 live 값은 비활성이다. 현재 broker 기동·Bedrock 응답·OpenDART
응답 실행 증거는 없다.
