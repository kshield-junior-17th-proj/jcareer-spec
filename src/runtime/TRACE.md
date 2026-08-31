# J-Career TRACE / JC-RECEIPT

이 디렉터리의 TRACE 구현은 기존 합성 AS-IS 추천 결과에 붙는 권리·증적 계층이다. 합격 결정 AI, 자동 이의판정, ISO 충족 판정 또는 잔여 위험 판정이 아니다. 점수와 재계산은 기존 `deterministic-0.2.0` 매처의 `70/20/10` 산식만 사용한다.

## 실행 모드

`TRACE_MODE` 기본값은 `disabled`다.

- `disabled`: 기존 추천 응답을 그대로 반환하고 새 receipt를 만들지 않는다.
- `shadow`: receipt 저장을 시도하되 실패해도 기존 추천 응답을 반환한다. 응답의 `trace_receipt.source_status`에 관찰 상태만 남긴다.
- `enforced`: receipt가 canonical JSON SHA-256과 함께 저장되지 않으면 추천 결과 대신 `503 TRACE_RECEIPT_UNAVAILABLE`을 반환한다. 같은 idempotency key가 다른 관찰값에 재사용되면 `409`를 반환한다.

기존 AS-IS MLOps 산출물과 명칭·테이블을 공유하지 않는다. TRACE는 기존 outcome DB 안의 `trace_decision_receipts`, `trace_recourse_cases`, `trace_human_review_records` 세 테이블만 사용하며 새 AWS 또는 Terraform 리소스를 요구하지 않는다.

## 최소 저장 범위

Receipt에는 가명 subject ref, 공고·기업 ref, 사용·일치·제외 feature ID, 숫자형 score breakdown, matcher/formula/policy/runtime-dataset/provider-config fingerprint, UTC timestamp, 불투명 evidence ref만 저장한다. 이름, 이메일, 전화번호, 주소, 학교, 자격증, 프로젝트, 자기소개 원문, 설명용 label/calculation/evidence 문자열은 receipt projection에서 제외한다. 요청의 `Idempotency-Key`도 원문 대신 SHA-256 기반 request ref로 저장한다.

정정 요청은 구조화된 직무·기술·경력 값을 기존 매처에 일회성으로 전달하지만, case에는 그 값 자체가 아니라 정정 feature ID와 original-vs-corrected score observation만 저장한다.

## API와 권한

- `GET /api/v1/trace/status`
- `GET /api/v1/trace/receipts[/{receipt_id}]`
- `POST /api/v1/trace/receipts/{receipt_id}/recourse`
- `GET /api/v1/trace/cases[/{case_id}]`
- `POST /api/v1/trace/cases/{case_id}/reviews`

후보자는 자기 가명 subject에 결속된 receipt/case만, 채용 담당자는 현재 자기 기업의 공고에 결속된 항목만 조회한다. `UPHOLD`, `CHANGE`, `REQUEST_INFO`, `ESCALATE` disposition은 admin reviewer만 기록할 수 있다. Case version과 idempotency binding은 재시도와 동시 갱신 충돌을 구분한다.

## 검증

```powershell
python -B src/runtime/tests/trace_receipt_contract.py
npm run verify --prefix src/runtime/web
npm run build --prefix src/runtime/web
```

첫 시험은 canonical hash, tamper detection, no-PII 직렬화, 동일 요청 재시도/충돌, cache hit 출처, 세 역할 권한, Recourse Twin, 상태 전이, 사람 처분, shadow 비차단 및 enforced fail-closed를 독립 임시 SQLite DB에서 확인한다.
