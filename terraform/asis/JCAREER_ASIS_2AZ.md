# J-Career AS-IS · Seoul 2-AZ 아키텍처 가이드

[편집 가능한 draw.io 원본](JCAREER_ASIS_2AZ.drawio)은 Phase 1 mock plan의 기존
채용 매칭 서비스를 기술 리뷰용으로 시각화한다. 실제 AWS 리소스를 나타내는 운영
다이어그램이 아니며 `terraform apply`는 금지되어 있다.

## 요청 흐름

1. 지원자와 채용 담당자가 Route 53의 공개 도메인으로 접속한다.
2. CloudFront와 AWS WAF 관리형 규칙을 거쳐 서울 리전의 Public ALB로 전달된다.
3. ALB가 경로에 따라 `web`, `api`, `agent`, `llm-gateway` ECS Fargate 서비스로
   요청을 분배한다.
4. 서비스는 Data 서브넷의 RDS PostgreSQL과 ElastiCache Redis를 사용한다.
5. 이력서 원본, ALB 액세스 로그, CloudTrail 로그는 용도별 S3 버킷에 저장된다.
6. CloudWatch Logs, VPC Flow Logs, CloudTrail, GuardDuty가 현재 관측·탐지 평면을
   구성한다. 표시된 구성 부족은 AS-IS 진단의 입력이다.

## 2-AZ 배치

| 계층 | ap-northeast-2a | ap-northeast-2c |
|---|---|---|
| Public | Public subnet, NAT-A | Public subnet, NAT-C |
| Application | App subnet, Fargate task 배치 대상 | App subnet, Fargate task 배치 대상 |
| Data | Data subnet, DB/Cache subnet group | Data subnet, DB/Cache subnet group |

Fargate 서비스마다 `desired_count = 2`를 사용한다. 별도의 task placement strategy를
강제하지 않고 Fargate 서비스 스케줄러의 가용 영역 균형 동작에 맡긴다.

## 서비스 역할

| 구성 | 역할 |
|---|---|
| Route 53 · CloudFront · WAF | 공개 DNS, CDN/TLS 엣지, 관리형 웹 방화벽 규칙 |
| Public ALB | HTTPS 종단과 4개 서비스 경로 라우팅 |
| ECS Fargate · ECR | 기존 매칭 애플리케이션 실행과 이미지 저장 |
| RDS PostgreSQL | Primary와 Replica로 구성한 관계형 데이터 계층 |
| ElastiCache Redis | 추천 결과 캐시 |
| S3 | 이력서 원본, ALB 액세스 로그, CloudTrail 로그 분리 저장 |
| VPC Endpoint | SSM, EC2 Messages, SSM Messages 사설 제어 경로 |
| CloudWatch · CloudTrail · GuardDuty | 로그, 관리 이벤트, 위협 탐지 |

## 설계 경계

- 권위 근거: `context/raw/인프라컨텍스트-외부협업용.md#2.2`,
  `context/raw/D02-진단대상-아키텍처-정의.md#3.1`
- PNG 단일-AZ 축약본이나 아직 존재하지 않는 2-AZ 그림을 근거로 사용하지 않았다.
- AWS Config, 고객 관리형 KMS 키, Secrets Manager 등 원문상 없는 통제를 임의로
  채우지 않았다.
- J-Career TRACE, JC-RECEIPT, Decision Receipt, Recourse Twin은 제안 단계다. 이
  다이어그램과 Terraform에는 구현하지 않았다.
- Terraform plan 결과는 `110 add / 0 change / 0 destroy`이며 apply하지 않았다.

스캐너 결과와 사람이 판단할 명세 상충은
`context/findings/PHASE1_ASIS_EVIDENCE.md`에서 확인한다.
