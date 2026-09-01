# J-Career AI 서비스 실행면

편집 가능한 원본은 [`JCAREER_PRODUCTION_ASSESSMENT_MAP.drawio`](./JCAREER_PRODUCTION_ASSESSMENT_MAP.drawio), Pages용 도식은 [`JCAREER_PRODUCTION_ASSESSMENT_MAP.svg`](./JCAREER_PRODUCTION_ASSESSMENT_MAP.svg)입니다.

## 상태 기준

- 구현 근거는 `jcareer-aws-lab` main `96d70d7346774e9502fc4b509e1ed5b9e99eaa5d`의 `terraform/production-serverless`, `src/serverless_runtime`, `terraform/serverless-mlops`입니다.
- 사용자가 2026-09-01 apply 실행을 보고했지만 이 작업에서는 GitHub Actions나 AWS 완료 결과를 조회하지 않았습니다. 따라서 현재 실행은 `dispatch reported · completion/live smoke unverified`로 표시합니다.
- production-serverless 구성요소는 구현 및 승인형 apply 대상입니다. 완료 receipt를 확인하기 전에는 `DEPLOYED`, `PASS`, `pipeline re-locked`로 표기하지 않습니다.
- serverless MLOps는 별도 Terraform root의 source contract입니다. production workflow에 연결되지 않았고 AWS 배포·일회성 실행·사람 검토 receipt를 이 소스만으로 주장하지 않습니다.

## production-serverless AI 요청 흐름

1. 지원자·채용 담당자 브라우저가 CloudFront 기본 HTTPS 도메인으로 접속하고, CloudFront는 private S3 web origin에서 화면을 제공합니다.
2. 브라우저는 Cognito와 별도 sign-in/JWT 인증을 주고받습니다. Cognito는 API 요청을 중계하지 않습니다.
3. 브라우저는 JWT를 담은 `/api/*` 요청을 CloudFront로 보내고, CloudFront는 이를 HTTP API origin으로 전달합니다. HTTP API가 JWT와 throttle을 확인합니다.
4. API Lambda가 matching run을 DynamoDB에 기록하고 SQS에 요청한 뒤 `202`를 반환합니다.
5. Agent Lambda가 결정론적 점수와 근거를 계산합니다.
6. Gateway Lambda가 설명 입력을 최소화하고 Broker Lambda가 exact Bedrock ARN allowlist를 검사합니다.
7. Broker만 Bedrock을 호출합니다. 결과 증적은 private S3에, run 상태는 DynamoDB에 보관합니다.

지원면에는 jobs와 candidates를 `entity_type`으로 구분하는 단일 catalog, 별도 8개 qualitative examples, matching runs TTL, 결과 증적 S3, SQS DLQ, CloudWatch 로그·경보를 표시합니다.

## 분리형 serverless MLOps

1. exporter가 합성 DB 옆에서 숫자 특징만 만들고 S3 `mlops/sources/`에 CSV 1개와 검증 JSON 2개를 둡니다.
2. `runtime` 단계에서만 digest-pinned ECR 이미지의 one-shot Trainer Lambda를 만들 수 있습니다.
3. Trainer는 S3 `mlops/runs/`에 6개 versioned artifact를 쓰고 DynamoDB 상태를 `TRAINED_PENDING_HUMAN_REVIEW`로 둡니다.
4. 사람 입력은 별도 record-only 단계입니다. 모델 자동 활성화, 추천 순위 교체, release 승인은 없습니다.

단계 계약은 `disabled=0`, `bootstrap=13`, `runtime=14`입니다. EventBridge schedule, SageMaker, API endpoint, NAT, RDS, 자동 승격은 이 root에 없습니다.

## 이 AI 중심 도식에서 제외한 항목

현재 AI 요청·학습 경로에 쓰이지 않는 Evidence Desk, OpenDART, ECS/RDS/Redis/EC2, 업무 단말, 기업 목표 topology는 제거했습니다. 이들은 별도 문서의 설계 또는 다른 수명주기이며 이 도식의 실행 경로에 합치지 않습니다.
