# J-Career 전체 인프라 지도

편집 원본은 [`JCAREER_FULL_INFRA.drawio`](./JCAREER_FULL_INFRA.drawio), 웹용 애니메이션 도면은 [`../../assets/JCAREER_FULL_INFRA_ANIMATED.svg`](../../assets/JCAREER_FULL_INFRA_ANIMATED.svg)입니다.

## 읽는 순서

1. GitHub Actions는 PR과 `main` push에서 공개 검사를 실행합니다. GitHub Pages는 Actions deploy job이 아니라 legacy `main / (root)` branch source에서 공개 명세를 배포합니다.
2. 서비스 사용자의 기준 요청은 Route 53 → CloudFront → WAF → ALB → ECS Fargate → RDS로 흐릅니다. 이 2-AZ·110개 기준선은 Terraform 모델이며 실제 배포가 아닙니다.
3. ECS는 `web`·`api`·`agent`·`llm-gateway` 네 기술 배포 단위를 모델링합니다. LLM Gateway는 로컬 소스가 구현됐지만 ECR 이미지 게시와 AWS 런타임 실행은 확인되지 않았습니다.
4. 설명 경로는 API → LLM Gateway → 조건부 Bedrock capability broker → Amazon Bedrock 관계로 읽습니다. Bedrock 직접 합성 호출 한 건은 통과했지만 이 전체 경로는 확인되지 않았습니다.
5. OpenDART는 API/broker → SQS FIFO 2개 → Lambda → DynamoDB 결과함 → 외부 OpenDART API의 별도 `0 / 8 / 11` source-only 경계입니다. ECR·IAM·CloudWatch Logs 지원 리소스도 소스에 있지만 전체 경로의 배포·live 호출은 미확인입니다.
6. ACM, target groups·Auto Scaling, IGW·EIP·security groups·route tables, ECR, NAT Gateway, VPC Endpoints, IAM·Systems Manager, GuardDuty, VPC Flow Logs, CloudWatch, S3, CloudTrail과 세 논리 DB 경계를 함께 표시합니다.
7. 별도 serverless MLOps는 bootstrap 13개(S3 버킷·보호 설정 7, ECR 저장소·lifecycle 2, IAM role·policy 2, DynamoDB 1, CloudWatch Logs 1) 적용이 확인됐습니다. 이미지 게시, 14번째 Lambda 배포·실행, 결과 6종 생성, 사람 검토와 추천 서비스 연결은 아직 없습니다.
8. 업무망 PC 180대, VPN·MFA·UTM 시나리오, Slack·Notion·SMTP, Windows 3 + macOS 3 endpoint review source는 AWS 밖에서 확인 수준을 나눠 표시합니다.

## 연결선 의미

- 화살표와 움직이는 점은 해당 영역 안의 구현 또는 기준 처리 순서를 나타냅니다. 움직임 자체는 AWS 배포나 외부 호출의 증거가 아닙니다.
- 촘촘한 점선은 `IaC → 배포 대상`, source-only broker, 합성 MLOps 입력, 사람 검토 후 향후 서비스 반영, 관리·로그 관계입니다. 자동 배포·운영 DB 연결·provider live 성공을 뜻하지 않습니다.
- Slack·Notion·SMTP 점선은 바로가기와 기본 비활성 어댑터 소스의 관계만 뜻합니다. 실제 workspace, 자격 증명, 보존 정책과 외부 전송은 확인되지 않았습니다.

## 상태 경계

