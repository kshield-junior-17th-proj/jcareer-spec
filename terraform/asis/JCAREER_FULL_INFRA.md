# J-Career 전체 인프라 지도

편집 원본은 [`JCAREER_FULL_INFRA.drawio`](./JCAREER_FULL_INFRA.drawio), 웹용 애니메이션 도면은 [`../../assets/JCAREER_FULL_INFRA_ANIMATED.svg`](../../assets/JCAREER_FULL_INFRA_ANIMATED.svg)입니다.

## 읽는 순서

1. GitHub 저장소의 push 또는 PR이 GitHub Actions 검사를 통과하면 공개 명세만 GitHub Pages로 배포됩니다.
2. 업무망 PC 180대에서 시작하는 서비스 요청은 Route 53 → CloudFront → WAF → ALB → ECS Fargate → RDS 기준으로 모델링되어 있습니다.
3. 로그와 보안 기록은 GuardDuty, VPC Flow Logs, CloudWatch, S3, CloudTrail 기준 구성을 보여 줍니다.
4. 별도 serverless MLOps는 합성 특징 스냅샷 → S3 입력 → 수동 Lambda 학습 → S3 결과·DynamoDB 상태 → 사람 검토 대기 순서이며 자동 승격이나 서비스 연결이 없습니다.

## 상태 경계

- GitHub Actions 검사와 GitHub Pages 배포는 저장소 워크플로에 구현되어 있습니다.
- AWS 런타임은 Terraform 기준 계획 110개인 미배포 설계이며 실제 AWS 실행 상태를 뜻하지 않습니다.
- serverless MLOps는 기본 잠금 0개, bootstrap 13개, runtime 14개 계획으로 분리되어 있고 실제 배포·실행은 확인되지 않았습니다.
- CI에서 AWS 또는 MLOps로 이어지는 자동 배포선은 없습니다. 도면에서도 CI/AWS 경계에서 선을 끝냅니다.

## 포함하지 않은 것

TRACE와 JC-RECEIPT는 이 AS-IS 인프라 및 MLOps 구현 범위에 포함하지 않습니다. Slack 또는 별도 업무시스템 연동도 구현 근거가 없어 흐름선으로 추가하지 않았습니다.
