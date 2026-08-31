# 합성 runtime 소스 계약과 실행 전 manifest

이 디렉터리는 실제 실행 증거가 아니라 아직 만들거나 시험하지 않은 대상을 명시적으로
추적한다. 자동 검증은 AWS, Docker, Git, 브라우저 또는 외부 URL을 호출하지 않는다.

- `mentor_feedback_2026_08_28.json`: Notion `8/28 멘토 회의`의 `0828 회의록 정리본`을
  조직 관찰값·멘토 제안·자산 후보·학습 경계·CEO 보고 후보로 분리한 초안 계약. DevOps를
  별도 팀으로 두지 않고 AI서비스에서 인프라팀 책임으로 이동시키는 안, 인프라팀 하위
  SI팀·데이터팀, 정보보안 Blue·Red·Compliance, 그룹웨어·사내DB 제외, Slack 등 추가 자산
  후보를 기록한다. 조직 기준선·자산 존재·책임자·학습 동의·97개 체크리스트 판정은 확정하지
  않는다. 정보보호시스템의 기존 시나리오 기록·source 모델·멘토 요청 미확인 후보는
  [`../INFORMATION_PROTECTION_SYSTEM_INVENTORY.md`](../INFORMATION_PROTECTION_SYSTEM_INVENTORY.md)에서
  별도 대조한다.
- `endpoint_test_sample.yaml`: 문서상 Windows 100대·macOS 80대 inventory와 별개인
  Windows 3대·macOS 3대 시험표본. 현재 `NOT_EXECUTED`다.
- `application_artifacts.yaml`: `web`, `api`, `agent`, `llm-gateway` 네 앱의 source와
  Terraform model 참조. 현재 모두 `UNBUILT`, `UNPUBLISHED`다.
- `api_surface.json`: 기존 core 세 FastAPI source의 35개 handler·40개 decorator route, 역할·선택된
  tenant marker, Pydantic model 선언과 선택된 기업 계정·현재 지원자료·audit·cache·공개 마감 공고·
  거부 audit tenant shape·동의/설명 필드 matrix·설명 provider 구성 source state, 브라우저
  localStorage 신원 복원과 API의 회원 DB 권한원·custom token/세션 철회 공백을
  버전 고정한 inventory. `AST_PARTIAL`이며 실행된 API, 완전한 DB read/write graph,
  response/error wire 계약 또는 OpenAPI security scheme 증거가 아니다. legacy `required_calls`는
  선택된 AST 호출 symbol 목록으로, 모든 분기에서 실제 호출된다는 뜻이 아니다. 브라우저 역할
  source가 취약한 UI 상태를 만들 수 있다는 기록은 서버 BOLA 성공을 뜻하지 않는다.
- TRACE·JC-RECEIPT router 7개와 외부 업무도구 admin router 2개는 additive guarded surface다.
  각각 `../tests/trace_receipt_contract.py`와 `../tests/integrations_contract.py`에서 별도로 검사하며,
  기존 core inventory 40개에 자동 합산하지 않는다. 기본 비활성 소스·합성 대역 결과일 뿐 실제
  외부 호출, 운영 OpenAPI 또는 AWS 배포 증거가 아니다.
- `api_effects.json`: 같은 35개 handler의 회원/기업/outcome DB·감사·Redis·agent·gateway·prompt·SQS·DynamoDB 결과함
  효과와 주요 분기를 source review 선언으로 정리하고, 전 handler와 20개 helper의 AST 지문 및
  추천·기업 가입·열람 감사·gateway의 선택된 9개 lexical 순서를 검사한다. CFG dominance,
  실제 cardinality, commit 원자성, downstream 수신 또는 실행 증거가 아니다.
