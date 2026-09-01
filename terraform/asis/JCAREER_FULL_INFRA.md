# J-Career 전체 인프라 지도

현재 배포 기준은 [`JCAREER_PRODUCTION_ASSESSMENT_MAP.drawio`](../../assets/JCAREER_PRODUCTION_ASSESSMENT_MAP.drawio)와 [웹용 SVG](../../assets/JCAREER_PRODUCTION_ASSESSMENT_MAP.svg), 기업 2-AZ 목표 편집 원본은 [`JCAREER_FULL_INFRA.drawio`](./JCAREER_FULL_INFRA.drawio)입니다.

## 먼저 구분할 두 도면

1. **현재 production-serverless** — GitHub Actions saved plan → 다른 사람 승인 → OIDC → 동일 plan apply → live smoke → pipeline 재잠금과 실제 서버리스 요청 경로를 표시합니다.
2. **기업 2-AZ 목표** — Route 53 → CloudFront → WAF → ALB → ECS Fargate → RDS, Redis, NAT와 운영 통제를 모델링합니다. 110개 Terraform 기준선이며 현재 배포가 아닙니다.

2026-09-01 production-serverless apply와 live smoke는 성공했습니다. smoke는 임시 Cognito 사용자, 합성 직무 1,000건, 매칭, OWASP LLM 10개 시나리오를 확인하고 임시 사용자를 정리했습니다. 공개 결과는 [GitHub Actions 실행](https://github.com/kshield-junior-17th-proj/jcareer-aws-lab/actions/runs/33466745822)에서 확인할 수 있습니다.

## 현재 배포된 production-serverless

- 사용자 → CloudFront → API Gateway HTTP API → API Lambda → SQS → Agent Lambda → LLM Gateway Lambda → Capability Broker Lambda → Amazon Bedrock
- private S3 Web, Cognito 역할 그룹 3개, DynamoDB 직무·matching run, Evidence S3, Seed Lambda, DLQ·경보, CloudWatch Logs 7일
- S3·KMS·native lockfile 원격 Terraform state와 retained bootstrap의 budget·HTTP API·CloudFront/OAC·OIDC 통제
- 현재 애플리케이션 범위에는 NAT, RDS, ElastiCache, ECS, ALB, WAF, EC2가 없습니다.
- CloudFront viewer 최소 프로토콜은 TLSv1이며 origin TLS는 1.2입니다. viewer TLS 1.2 강제 완료로 표기하지 않습니다.

## 업무망·외부 업무도구

- Windows 100대와 macOS 80대는 사용자 확인 자산 모델이며 실물·접속·이미지 배포를 관찰한 증거가 아닙니다.
- Slack·Notion·SMTP는 기본 비활성 adapter source만 있습니다. workspace·자격 증명·실전송과 production-serverless 연결은 확인되지 않았습니다.
- Windows 3개·macOS 3개 endpoint review source는 실제 배포된 golden image가 아닙니다.

## 분리된 수명주기

| 영역 | 상태 | 현재 실행면과의 관계 |
|---|---|---|
| Evidence Desk | source contract·제안, 미배포 | 승인된 비식별 snapshot만 받는 별도 컨설팅 경계 |
| MLOps | bootstrap 13개 적용, runtime/Lambda 미실행 | 합성 특징만 사용, 추천 자동 연결 없음 |
| OpenDART | source-only·opt-in, live 미확인 | `score_effect=NONE`, 추천 입력 아님 |
| 검증 Lab | production과 별도, private EC2 정지 | NAT·공인 IPv4·볼륨·edge 잔존비용 경로 별도 확인 |
| 기업 2-AZ | Terraform 110개 목표, 미배포 | 현 production-serverless 성공 증거에 합산 금지 |

## 선의 의미

- 굵은 실선은 검증된 GitHub delivery 또는 production-serverless 요청 경로입니다.
- 점선은 source, 제안, 목표, 관리 의존을 뜻하며 자동 배포·운영 데이터 연결의 증거가 아닙니다.
- GitHub Pages publish와 AWS apply는 서로 다른 경로입니다.

## 공개 AS-IS에 반드시 포함할 것

- GitHub OIDC 승인형 apply와 재잠금, 실제 서버리스 서비스·데이터 흐름
- 업무망·Slack과 AWS 사이의 미연결 상태
- LLM Gateway와 Capability Broker를 독립 컴포넌트로 표시하고 Bedrock E2E 성공 범위를 current serverless로 한정
- Evidence Desk 제안, MLOps 13/runtime 미실행, OpenDART source-only, 검증 Lab, 2-AZ 목표를 각각 분리

## 공개 AS-IS에 추가하면 안 되는 것

- TRACE·JC-RECEIPT를 실행 컴포넌트나 AWS 서비스로 추가하지 않습니다.
- Slack workspace·webhook 실전송, Notion·SMTP 운영 연결을 구현된 것으로 표시하지 않습니다.
- SageMaker, 자동 모델 승격·자동 추천 반영, Evidence Desk와 OpenDART live를 현행으로 추가하지 않습니다.
- 계정 ID, ARN, endpoint, 자격 증명과 Terraform state 내용을 공개하지 않습니다.
