# J-Career AI 실행·진단·TO-BE 도면

세 도면은 같은 상태로 합치지 않는다. 현재 계정의 배포 완료 여부는 해당 GitHub Actions apply와 live-smoke 영수증으로만 갱신한다.

| 도면 | 포함 범위 | 상태 경계 |
|---|---|---|
| [현재 AI 서비스 실행면](JCAREER_AI_RUNTIME_ACTUAL.svg) | CloudFront, S3 Web, Cognito, API Gateway, API·Agent·Gateway·Broker Lambda, SQS·DLQ, DynamoDB, Evidence S3, CloudWatch, Bedrock | 최신 소스 `a9764f8`, plan run `33569358467` attempt `1`, plan SHA-256 `c0e596e222fcf440f23e29dd165fe42b3d934656d89b96195c2e0a0e9ca8b2f2` 성공. **APPLY · LIVE SMOKE NOT RUN.** 마지막 관찰 배포는 별도 revision `7a5acfb`, run `33466745822` |
| [진단·증적 흐름](JCAREER_ASSESSMENT_EVIDENCE.svg) | Prowler AWS/LLM, 동적 LLM 시험, MLOps receipt, 수기 점검, 공통 포맷, 비식별화, 사람 승인, Evidence Desk | 부분 소스. 실제 통합 실행·승인 snapshot 미확인 |
| [기업 TO-BE 목표](JCAREER_ENTERPRISE_TOBE_TARGET.svg) | WAF, ALB, ECS Fargate, RDS PostgreSQL, ElastiCache Redis, NAT, 2-AZ, S3, CloudWatch, Bedrock | 승인 전 미배포 목표. 현재 서버리스 실행면의 리소스로 주장하지 않음 |

편집 가능한 원본은 [JCAREER_AI_SECURITY_FLOWS.drawio](JCAREER_AI_SECURITY_FLOWS.drawio)의 세 페이지다. 각 애니메이션 SVG의 입력 명세는 같은 이름의 `.spec.json`이며 PNG는 정지·축소 모션 대체본이다.

진단 결과는 `observation.status`와 `assessment.status`를 분리한다. Prowler의 `FAIL`이나 모델 응답을 자동으로 취약 판정하지 않고, 승인된 비식별 snapshot만 Evidence Desk에 반입한다.
