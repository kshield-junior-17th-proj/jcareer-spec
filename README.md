# J-Career 서비스·AWS 아키텍처

J-Career는 구직자와 기업을 연결하는 채용 플랫폼입니다. 이 저장소는 공고 추천, 기업용 인재
탐색, 지원 관리와 AI 설명을 뒷받침하는 AWS 기준 설계와 MLOps 모델 검증 체계를 함께 제공합니다.
서비스 구조부터 데이터, 보안·관측, 검증 환경까지 같은 기준으로 살펴볼 수 있습니다.

## 바로 보기

- [서비스 아키텍처](https://kshield-junior-17th-proj.github.io/jcareer-spec/)
- [전체 AWS 인프라 흐름도](https://kshield-junior-17th-proj.github.io/jcareer-spec/terraform/asis/architecture.html)
- [MLOps 7단계 모델 검증](https://kshield-junior-17th-proj.github.io/jcareer-spec/mlops/)
- [AWS 검증 환경](https://kshield-junior-17th-proj.github.io/jcareer-spec/terraform/lab/)

## 구성 한눈에 보기

| 구성 | 역할 | 현재 관리 기준 |
|---|---|---|
| [`terraform/asis`](terraform/asis/README.md) | J-Career 서비스·AWS 기준 설계 | 서울 리전 2-AZ, 6개 모듈, Terraform 계획 항목 110개 |
| [`terraform/serverless-mlops`](terraform/serverless-mlops/README.md) | 합성 데이터 기반 후보 모델 검증 | 기본 잠금 0개, 기반 준비 13개, 한 차례 실행 14개 계획 |
| [`terraform/lab`](terraform/lab/README.md) | 서비스와 데이터 흐름을 확인하는 AWS 검증 환경 | 기본 계획 13개, 외부 인바운드 0개, SSM 관리 접속 |

## 기술 상태와 검증 범위

기준 설계의 110개는 AWS에 접속하지 않는 Terraform 계획에서 계산한 생성 예정 항목입니다.
AWS 배포 결과와 애플리케이션 이미지는 별도 검증 기록으로 관리합니다. MLOps와 AWS 검증 환경은
기준 설계와 분리된 Terraform 루트이며, 명시적인 확인값이 있어야 다음 단계가 열립니다.
TRACE와 JC-RECEIPT 등 제안 단계 신규 서비스는 이 기준 설계에 포함하지 않습니다.

## MLOps 명세 바로 보기

- **브라우저용:** [MLOps 모델 검증 체계](https://kshield-junior-17th-proj.github.io/jcareer-spec/mlops/)
- [PDF 명세](mlops/JCAREER_MLOPS_SYSTEM_SPEC.pdf)
- [한글 PNG 흐름도](terraform/serverless-mlops/JCAREER_MLOPS_FLOW.drawio.png)
- [편집 가능한 draw.io 원본](terraform/serverless-mlops/JCAREER_MLOPS_FLOW.drawio)
- [학습·검증 소스](src/mlops/README.md)
- [서버리스 Terraform](terraform/serverless-mlops/README.md)

MLOps는 기존 110개 기준 설계와 별도입니다. 기본 `disabled` 계획은 관리 리소스 0개입니다.
담당자가 확인 문자열을 넣은 `bootstrap`은 13개, 이미지 해시를 고정한 Lambda까지 포함한
`runtime`은 14개를 계획합니다. 세 단계의 수치는 AWS 비접속 계획 결과이며 배포 결과와 구분합니다.

현재 배치 경로는 합성 DB 옆 내보내기 도구가 만든 비교 수치 CSV 1개와 검증용 JSON 2개를
S3에서 읽습니다. Lambda는 후보 모델을 한 차례 학습한 뒤 결과 파일 6개와 실행 상태를 기록합니다.
자동 일정, 공개 API, SageMaker, 자동 승격과 기존 추천 점수 연결은 현재 범위에서 분리했습니다.
두 가지 문서 비교값은 단어 중복 정도만 나타내며, 합격 가능성이나 인재 수준 판단에는 사용하지 않습니다.

확인 문자열은 의도하지 않은 활성화를 막는 절차 장치일 뿐, 사용자 인증이나 조직의 평가 승인을
증명하지 않습니다. 합성 여부 검사도 기업 원문의 출처까지 증명하지 못합니다.

## AS-IS 명세 바로 보기

- **브라우저용:** [전체 명세](https://kshield-junior-17th-proj.github.io/jcareer-spec/terraform/asis/) · [대화형 아키텍처](https://kshield-junior-17th-proj.github.io/jcareer-spec/terraform/asis/architecture.html)
- [웹 명세](terraform/asis/index.html): 서비스, 기능, API, 데이터·이벤트 흐름, 보안·운영·장애 시나리오
- [대화형 아키텍처](terraform/asis/architecture.html): 전체 구성과 경로별 1·2·3 단계 강조
- [PDF 명세](terraform/asis/JCAREER_ASIS_SYSTEM_SPEC.pdf)
- [PNG 도면](terraform/asis/JCAREER_ASIS_FLOW.drawio.png)
- [편집 가능한 draw.io 원본](terraform/asis/JCAREER_ASIS_FLOW.drawio)

업무망 PC 180대는 Windows 100대와 macOS 80대로 구분합니다. 이 수량은 사용자 확정 입력이며
Terraform 자원 수나 동시 사용자 수로 바꾸어 해석하지 않습니다.

## 보안 서비스는 어디에 있나

| 서비스 | AS-IS 선언 위치 | 설계 모델에서 확인되는 내용 | 배포 검증 상태 |
|---|---|---|---|
| AWS WAF | [`edge/main.tf`](terraform/asis/edge/main.tf) | CloudFront 범위, Common·SQLi 관리형 규칙, 지표·샘플 요청 | 별도 검증 기록 필요 |
| GuardDuty | [`observability/main.tf`](terraform/asis/observability/main.tf) | detector 활성 선언 | 별도 검증 기록 필요 |
| CloudTrail | [`observability/main.tf`](terraform/asis/observability/main.tf) | 관리 이벤트를 S3로 기록하도록 선언 | 별도 검증 기록 필요 |
| VPC Flow Logs | [`observability/main.tf`](terraform/asis/observability/main.tf) | VPC의 ALL 트래픽을 CloudWatch Logs로 전달하도록 선언 | 별도 검증 기록 필요 |
| CloudWatch Logs | [`observability/main.tf`](terraform/asis/observability/main.tf) | access 365일, flow 30일, prompt_raw 보존기간 미설정 | 별도 검증 기록 필요 |

WAF 요청 로그, GuardDuty 알림·자동 대응, CloudTrail 데이터 이벤트·CloudWatch 연동,
CloudWatch 경보·대시보드 등은 이 AS-IS 모델에 선언되어 있지 않습니다. 자세한 설정과 한계는
[`terraform/README.md`](terraform/README.md)에 정리했습니다.

AS-IS 파일은 자격증명 없이 다음처럼 검토합니다. `apply`는 실행하지 마십시오.

```powershell
terraform -chdir=terraform/asis init -backend=false -lockfile=readonly
terraform -chdir=terraform/asis validate
terraform -chdir=terraform/asis plan -refresh=false -lock=false
```

저장된 plan, state, `tfvars`, 계정 정보는 저장소에 올리지 않습니다. 포함된 검증 JSON은 원본
작업 트리에서 만든 기록입니다. 공개 사본의 독립 실행 결과로 오해하면 안 됩니다.
AS-IS 코드의 12자리 숫자는 가상 입력값과 AWS가 공개한 서비스 주체 값뿐이며, 조직 계정
식별자는 포함하지 않습니다.

## 합성 Lab 한 명령 배포

필요 도구는 AWS CLI, Terraform `1.15.9`, Python 3입니다. AWS CLI 로그인 후 저장소 루트에서
다음 명령을 실행합니다.

```powershell
.\terraform\lab\provisioning\deploy-lab.ps1 `
  -ActivationAcknowledgement JCAREER_SYNTHETIC_LAB_APPROVED `
  -Apply
```

이 명령은 다음 작업을 순서대로 수행합니다.

1. 소스·회귀 검사
2. Terraform 초기화·검증
3. saved plan 생성
4. 비용·노출·허용 자원 검사
5. 검사한 saved plan만 적용
6. SSM을 통한 런타임 전송
7. 원격 기능·기업 간 접근 차단·DB 경계 검사

`-Apply`를 빼면 AWS를 변경하지 않고 plan까지만 검사합니다. 삭제나 교체가 포함된 plan은 자동
차단되며 `-target`과 `-auto-approve`는 사용하지 않습니다.

## 생성 범위

- 리전: 서울 `ap-northeast-2`
- EC2: `t3.small` 1대
- 저장장치: 암호화된 `gp3` 20GiB, 인스턴스 삭제 시 함께 제거
- 네트워크: 전용 VPC·서브넷·인터넷 출구, 인바운드 규칙 0개
- 접근: SSH·공개 3000 포트 없이 SSM만 사용
- 런타임: PostgreSQL, Redis, API, 매칭기, 설명 게이트웨이, 웹 등 6개 컨테이너
- 데이터: 예약 도메인과 합성 데이터만 사용
- AI 공급자: 로컬 합성 stub만 사용하며 Bedrock 호출은 차단
- 비용 제어: 240분 자동 중지와 월 USD 20 관찰 예산

예산은 알림이나 하드캡이 아닙니다. 자동 중지도 자원을 삭제하지 않으므로 사용 후 정리가
필요합니다.

## 접속

웹은 EC2 loopback에만 바인딩됩니다. Terraform output으로 대상 인스턴스를 읽은 뒤 SSM 로컬
터널을 엽니다.

```powershell
$instanceId = terraform -chdir=terraform/lab output -raw runtime_instance_id
aws ssm start-session `
  --region ap-northeast-2 `
  --target $instanceId `
  --document-name AWS-StartPortForwardingSession `
  --parameters '{"portNumber":["3000"],"localPortNumber":["3000"]}'
```

터널이 열린 동안 `http://127.0.0.1:3000/jobs`로 접속합니다. 공개 URL은 만들지 않습니다.

## 종료

```powershell
$env:TF_VAR_activation_acknowledgement = 'JCAREER_SYNTHETIC_LAB_APPROVED'
$env:TF_VAR_enable_bedrock_live = 'false'
terraform -chdir=terraform/lab destroy
```

종료 후 `terraform -chdir=terraform/lab state list`가 비어 있는지 확인합니다. state·saved plan·
`.env`는 Git에 올리지 마십시오.

상세 경계와 수동 단계는 [`terraform/lab/README.md`](terraform/lab/README.md)에 있습니다.
