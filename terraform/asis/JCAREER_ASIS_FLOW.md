# J-Career 기존 구성 한눈에 보기

> 기준일: 2026-08-31
> 도면 성격: J-Career 채용 서비스와 AWS 인프라 기준 설계
> 핵심 수치: 업무망 PC 180대, 2-AZ, 6개 모듈, Terraform 계획 항목 110개

이 문서는 [JCAREER_ASIS_FLOW.drawio](JCAREER_ASIS_FLOW.drawio)의 짧은 해설이다.
[웹 도면](architecture.html)에서는 서비스 사용자·업무망과 Slack·GitHub CI와 Pages·AWS 기준 설계·LLM Gateway·Bedrock·OpenDART·별도 MLOps를
합친 [전체 지도 편집 원본](JCAREER_FULL_INFRA.drawio)과
[애니메이션 SVG](../../assets/JCAREER_FULL_INFRA_ANIMATED.svg)를 먼저 볼 수 있다. 여덟 개
서비스·보조 경로를 누르면 AWS 상세 강조 도면으로 바뀐다. MLOps를 누르면 전체 연결 지도를
유지해 입력과 검토 후 반영 경계를 함께 보여 주고, 별도 링크에서 7단계 전용 도면을 연다.
선택한 설명 아래의 바로가기를 누르면 관련 상세 명세로 이어진다. 자세한 기능과 API,
보안, 장애 내용은 [웹 명세](index.html)에 있다.

## 0. 먼저 볼 숫자

아래 네 항목이 현재 범위를 보여 준다.

- 업무망 PC 180대: Windows 100대, macOS 80대
- Terraform 구성: 가용 영역 2곳, 서브넷 6개, 모듈 6개
- Terraform 기준선: 6개 모듈, 계획 항목 110개
- 별도 MLOps: bootstrap 기반 13개 적용 확인, runtime 14번째 Lambda 미배포·미실행

GitHub Actions는 PR과 `main` push에서 저장소 단위시험과 공개 문서 검사를 수행한다.
GitHub Pages는 Actions deploy job이 아니라 legacy `main / (root)` branch source를 배포한다.
AWS 또는 MLOps를 자동 배포하는 워크플로는 없다. 전체 지도의 CI/AWS 점선은 IaC와 배포 대상의
관계만 표시하며 실행선을 뜻하지 않는다.

## 1. 선 읽는 법

- 바탕 도면의 실선은 Terraform에서 확인한 흐름이다.
- 바탕 도면의 자홍 점선은 실제 연결이 구현되지 않은 구간이다.
- 웹에서 덧씌우는 주황 실선은 진입 경로, 청록 점선은 별도 로컬 코드, 갈색 실선은 기록·탐지 구성을 뜻한다.
- 회색 점선 상자는 시나리오 선언 또는 운영 미확정 경계다. 선이 없으면 AWS 데이터 흐름이 아니다.
- 붉은 글씨는 주의해서 볼 상태다.

## 2. 사용자의 요청이 이동하는 순서

1. 지원자나 채용 담당자가 서비스에 접속한다.
2. Route 53이 서비스의 인터넷 주소를 안내한다.
3. CloudFront가 웹 콘텐츠를 전달한다.
4. AWS WAF가 웹 요청을 정해 둔 규칙으로 검사하도록 설계됐다.
5. ALB가 요청을 4개 앱 서비스로 나누도록 설계됐다.
6. RDS와 Redis는 저장소로 설계됐지만 앱과의 실제 연결은 구현되지 않았다. CloudWatch와 S3는 로그를 받도록 설계됐다.

## 3. 서비스·보조 경로별로 보는 흐름

웹 도면의 버튼은 선택에 따라 전체 시스템 지도, AWS 경로 강조 도면, MLOps 7단계 도면을
전환한다. 색만으로 상태를 판단하지 않도록 지나는 순서와 확인 수준을 글로도 함께 보여 준다.

