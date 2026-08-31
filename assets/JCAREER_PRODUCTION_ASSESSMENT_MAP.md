# J-Career 기업 목표와 실제 핵심 평가 슬라이스

## 주 요청 흐름

1. 지원자 또는 채용담당자가 CloudFront HTTPS 화면에 접속한다.
2. API Gateway가 Cognito JWT와 요청 속도를 확인한다.
3. API Lambda가 tenant 범위를 확인하고 matching run을 DynamoDB에 기록한다.
4. SQS가 요청을 내구성 있게 보관하고 즉시 `202 Accepted`를 반환하게 한다.
5. Agent Lambda가 고정된 결정식으로 점수와 근거를 계산한다.
6. LLM Gateway가 설명에 필요한 최소 필드만 구성한다.
7. Capability Broker만 정확히 허용된 Bedrock model ARN을 호출한다.
8. 결과와 correlation ID를 저장하고 화면의 polling 요청에 반환한다.

## 컨설팅 증적 흐름

1. 서비스 실행면에서 비식별 snapshot을 만든다.
2. exporter만 KMS 서명 권한을 사용한다.
3. 사람이 tenant·목적·만료를 승인한 snapshot만 Evidence Desk 경계로 반입한다.
4. Evidence Desk는 별도 Cognito, API, S3/DynamoDB, WORM 감사 receipt를 사용한다.
5. 컨설턴트 브라우저는 서비스 DB나 고객 AWS/API를 직접 조회하지 않는다.

## 분리된 lifecycle

- OpenDART는 공개 기업정보 보조 경로이며 추천 점수에 자동 연결하지 않는다.
- MLOps는 합성 특징 export에서 시작하고 사람 검토 대기에서 멈춘다.
- Windows 100대와 macOS 80대는 기업 자산 모델이다. 실제 단말 배포 증거가 아니다.
- ECS·RDS·Redis·NAT의 2-AZ 구성은 기업 목표 설계이며 USD 50 핵심 슬라이스의
  현재 배포 상태가 아니다.

## 배포와 비용 결정

- GitHub Pages 배포와 AWS apply는 서로 다른 선이다.
- AWS apply는 main 검사, saved plan digest, 다른 사람의 승인, OIDC, 동일 plan apply,
  smoke receipt 순서로 진행한다.
- 실제 실행체는 유휴 고정비를 피하는 CloudFront/S3, API Gateway, Lambda, SQS,
  DynamoDB on-demand를 사용한다.
- Redis는 선택형 성능 계층이며 없어도 cache miss로 정상 처리한다.
