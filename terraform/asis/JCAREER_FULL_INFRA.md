# J-Career 전체 인프라 지도

편집 원본은 [`JCAREER_FULL_INFRA.drawio`](./JCAREER_FULL_INFRA.drawio), 웹용 애니메이션 도면은 [`../../assets/JCAREER_FULL_INFRA_ANIMATED.svg`](../../assets/JCAREER_FULL_INFRA_ANIMATED.svg)입니다.

## 읽는 순서

1. GitHub 저장소의 push 또는 PR이 GitHub Actions 검사를 통과하면 공개 명세만 GitHub Pages로 배포됩니다.
2. 서비스 사용자의 요청은 Route 53 → CloudFront → WAF → public subnet의 ALB → app subnet의 ECS Fargate → data subnet의 RDS 기준으로 모델링되어 있습니다.
3. 업무망 PC 180대, VPN·MFA·UTM 시나리오와 Slack·Notion·SMTP는 AWS 밖의 별도 경계에서 확인 수준을 나눠 표시합니다.
4. 런타임 ECR, NAT Gateway, VPC Endpoints, IAM·Systems Manager, GuardDuty, VPC Flow Logs, CloudWatch, S3, CloudTrail의 의존 관계를 함께 표시합니다.
5. 별도 serverless MLOps는 합성 특징 스냅샷 → S3 입력 → 수동 Lambda 학습 → S3 결과·DynamoDB 상태 → 사람 검토 대기 순서이며 자동 승격이나 서비스 연결이 없습니다.
6. 사람 검토 결과가 향후 추천 서비스에 영향을 줄 수 있는 관계는 보이되, 현재 연결되지 않았다는 점을 점선과 `미구현` 라벨로 고정합니다.

## 연결선 의미

- 화살표와 움직이는 점은 해당 영역 안의 순서를 나타냅니다. GitHub 저장소 → Actions → Pages만 현재 동작이 확인된 전달 흐름이고, AWS와 MLOps의 움직이는 점은 계획 내부 순서입니다.
- 촘촘한 점선은 `IaC → 배포 대상`, `합성 대역 → MLOps 입력`, `사람 검토 → 향후 서비스 반영`, 관리·로그 같은 관계입니다. 자동 배포나 운영 데이터 연결을 뜻하지 않습니다.
- Slack·Notion·SMTP 점선은 바로가기와 기본 비활성 어댑터 소스의 관계만 뜻합니다. 실제 workspace, 자격 증명, 보존 정책과 외부 전송은 확인되지 않았습니다.

## 상태 경계

- GitHub Actions 검사와 GitHub Pages 배포는 저장소 워크플로에 구현되어 있습니다.
- AWS 런타임은 Terraform 기준 계획 110개인 미배포 설계이며 실제 AWS 실행 상태를 뜻하지 않습니다.
- serverless MLOps는 기본 잠금 0개, bootstrap 13개, runtime 14개 계획으로 분리되어 있고 실제 배포·실행은 확인되지 않았습니다.
- CI에서 AWS 또는 MLOps로 이어지는 자동 배포선은 없습니다. 도면의 CI/AWS 점선은 코드·IaC의 배포 대상 관계만 보여 줍니다.
- MLOps 입력은 별도 랩의 합성 DB exporter를 전제로 하며 기준 RDS와 직접 연결하지 않습니다. 검토 결과의 추천 런타임 반영도 구현되지 않았습니다.

## 포함하지 않은 것

전체 인프라 지도는 Slack·Notion·SMTP를 AWS 밖의 업무도구 경계로 표시하되 AWS 또는 MLOps의 구현된 실행 경로처럼 표시하지 않습니다. TRACE·JC-RECEIPT는 실행 컴포넌트에서 제외하고, 9개 상태를 제공하는 웹 화면의 별도 보조 설명으로만 남깁니다. 실제 자격 증명·외부 호출·AWS 배포·새 Terraform 리소스는 없고 Slack workspace 사용 여부는 `SCENARIO_USE_UNVERIFIED`입니다.
