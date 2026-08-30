# J-Career 합성 MLOps

세 가지 재현 경로가 있다.

1. 기존 `generate_synthetic_training.py`는 DB와 무관한 완전 생성형 오프라인 예시다.
2. `run_runtime_pipeline.py`는 합성 회원 DB와 합성 기업 DB를 직접 읽어 challenger를 학습하는 일회성 경로다.
3. `feature_snapshot` Lambda 경로는 DB 옆 exporter가 만든 숫자 특징 CSV 1개와 검증용 JSON 2개를 S3에서 받아 학습한다.

세 경로 모두 현재 결정론적 70·20·10 매처를 바꾸지 않는다. 생성된 모델은
`HUMAN_DECISION_NOT_RECORDED`이며 자동 활성화·자동 배포되지 않는다. 이 소스의 존재는 AWS 배포나
실행을 증명하지 않는다.

## DB 기반 학습 경로

DB 기반 경로는 다음 필드를 읽는다.

- 회원 DB: 이름, 이메일, 연락처, 생년, 주소, 교육, 희망 직무, 경력, 기술, 자격, 자소서,
  지원 상태, 최신 `privacy_core` 이벤트
- 기업 DB: 기업명, 기업 방향, 선언 가치, 공고 제목·본문·요구 기술·최소 경력

학습 데이터셋에는 아래 5개 숫자 특징과 가명 참조만 쓴다.

- `skill_overlap`
- `experience_fit`
- `role_overlap`
- `self_intro_job_overlap`
- `company_direction_overlap`

이름·이메일은 전체 source lineage 해시에만 반영되고 학습 특징이 아니다. 자소서와 기업·공고 원문은
DB 옆 exporter 프로세스에서 특징으로 변환한 뒤 dataset·receipt·model artifact에 기록하지 않는다.

`self_intro_job_overlap`과 `company_direction_overlap`은 현재 토큰 겹침 proxy다. Bedrock 임베딩이나
문맥 이해 결과가 아니므로 정성적 적합도를 충분히 측정한다고 주장하지 않는다. 현재 Bedrock 설명
경로는 별도로 정성 근거를 문장화하지만 점수·순위를 바꾸지 않는다. 임베딩 기반 의미 특징을
challenger에 추가하는 일은 모델·입력·보유기간을 정한 별도 변경이다.

레이블은 `reviewing/interview/offered=1`, `rejected=0`으로 만든
`pipeline_progression_proxy`다. `applied`는 결과가 정해지지 않은 행으로 제외한다. 이 값은 지원자 품질,
합격 가능성 또는 채용 성공을 뜻하지 않는다. 과거 지원 상태에는 채용담당자의 기존 행동이 반영될 수
있으므로 지표 해석과 운영 반영은 사람이 결정한다.

현재 `privacy_core`의 `ai_recommendation` 목적은 모델 학습 동의로 취급하지 않는다. DB 경로는
`JCAREER_SYNTHETIC_ONLY` attestation, 예약 이메일·합성 전화 형식, 합성 랩 표식을 검사한다. 다만 이 검사는
기업 원문의 출처까지 증명하지 않으며 운영 자료 차단을 보장하는 인증 장치도 아니다.
실제 이용자 데이터로 전환하려면 별도의 학습 목적 안내·동의·철회 전파·보존 및 재학습 절차가 먼저
필요하며, 그 충분성은 사람이 검토한다.

## 서버리스 실행 형태

SageMaker를 사용하지 않는다.

```text
합성 회원·기업 DB 옆 exporter
  → S3 mlops/sources/{run_id}/ 특징 CSV 1개와 검증용 JSON 2개
  → 확인 문자열을 넣은 수동 Lambda 호출·로지스틱 학습·합성 오프라인 비교
  → S3 versioned artifacts
  → DynamoDB RUNNING / TRAINED_PENDING_HUMAN_REVIEW / FAILED_SAFE 상태
```

`lambda_handler.py`와 `Dockerfile.lambda`가 이 실행 형태를 제공한다. Lambda는 다음 산출물 6개를 S3에
기록하도록 작성되어 있다.

- `ranking_dataset.csv`
- `dataset_manifest.json`
- `source_read_receipt.json`
- `challenger_model.json`
- `evaluation_observations.json`
- `pipeline_run_receipt.json`

