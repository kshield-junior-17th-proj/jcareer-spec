# J-Career 현재 배포 기준과 컨설팅 경계

편집 가능한 원본은 [`JCAREER_PRODUCTION_ASSESSMENT_MAP.drawio`](./JCAREER_PRODUCTION_ASSESSMENT_MAP.drawio), 웹용 도면은 [`JCAREER_PRODUCTION_ASSESSMENT_MAP.svg`](./JCAREER_PRODUCTION_ASSESSMENT_MAP.svg)입니다.

## 2026-09-01 확인 상태

- GitHub Actions에서 저장한 Terraform plan을 작성자와 다른 사람이 승인했고, GitHub OIDC 단기 역할로 같은 plan을 적용했습니다.
- production-serverless 핵심 경로 적용과 live smoke가 성공했습니다. smoke는 임시 Cognito 사용자, 합성 직무 1,000건, AI 매칭, OWASP LLM 10개 시나리오를 확인한 뒤 임시 사용자를 정리했습니다.
- 긴급 실행 경로는 제거됐고 production pipeline은 다시 잠겼습니다. 이 결과는 아래 서버리스 핵심 범위의 증거이며 기업 전체 production 완료를 뜻하지 않습니다.
- 공개 검증 기록은 [GitHub Actions 실행 결과](https://github.com/kshield-junior-17th-proj/jcareer-aws-lab/actions/runs/33466745822)에서 확인할 수 있습니다.

## 현재 배포된 요청 흐름

1. 지원자 또는 채용 담당자가 CloudFront 기본 HTTPS 도메인으로 접속합니다. 정적 화면은 private S3 origin에서 제공합니다.
2. API Gateway HTTP API가 Cognito JWT와 요청 속도를 확인합니다.
3. API Lambda가 tenant 범위를 확인하고 matching run을 DynamoDB에 기록한 뒤 SQS 요청을 만들고 `202 Accepted`를 반환합니다.
4. Agent Lambda가 고정된 결정식으로 점수와 근거를 계산합니다.
5. LLM Gateway Lambda가 설명에 필요한 최소 필드만 구성합니다.
6. Capability Broker Lambda만 정확히 허용된 Bedrock model ARN을 호출합니다.
7. 결과와 correlation ID는 DynamoDB·증적 S3에 저장되고 화면의 polling 요청으로 반환됩니다.

지원 리소스는 Cognito 3개 역할 그룹, Seed Lambda, Matching DLQ와 경보, CloudWatch Logs 7일 보존, S3·KMS·native lockfile 원격 Terraform state입니다. retained bootstrap은 예산, 고정 HTTP API, CloudFront/OAC, OIDC 역할·permissions boundary와 backend 통제를 소유합니다.

## 컨설팅 증적면

Evidence Desk는 다음 컨설팅 단계의 설계·source contract이며 아직 AWS에 배포하지 않았습니다.

1. 현재 서비스 증적 S3에서 비식별 snapshot을 만들고 exporter가 KMS로 서명합니다.
2. 사람이 tenant·목적·만료를 승인한 snapshot만 별도 경계로 반입합니다.
3. 별도 Cognito, API, S3/DynamoDB, WORM 감사 기록으로 역할·tenant·회수 상태를 확인합니다.
4. 컨설턴트 브라우저는 서비스 DB나 고객 AWS/API를 직접 조회하지 않습니다.

## 현재 배포와 분리할 경계

- Slack·Notion·SMTP는 기본 비활성 어댑터 source만 있습니다. workspace·자격 증명·실전송과 production-serverless 연결은 확인되지 않았습니다.
- Windows 100대와 macOS 80대는 사용자 확인 자산 모델입니다. endpoint 검토 source는 있지만 실제 단말·이미지 배포를 관찰한 증거는 없습니다.
- MLOps는 S3·ECR·IAM·DynamoDB·CloudWatch Logs 기반 13개만 적용했습니다. ECR 이미지, Trainer Lambda 실행, 결과 6종, 사람 검토와 추천 서비스 연결은 없습니다.
- OpenDART는 opt-in source-only 보조 경로이며 추천 점수에 영향을 주지 않습니다. AWS 배포·API key·live 조회는 확인되지 않았습니다.
- ECS·RDS·Redis·NAT의 2-AZ 110개 기준선은 기업 규모 목표 설계이며 현재 production-serverless 배포가 아닙니다.
- 별도 검증 Lab은 production과 분리합니다. private EC2는 정지 상태지만 NAT·공인 IPv4·볼륨·edge 등 잔존 비용 가능 경로는 별도 확인 대상입니다.
- CloudFront viewer 최소 프로토콜은 현재 TLSv1이며 origin TLS는 1.2입니다. viewer TLS 1.2 강제 완료로 표기하지 않습니다.

## 공개 AS-IS에 반드시 포함할 것

- GitHub saved plan → 다른 사람 승인 → OIDC → 동일 plan apply → live smoke → pipeline 재잠금
- 현재 서버리스 요청 경로와 retained bootstrap·관측·state 지원 리소스
- Slack·업무망·Windows/macOS와 AWS 사이의 미연결 상태
- Evidence Desk 제안, MLOps bootstrap 13/runtime 미실행, OpenDART source-only, 검증 Lab, 기업 2-AZ 목표의 분리
- `구현됨`, `제안`, `미확정`을 색과 문구로 동시에 구분하고 전체 기업 production 완료가 아님을 명시

## 공개 AS-IS에 추가하면 안 되는 것

- TRACE·JC-RECEIPT를 실행 컴포넌트나 AWS 서비스로 표시하지 않습니다.
- Slack workspace·webhook, Notion 계정, SMTP 그룹웨어나 production 연결을 구현된 것으로 표시하지 않습니다.
- Evidence Desk, OpenDART, MLOps runtime, ECS·RDS·Redis·NAT 2-AZ를 현재 배포된 production-serverless에 합치지 않습니다.
- SageMaker, 자동 모델 승격, 추천 자동 반영, 고객 AWS 직접 조회를 구현된 경로로 추가하지 않습니다.
- 계정 ID, ARN, endpoint, 자격 증명과 Terraform state 내용은 공개하지 않습니다.