| 선택 항목 | 무엇을 보여 주나 | 꼭 알아둘 한계 |
|---|---|---|
| 구직자 공고 추천 | 이력서와 열린 공고의 조건을 비교하는 흐름 | 합격 예측이 아닌 조건 일치도 제공 |
| 기업용 인재 찾기 | 자사 공고에 지원한 활성 후보자를 비교하는 흐름 | 최대 3명의 비교 선택은 현재 화면에서만 유지 |
| AI 설명 만들기 | API Lambda → LLM Gateway Lambda → Capability Broker Lambda → Bedrock | production-serverless E2E smoke PASS, 2-AZ ECS 목표 경로는 미배포 |
| MLOps 학습·평가 | 합성 자료 준비부터 사람 검토 대기까지의 모델 검증 흐름 | bootstrap 13개 적용, runtime/Lambda·서비스 연계 전 |
| 업무망·Slack | PC 수량, VPN+MFA·UTM 선언과 외부 업무 SaaS 자산대장 경계 | Slack 실제 workspace 운영과 AWS 연동은 확인되지 않음 |
| TRACE·JC-RECEIPT | 보조 설명에서만 다루는 receipt·정정·사람 검토 source | 실행 인프라·구현 대상으로 전체 지도에 넣지 않음 |
| 외부 업무도구 | admin의 고정 합성 이벤트를 Slack·Notion·SMTP로 보내는 opt-in 경로 | 실제 credential·외부 전송·AWS 리소스 없음 |
| 기록·탐지 | 위협 탐지, 파일·앱 로그 목적지, AWS 작업 기록을 왼쪽부터 확인 | 운영 효과는 별도 관찰 기록에서 확인 |

기업용 인재 찾기 화면은 현재 응답 안에서 이름·직무·기술과 최소 표시 점수로 좁혀 보고,
최대 3명의 계산 내역을 나란히 보는 로컬 UI를 포함한다. 필터는 서버가 준 순서를 바꾸지
않는다. 기업 선언문과 자소서의 문자열 대조도 기존 점수에 반영되지 않는다.

OpenDART 기업 공개정보는 추천 점수와 분리된 source-only 보조 경계로 전체 지도에 표시한다.
SQS FIFO 2개·Lambda·DynamoDB·ECR·IAM·CloudWatch Logs의 0/8/11 source가 있지만 배포와 실호출은 확인되지 않았다.
MLOps를 선택하면 기준 110개와 분리된 서버리스 모델 검증 루트 7단계를 전체 맥락 안에서 보여 준다.

### 3.1 MLOps 경로를 번호로 따라가기

1. 별도 랩의 합성 회원·기업 자료를 읽는다.
2. 자료를 기술·경력·직무와 두 가지 단어 겹침으로 구성한 숫자 특징 5개로 줄인다.
3. feature-only S3 입력 파일 3개(원문 없는 feature CSV 1개와 검증 JSON 2개)를 실행 번호별 경로에 보관한다.
4. 담당자가 확인값과 실행 정보를 넣어 일회성 Lambda를 직접 시작한다.
5. Lambda가 세 파일과 해시를 검사하고 후보 모델을 한 번 학습한다.
6. S3에 결과 파일 6개, DynamoDB에 실행 상태를 남긴다.
7. `TRAINED_PENDING_HUMAN_REVIEW`에서 끝내고 사람의 결정을 기다린다.

전용 Terraform은 기본 잠금 0개, bootstrap 13개, runtime 14개로 나뉜다.
2026-08-31 bootstrap 13개 기반 적용은 확인됐지만 이미지 게시·14번째 Lambda 배포·실행,
결과 6종·모델 승인·추천 서비스 연결은 확인되지 않았다. 기준 Terraform의 110개와 합산하지 않는다. 자세한 일곱 단계는
[MLOps 전용 명세](../../mlops/)에서 확인할 수 있다.

자동 일정, 자동 모델 승격과 현재 추천 런타임 배선은 없다. 공개 도면의 MLOps 처리선은
bootstrap 기반과 아직 실행하지 않은 runtime 단계를 함께 설명하며 기준 110개 AWS 설계의 실행선이 아니다.

### 3.2 LLM Gateway·Bedrock·OpenDART 경계

1. ECS 기준선에는 `web`·`api`·`agent`·`llm-gateway` 네 서비스 정의가 있다.
2. LLM Gateway는 설명 전용 로컬 소스가 구현됐지만 기준 ECR 이미지 게시와 AWS 실행은 미확인이다.
3. Bedrock adapter는 Gateway 안에 있고 기본값은 `local-synthetic-stub`, `ALLOW_BEDROCK_LIVE=false`다.
4. APAC Nova Lite 직접 합성 호출 한 건(입력 39·출력 53토큰)은 PASS다.
5. 조건부 capability broker는 별도 Lab source이며 `API → Gateway → Broker → Bedrock` 전체 경로는 미확인이다.
6. OpenDART는 별도 broker와 SQS 2개·Lambda·DynamoDB·ECR·IAM·Logs의 0/8/11 serverless source만 있으며 적용·API key·외부 실조회는 미확인이다.

