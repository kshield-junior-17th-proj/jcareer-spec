# J-Career 운영 인프라 전환 기록

이 문서는 `ap-northeast-2` 운영 경로를 2026-09-01 12:56:38 KST에 읽기 전용으로 다시 확인한 시점 기록이다. 공개본에서는 AWS 계정 식별자를 제외했다. 기준 설계와 실제 운영 전환을 섞지 않기 위해 기존 전체 인프라 지도는 그대로 두고, 적용 결과를 이 문서와 [운영 전환 페이지](production-transition.html)에 별도 기록한다.

## 결론

[GitHub 운영 배포 run 33466745822](https://github.com/kshield-junior-17th-proj/jcareer-aws-lab/actions/runs/33466745822)는 `SUCCESS`로 종료됐다. 이 실행에서 저장한 plan, GitHub OIDC 배포, 강제 도구 호출 계약과 최종 fail-closed gate가 통과했다.

- 서버리스 요청 경로: `CloudFront → HTTP API → API Lambda → SQS → Agent Lambda → LLM Gateway Lambda → Capability Broker Lambda → Amazon Bedrock`
- 매칭 결과: 합성 공고 1,000건 평가, 200건 반환, `provider=bedrock`, `state=COMPLETED`
- OWASP LLM 검증: 10/10 `SUCCEEDED`, 10/10 `LIVE_OBSERVED`, 전체 `COMPLETE`
- 정리 상태: main queue 0, DLQ 0, DynamoDB `RETRY_PENDING` 0
- 배포 통제: 운영 파이프라인 재잠금, break-glass 변수 제거, 정상 2인 승인 경계 복원

## 공개 확인 경로

| 경로 | 2026-09-01 확인 결과 | 범위 |
|---|---:|---|
| [운영 웹](https://d3n5j95qeqsluw.cloudfront.net/) | HTTP `200` | 정적 UI 응답 |
| [운영 edge health](https://d3n5j95qeqsluw.cloudfront.net/api/v1/health) | HTTP `200` | CloudFront 경유 API 상태 |
| [직접 HTTP API health](https://pyvaij2cpk.execute-api.ap-northeast-2.amazonaws.com/api/v1/health) | HTTP `200` | API Gateway 기본 stage 상태 |

공개 health 응답은 가용성 확인용이다. 보호된 매칭·역할·OWASP 결과의 근거는 위 GitHub run과 보존된 실행 증거다.

## 아직 완료로 말하지 않는 범위

- CloudFront 기본 viewer TLS 최소 버전은 `TLSv1`이며 상향 조치가 남아 있다.
- J-Career RDS와 Redis/ElastiCache는 관찰되지 않았다. 현재 운영 데이터 경로는 DynamoDB와 S3다.
- Windows, macOS, Image Builder, SSM managed node, MDM·원격접속·정리 영수증은 모두 미배포·미관찰이다.
- OpenDART와 serverless MLOps는 각각 별도 승인·배포 수명주기이며 자동 추천 경로에 연결되지 않았다.
- 마지막 재처리 항목은 `COMPLETED`로 끝났지만 과거 실패의 `error_category=GATEWAY_RESPONSE_INVALID` 필드가 남아 있어 데이터 정규화가 필요하다.
- 기존 preview는 중지된 EC2 origin을 향해 `403`을 반환했으므로 운영 fallback으로 보지 않는다.

## 산출물

- [단일 페이지 SVG](JCAREER_PRODUCTION_TRANSITION.svg)
- [편집 가능한 3페이지 draw.io 원본](JCAREER_PRODUCTION_TRANSITION.drawio)
- [서버리스 운영 전환 PNG](JCAREER_PRODUCTION_TRANSITION_SERVERLESS.png)
- [엔드포인트·MDM 미배포 경계 PNG](JCAREER_PRODUCTION_TRANSITION_ENDPOINT_MDM.png)

SVG와 draw.io 공개본의 계정 식별자는 비식별화했다. PNG는 현재 서버리스 전환과 아직 배포하지 않은 엔드포인트 경계만 제공한다.