현재 별도 Terraform 시연 루트는 DB URL·DB 비밀번호·VPC 연결·EventBridge schedule 없이
`feature_snapshot` 모드만 배치한다. 직접 DB 경로는 공통 코드 재현용으로 남지만 해당 Terraform
기본 경로가 아니다. 이 Terraform 배치는 KMS를 연결하지 않고 S3 `AES256`(SSE-S3)만 사용한다. DynamoDB 상태는 사람
검토 대기까지만 진행한다. 운영 매처가 S3 모델을 읽거나 자동 승격하는 코드는 없다.

## AS-IS LLM Gateway와의 경계

현재 AS-IS LLM Gateway는 비식별 기능을 구현하지 않았다. 8개 후보자 필드를 받고 6개 PII 필드명을
분류할 뿐, 원문을 raw prompt 로그와 선택적 Bedrock 요청에 포함한다. 이 동작은 위험 시나리오 관찰을
위해 유지한다.

입력 최소화, 한국어 PII 마스킹·차단, 잔여정보 재검사, 원문 로그 차단은 TO-BE 요구사항이다. 따라서
DB 기반 MLOps의 feature-only artifact와 AS-IS Gateway의 비식별 미구현 상태를 혼동하면 안 된다.

## 로컬 계약 검증

실제 AWS 호출 없이 합성 SQLite와 가짜 S3/DynamoDB client로 전체 경로를 검증한다.

```powershell
python -m unittest src/mlops/tests/test_synthetic_pipeline.py
```

테스트는 원문 canary가 dataset·model·S3 payload에 남지 않는지, 두 DB가 분리되는지, attestation 없이
실행이 막히는지, RUNNING 뒤 실패가 `FAILED_SAFE`로 기록되는지, 모델이 자동 활성화되지 않는지를 확인한다.

활성화 값·합성 attestation·event 형식·run ID·source mode·필수 환경 설정 검증과 최초 DynamoDB
`RUNNING` 조건부 쓰기는 try/fail-state 경계보다 앞선다. 따라서 이 pre-state 단계의 거부, 중복 run ID,
또는 최초 상태 저장 실패는 `FAILED_SAFE`를 남기기 전에 종료될 수 있다. `RUNNING`이 기록된 뒤의 snapshot
검증·학습·artifact 저장 실패만 `FAILED_SAFE` 전이를 시도한다.

## S3 특징 스냅샷 학습 경로

Lambda는 기존 `runtime_db` 직접 조회 경로와 별도로 `feature_snapshot` 입력을 지원한다.
이 모드에서는 환경 변수로 고정한 버킷과 `mlops/sources/{run_id}/` 아래의 다음 세 파일만 읽는다.

- `ranking_dataset.csv`
- `dataset_manifest.json`
- `source_read_receipt.json`

호출자는 다른 prefix를 지정할 수 없다. Lambda는 run ID가 허용된 문자로만 구성됐는지 확인하고, 필수 3개 파일의 존재 여부와 크기, 해시, 허용 필드를 검사한다. 같은 prefix 아래에 다른 객체가 더 있는지는 확인하지 않으며 이를 거부하는 기능도 없다. dataset SHA-256 값과 source digest가 맞는지, 합성 데이터와 비식별 특징 규칙을 지켰는지도 검사한다. manifest나 receipt에 허용되지 않은 필드가 추가되면 거부한다. 검증과 학습이 끝나면 원본 특징 스냅샷 3개, challenger 결과 2개, 실행 receipt 1개를 `mlops/runs/{run_id}/`에 저장한다.

최초 DynamoDB 상태 쓰기는 `attribute_not_exists(run_id)` 조건을 사용하므로 같은 run ID를 다시 실행해 기존 결과를 덮어쓰지 않는다. 최종 상태는 `TRAINED_PENDING_HUMAN_REVIEW`이며 모델 자동 활성화와 현재 추천 순위 연결은 계속 금지된다. `MLOPS_SOURCE_MODE=feature_snapshot`을 Terraform 고정값으로 사용하고, 기존 직접 DB 경로는 코드에서 명시적 `runtime_db`로 유지된다. 오늘 시연 루트는 직접 DB 경로를 배치하지 않는다.