### 3.3 업무망과 Slack 경계

1. 업무망 수량은 Windows 100대와 macOS 80대, 합계 180대로 사용자 확인됐다.
2. VPN+MFA와 UTM은 시나리오 선언이다. 이 저장소에서 구현·배치·운영 관찰을 확인한 상태가 아니다.
3. Slack은 AWS 밖의 외부 업무 SaaS·자산대장 경계다. Windows/macOS 이미지 소스의
   `app.slack.com` 바로가기와 macOS 종료 시 best-effort Slack 프로세스 종료를 확인했다.

기존 API에는 기본 비활성 Slack webhook 어댑터가 있지만 실제 workspace 사용, 계정,
보존·삭제 정책과 전송은 `SCENARIO_USE_UNVERIFIED`다. Amazon Q Developer(AWS Chatbot), SNS,
EventBridge나 새 Terraform 리소스는 없다.

Windows 이미지 기준선, macOS MDM 우선 경로와 배포 후 단말 관찰 방법은
[이기종 업무 단말 보안 진단 사례](../../consulting/)에서 별도로 설명한다.

### 3.4 TRACE·JC-RECEIPT 경계

1. 기존 70·20·10 추천 결과가 성공하면 최소 개인정보 receipt를 만들 수 있다.
2. 지원자는 구조화 정정 요청을 내고, 원본과 정정 입력의 점수 관찰값을 분리해 볼 수 있다.
3. 관리자는 `UPHOLD`, `CHANGE`, `REQUEST_INFO`, `ESCALATE` 중 사람 처분만 기록한다.

`TRACE_MODE` 기본값은 `disabled`다. 로컬 API·역할별 화면과 합성 회귀시험이 있으나 실제 지원자
자료, 운영 승인, AWS 배포와 새 Terraform 리소스는 없다. 합격, 이의, ISO 충족 또는 잔여위험을
자동 판정하지 않는다.

### 3.5 외부 업무도구 경계

1. admin 상태 API는 Slack·Notion·SMTP 설정의 활성 가능 여부만 확인하고 외부 probe를 하지 않는다.
2. admin 합성 전송 API는 고정 `SYNTHETIC_NON_PERSONAL` 이벤트만 받고 감사 요청을 먼저 기록한다.
3. 명시적으로 opt-in된 provider만 exact-host/TLS/timeout/redaction과 멱등 경계를 거쳐 시도한다.

세 어댑터는 전역과 provider별 기본값이 모두 꺼져 있다. 현재 확인된 것은 외부 네트워크를 대역으로
바꾼 18건의 계약 시험뿐이며 실제 credential, Slack/Notion workspace, 메일 시스템, 메시지 전송,
AWS 리소스는 확인하지 않았다. SMTP 소스 존재를 조직 그룹웨어 연동 완료로 읽지 않는다.

## 4. AWS 안의 세 구역

| 구역 | 들어 있는 것 | 쉬운 설명 |
|---|---|---|
| 공개 구역 | 도면에는 ALB 표시. Terraform의 NAT 2개는 생략 | 인터넷 요청을 받고 외부 연결을 내보내도록 설계됨 |
| 앱 구역 | ECS Fargate 서비스 4종 | 화면, 업무 처리, 추천, 인공지능 설명을 맡도록 설계됨 |
| 데이터 구역 | RDS, Redis | 주요 데이터와 임시 추천 결과를 보관함 |

세 구역은 서울 지역의 2a와 2c에 나누도록 설계됐다. 데이터 구역에는 인터넷으로 바로
나가는 경로가 없다.

## 5. 기준 설계 밖의 항목