| 컴포넌트 | 현재 상태 | 직접 근거 |
|---|---|---|
| GitHub Actions CI | PR·`main` 검사 구현, Pages/AWS deploy job 없음 | [공개 release workflow](../../.github/workflows/public-release-check.yml) |
| GitHub Pages | legacy `main / (root)` branch source 배포 | 저장소 Pages 설정(2026-08-31 확인) |
| AWS 2-AZ 기준 런타임 | Terraform 110개 모델·미배포 | [AS-IS README](./README.md), [runtime Terraform 대조](../../src/runtime/ASIS_RUNTIME_SPEC.md#11-terraform-대조) |
| ECS 4서비스·LLM Gateway | Terraform 서비스 정의 + 로컬 runtime source, 이미지 미게시·AWS 실행 미확인 | [compute README](./compute/README.md), [runtime 배포 단위](../../src/runtime/ASIS_RUNTIME_SPEC.md#2-실행-토폴로지) |
| Bedrock adapter | LLM Gateway 코드 안에 구현, 기본 live=false | [AI matching flow](../../src/runtime/AI_MATCHING_FLOW.md#bedrock-구성-상태) |
| Bedrock 직접 호출 | 합성 문장 1건 PASS(39 input / 53 output tokens), end-to-end 아님 | [공개 검증 기록](./JCAREER_ASIS_SYSTEM_SPEC.md#17-검증-경계) |
| Bedrock capability broker | 별도 Lab source only·미배포 | [runtime Bedrock 경계](../../src/runtime/ASIS_RUNTIME_SPEC.md#9-bedrock-경계) |
| OpenDART serverless | source 0/8/11·기본 disabled·미배포·live 미확인 | [OpenDART README](../serverless-opendart/README.md#stages-and-approvals) |
| MLOps bootstrap | 2026-08-31 기반 13개 적용 확인 | [저장소 현재 상태](../../README.md#현재-확인된-aws-상태) |
| MLOps runtime | ECR 이미지 미게시, Lambda 미배포·미실행, 추천 미연결 | [serverless MLOps README](../serverless-mlops/README.md) |
| 비공개 Terraform state | serverless roots용 S3 1개 생성·보호 설정 확인 | [저장소 현재 상태](../../README.md#현재-확인된-aws-상태) |
| 업무망·Slack·외부 도구 | 180대 수량은 사용자 확인, 실물·운영·workspace·실전송 미확인 | [fleet README](../../fleet/README.md), [runtime 검증](../../src/runtime/VERIFICATION.md) |

CI에서 AWS, Bedrock, OpenDART 또는 MLOps로 이어지는 자동 배포선은 없습니다. MLOps bootstrap 적용은 별도 승인형 운영 기록이며 GitHub Actions가 수행한 것이 아닙니다.

## 공개 AS-IS 명세에 반드시 추가할 항목

- LLM Gateway를 ECS의 “4종” 문구에만 숨기지 말고 독립 노드로 표시합니다.
- Amazon Bedrock, 조건부 capability broker, 직접 호출 PASS와 end-to-end 미확인을 같은 경계 안에서 분리합니다.
- OpenDART의 broker·SQS FIFO 2개·Lambda·DynamoDB 결과함·ECR·IAM·CloudWatch Logs·외부 API 관계와 `0 / 8 / 11` 미배포 상태를 표시합니다.
- RDS 물리 경계와 `member`·`company`·`outcome` 세 논리 DB, 일부 Terraform 미배선을 함께 표시합니다.
- ACM, target groups·Auto Scaling, IGW·EIP·security groups·routes, ECR 이미지 미게시, `prompt_raw` 로그 모델을 표시합니다.
- MLOps를 “전부 미배포”로 쓰지 말고 bootstrap 13개 적용과 runtime/Lambda 미실행을 분리하고, 적용된 S3·ECR·IAM·DynamoDB·CloudWatch Logs 서비스군을 빠짐없이 표시합니다.
- Slack·Notion·SMTP, endpoint/image source, GitHub Pages와 AWS 자동 배포 부재를 계속 표시합니다.

## 공개 AS-IS 명세에 추가하면 안 되는 항목

- TRACE·JC-RECEIPT를 실행 컴포넌트나 AWS 서비스로 추가하지 않습니다.
- SageMaker, Bedrock embeddings, EventBridge schedule, API Gateway, 자동 모델 승격·자동 서비스 반영을 MLOps 경로에 추가하지 않습니다.
- Secrets Manager, EFS 영속 prompt log, Network Firewall, Route 53 Resolver Firewall을 현행 구현처럼 추가하지 않습니다.
- Slack workspace·webhook 실전송, Notion 계정, SMTP 그룹웨어, Amazon Q Developer/AWS Chatbot·SNS 연동을 구현된 경로로 추가하지 않습니다.
- Bedrock 직접 호출을 `API → Gateway → Broker → Bedrock` 전체 경로 성공이나 운영 배포로 확대하지 않습니다.
- OpenDART source 존재를 AWS 배포·API key 준비·외부 live 조회로 확대하지 않습니다.
- Lab EC2·CloudFront preview와 workplace Image Builder/endpoint source를 현재 운영 인프라로 합치지 않습니다.
- dashboard/AIMS Desk를 Lab Terraform·Compose·edge route 또는 고객 AWS 직접 연결로 추가하지 않습니다.

## 포함하지 않은 것

전체 인프라 지도는 상태가 다른 기준 AWS, 직접 Bedrock 관찰, source-only broker/OpenDART, 적용된 MLOps 기반, 미확인 업무도구를 한 장에 연결하되 같은 실행 수준으로 칠하지 않습니다. TRACE·JC-RECEIPT는 실행 컴포넌트에서 제외하고 웹 화면의 보조 설명으로만 남깁니다. 실제 자격 증명·식별자·state 내용은 공개하지 않으며 Slack workspace 사용 여부는 `SCENARIO_USE_UNVERIFIED`입니다.
