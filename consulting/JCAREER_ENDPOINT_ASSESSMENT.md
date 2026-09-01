# J-Career 이기종 업무 단말 보안 진단 도면

기준일: 2026-09-01
대상: 가상 기업 J사의 Windows 100대, macOS 80대 시나리오
편집 원본: [JCAREER_ENDPOINT_ASSESSMENT.drawio](JCAREER_ENDPOINT_ASSESSMENT.drawio)

## 도면의 목적

이 도면은 승인된 이미지 또는 MDM 정책과 실제 배포 단말의 상태를 분리해서 보여 준다. 색이 채워진 녹색 노드는 저장소에 구현된 소스이고, 점선 노드는 아직 만들거나 실행하지 않은 단계다. 주황색 노드는 담당자의 승인과 선택이 먼저 필요한 경계다.

현재 상태를 한 문장으로 요약하면 다음과 같다.

> Windows와 macOS의 검토 소스는 있지만, AMI·MDM·샘플 단말·원격 세션·GUI 관찰 결과는 아직 없다.

## 컴포넌트와 AWS 서비스

| 구역 | 컴포넌트 | AWS 서비스 | 현재 상태 |
|---|---|---|---|
| 공통 소스 | endpoint image contract, 승인 입력, 소스 SHA | 없음 | 구현 |
| Windows 이미지 | 이미지 recipe, build/test component | EC2 Image Builder | 정의 구현, 빌드 미실행 |
| Windows 샘플 | WIN-01, WIN-02, WIN-03 | EC2 | 미배포 |
| Windows 접속 | 외부 인바운드 없는 loopback RDP | Systems Manager | 미실행·미관찰 |
| 보조 통제 | 최소 권한, 실행 로그 목적지 | IAM, CloudWatch | 정의에 포함, 운영 효과 미관찰 |
| macOS 기준선 | prepare, configure, validate, remove scripts | 없음 | source-only 구현 |
| macOS 우선 경로 | 물리 Mac 3대와 승인된 MDM | 고객사 단말·MDM | 결정 전·미배포 |
| macOS 예외 | EC2 Mac Dedicated Host | EC2 Mac | 별도 사람 승인 전 제외 |
| 업무 SaaS | Slack shortcut와 종료 보조 소스 | AWS 밖의 Slack | workspace·정책·연동 미확인 |
| 컨설팅 | 비식별 관찰값, finding, 담당자, 잔여위험 | J-Career AIMS Desk 개념 경계 | 실제 단말 관찰 전 |

## Windows 흐름

1. 버전이 고정된 상위 이미지와 구성 번들의 SHA를 승인 입력에 묶는다.
2. EC2 Image Builder가 이미지 빌드와 시험을 수행한다.
3. 승인된 AMI와 소스 SHA가 일치할 때만 WIN-01부터 WIN-03까지 정확히 세 대를 만든다.
4. 보안 그룹의 인바운드 규칙을 0개로 유지하고 Systems Manager 터널을 통해 loopback RDP로 접근한다.
5. Firewall, Defender, Edge 서명, 원본 동일성, 세션 만료와 종료 정리를 관찰한다.
6. 비식별 관찰값만 컨설턴트 검토 경계로 보낸다.

현재는 1단계의 소스와 계약까지만 구현됐다. Image Builder 정의를 활성화하는 일, 빌드를 시작하는 일, AMI를 승인하는 일, 세 대를 배포하는 일은 서로 다른 승인 단계다.

## macOS 흐름

1. 담당자가 물리 Mac + MDM 또는 EC2 Mac 예외 중 하나를 승인한다.
2. 우선 경로에서는 승인된 MDM으로 MAC-01부터 MAC-03까지 정책을 배포한다.
3. FileVault, Gatekeeper, 방화벽, EDR, 브라우저와 Slack 세션 정리를 역할별로 확인한다.
4. EC2 Mac은 Dedicated Host 비용, 최소 할당 시간, Apple 정책, 리전 용량, 원격 접속을 모두 승인한 경우에만 예외로 검토한다.
5. 비식별 관찰값을 컨설턴트 검토 경계로 보낸다.

현재 macOS 파일은 서명된 설치 패키지나 MDM 프로필이 아니다. 배포된 이미지 또는 단말 관찰로 표현하면 안 된다.

## 근거 위치

| 확인 사실 | 파일·행 근거 |
|---|---|
| Windows 100대, macOS 80대는 문서상의 시나리오 inventory | `fleet/README.md:6` |
| 전체 실행 상태는 NOT_BUILT_OR_DEPLOYED | `fleet/images/endpoint_image_contract.yaml:4` |
| Windows는 EC2 Image Builder AMI 전략 | `fleet/images/endpoint_image_contract.yaml:15` |
| Windows OS는 Server 2022 desktop simulation | `fleet/images/endpoint_image_contract.yaml:16` |
| Image Builder root는 정의만 제공하고 빌드와 단말을 시작하지 않음 | `terraform/workplace-images/README.md:5` |
| Windows 통제에 IMDSv2, Firewall, Defender, SSM, signed Edge 포함 | `terraform/workplace-images/README.md:8-11` |
| macOS는 source-only이며 서명 패키지·MDM profile·관찰 결과가 아님 | `terraform/workplace-images/README.md:121-125` |
| macOS는 물리 Mac + MDM 우선, EC2 Mac은 승인 예외 | `terraform/workplace-images/README.md:125-126` |
| Windows 세션은 정확히 3개이며 SSM tunneled RDP 사용 | `terraform/workplace-endpoints/README.md:22-26` |
| macOS는 physical Mac/MDM 또는 승인된 EC2 Mac 예외 | `terraform/workplace-endpoints/README.md:96-98` |
| 6개 프로필 모두 NOT_DEPLOYED·NOT_EXECUTED | `../jcareer-aws-lab-review/consulting/access-matrix.json:255-262` |

## 공개 AS-IS에 추가할 내용

- 자산 수량은 시나리오 규모이며 실물 관찰 수가 아니라는 설명
- Windows Server 2022 Desktop Experience 시뮬레이션이라는 정확한 표기
- 이미지 소스, 이미지 빌드, 단말 배포, 원격 세션, GUI 관찰의 개별 상태
- macOS 물리 Mac + MDM 우선안과 EC2 Mac 예외 승인 조건
- Slack은 AWS 밖의 운영 미확인 SaaS 경계라는 설명
- 3+3 샘플은 통제 경로 검증용이며 180대 전체를 대표하지 않는다는 한계

## 공개 AS-IS에 추가하지 않을 내용

- 180대를 만들거나 관찰했다는 표현
- Windows 11 또는 macOS 이미지를 배포했다는 표현
- Slack workspace와 AWS가 연결됐다는 표현
- AWS 계정 ID, 자격증명, 내부 주소, 원본 state, 민감 로그
- 실제 지원자 정보, 인증 쿠키, 복구 가능한 개인정보
- TRACE 또는 JC-RECEIPT를 단말 실행 인프라 컴포넌트로 그리는 표현

TRACE와 JC-RECEIPT는 이 도면의 구현 대상이 아니다. 추천 결과 설명을 위한 별도 보조 경계이며, 업무 단말의 이미지·배포·세션 아키텍처에 섞지 않는다.