- 서비스 구현 코드는 검증용 합성 데이터를 사용한다. 전체 source/static/fixture 검사 115건을 통과했다. 이는 소스와 시험 자료의 예상 결과를 대조한 값이며 AWS 실행 결과가 아니다.
- OpenDART 공개정보 기능의 기본값은 합성 예시다. 0/8/11 source는 있으나 Terraform 적용·API key·외부 실조회는 없다.
- MLOps 전용 루트는 합성 특징 파일만 받도록 작성됐고 현재 추천 점수나 순위를 바꾸지 않는다. bootstrap 13개 기반만 적용됐고 runtime/Lambda는 미배포·미실행이다.
- MLOps 전용 경계 시험 19건과 합성 파이프라인 시험 22건을 통과했다. 기반 적용은 모델 품질 평가나 운영 완료를 뜻하지 않는다.
- Slack·Notion·SMTP 어댑터는 기본 비활성 소스와 무통신 시험만 있으며 workspace·메일 시스템 운영이나 실제 전송을 증명하지 않는다.
- TRACE·JC-RECEIPT는 기본 비활성 로컬 소스다. 운영 승인·실데이터·자동 채용/이의/적합성/잔여위험 판정 증거가 아니다.
- 2026-09-01 production-serverless의 API→LLM Gateway→Capability Broker→Bedrock 전체 경로와 live smoke를 확인했다. 이 결과를 미배포 2-AZ ECS 목표 경로의 증거로 확대하지 않는다.
- AWS 검증 Lab은 production과 별도이며 private EC2는 정지 상태다. NAT·공인 IPv4·볼륨·edge 등 잔존 비용 가능 경로는 별도 정리 대상이다. MLOps 13개·Lab·production-serverless·AS-IS 기준선 110개를 서로 합산하지 않는다.
- 컨설턴트 대시보드는 고객사 AWS에 직접 연결하지 않는다. 승인된 비식별본만 받아야 한다.
- 외부 미리보기에는 민감정보 제거본만 쓴다.
- 개선안(TO-BE)은 승인 전 리소스 0개를 유지한다. 승인 정보에 문제가 있으면 중단한다.

## 6. 이 그림만 보고 단정하면 안 되는 것

- 고객사 AWS에 같은 구성이 실제로 있다는 뜻이 아니다.
- 2-AZ 기준 애플리케이션이 실행 중이라는 뜻이 아니다. 현재 검증된 것은 별도 production-serverless다.
- 업무망 PC가 AWS에 연결됐다는 뜻이 아니다. 실제 접속 경로는 확인하지 못했다.
- Slack workspace가 운영 중이거나 AWS 알림·이벤트와 연결됐다는 뜻이 아니다.
- TRACE·JC-RECEIPT와 외부 업무도구 소스가 실제 운영 또는 AWS에 배포됐다는 뜻이 아니다.

## 7. USD 50 핵심 평가 슬라이스와 컨설팅 경계

기업 목표 설계를 없애거나 축소한 것이 아니다. 고정비가 큰 ECS·RDS·Redis·NAT 2-AZ 구성은
목표 설계로 유지하고, 현재 예산에서 실제 OWASP LLM 시연과 증적 수집에 필요한 경로만 별도
서버리스 스택으로 배포한다.

1. 지원자·채용담당자는 CloudFront HTTPS 화면에서 AI 매칭 실행을 요청한다.
2. API Gateway와 API Lambda는 tenant 경계와 입력 계약을 검사하고 `202 Accepted`를 반환한다.
3. SQS가 요청을 보존하고 Agent Lambda가 결정식 점수와 근거를 만든다.
4. LLM Gateway는 설명에 필요한 최소 필드만 만들며 capability broker만 허용된 Bedrock model ARN을 호출한다.
5. 결과와 correlation ID는 DynamoDB·S3·CloudWatch에 남고 화면은 상태를 polling한다.
6. 제안된 Evidence Desk에서는 컨설턴트가 고객 DB나 AWS API를 브라우저에서 직접 조회하지 않는다. 사람이 승인한 비식별·서명·만료 snapshot만 별도 경계로 반입한다. 이 경계는 아직 미배포다.

OpenDART와 MLOps는 별도 수명주기다. 두 경로는 추천 결과에 자동 연결하지 않으며 사람 검토 전
승격하지 않는다. Redis는 필수 저장소가 아닌 선택형 성능 계층으로 두고, 없을 때도 cache miss로
정상 처리해야 한다. Windows 100대와 macOS 80대는 자산 모델이며 현재 실제 배포 수량이 아니다.
새 지도는 [웹용 SVG](../../assets/JCAREER_PRODUCTION_ASSESSMENT_MAP.svg)와
[편집 가능한 draw.io 원본](../../assets/JCAREER_PRODUCTION_ASSESSMENT_MAP.drawio)으로 제공한다.
2026-09-01 GitHub 승인형 OIDC apply와 live smoke는 성공했지만 이를 전체 기업 production 완료로 주장하지 않는다.