- `api_wire_shapes.json`: 같은 35개 handler의 직접 `return` 표현식, 40개 route의 선언된 성공
  status, handler 본문에 직접 적힌 literal `HTTPException`을 source-only로 묶는다. literal
  object의 최상위 key만 기록하고 helper·local name·cache 반환은 펼치지 않는다. 빈 오류 목록은
  dependency·helper·downstream·422·500이 없다는 뜻이 아니며 response model이나 제품 wire
  schema 강제, 실제 HTTP·Bedrock 실행 증거가 아니다.
- `risk_observation_plan.yaml`: 기업·지원자 양측의 현재 source 동작을 나중에 합성 데이터로
  관찰하기 위한 16개 시나리오. 현재 `DRAFT_NOT_APPROVED`, `NOT_EXECUTED`이며 기능 smoke와
  분리되고 자동 실행·자동 위험 판정을 금지한다. 특정 API token/회원 `active` 게이트와 담당자-
  기업 논리 연결 관찰의 시험 전용 회원 상태 변경은 조건부 정확히 한 행 변경·즉시 복구·공통
  cleanup 재시도를 요구한다. 브라우저 저장 상태, token 만료, 조직 membership·role 수명주기,
  교차 저장소 부분 commit fault injection은 명시적으로 미관찰이다. raw prompt 잔존 관찰은 시작
  전에 gateway가 합성 stub·성공 mode·Bedrock 비활성뿐 아니라 raw prompt 기록 활성 상태도
  보고해야 한다.
- `lab_run_receipt.schema.json`: 승인 뒤 별도 lab 실행이 생길 경우 사용할 redacted receipt v2의
  JSON Schema. source archive·manifest·API surface·API effect inventory·관찰 plan·schema·배포 script hash와 네 앱
  digest, 원문 식별자를 싣지 않는 합성 cleanup identifier/prompt-pair 집합 hash를 구분한다. 각
  위험 시나리오는 plan slice와 관찰 script hash에 결속된 source digest, redacted result digest,
  정렬된 redacted evidence manifest digest를 분리하고 `COMPLETED* → FAILED → SKIPPED_AFTER_FAILURE*`
  중단 순서를 표현한다. `PASS/FAIL` 대신 source assertion 일치 여부와 사람 검토 필요 여부만
  허용한다. `validate_receipt_instance`는 전달된 source payload bytes를 전역 hash 및 parsed plan과
  결속하고, evidence는 허용된 비음수 집계 metric만 가진 redacted payload로 제한해 manifest hash를
  재계산한다. source assertion 집계는 result 상태·assertion 수와도 교차 검사하며, 선택적
  `jsonschema` 의존성이 없어도 순수 validator 회귀는 동일하게 실행된다. 이 검사는 메모리 안의 합성
  fixture 검증일 뿐이다. schema와 validator가 있다는 사실은
  receipt·실행·정리·통제 적용이나 원자료 전체의 무민감성을 증명하지 않으며, 실제 archive 포함관계·
  승인 참조·서명·보관을 검증하는 ingestion은 아직 없다.

OS/browser version, image 출처와 승인 참조는 사람이 시험방법과 소유권을 결정하기 전에는
비워 둔다. 나중에 값을 넣으려면 `docs/current/**`의 실제 heading에 `status`, `approved_by`,
`approved_at`, `source_sha256`, `approved_source_ref`가 있는 사람 승인 문서가 필요하고,
`approved_source_ref`는 manifest 값과 같아야 한다. macOS image 배포 제약은
`fleet/README.md`를 따른다. `:asis` ECR URI 문자열은 image, digest 또는 배포 증거가 아니다.

```powershell
python scripts/check_runtime_manifests.py --root .
python tests/test_runtime_manifests.py
python scripts/check_api_surface_contract.py --root .
python tests/test_api_surface_contract.py
python scripts/check_api_effects_contract.py --root .
python tests/test_api_effects_contract.py
python scripts/check_api_wire_shapes.py --root .
python tests/test_api_wire_shapes.py
python scripts/check_runtime_evidence_contracts.py --root .
python tests/test_runtime_evidence_contracts.py
```

검증 결과는 제품·보안통제·인증 판정이 아니다.
