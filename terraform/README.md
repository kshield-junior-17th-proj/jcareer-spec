# terraform — 3분할

```
asis/   전체 다이어그램의 선언적 AS-IS 모델. validate·plan·정적분석만. apply 금지
lab/    t3.small 중심 실제 재현환경. 측정 5건 실행. apply 허용 (가드레일 있음)
tobe/   사람이 승인한 보완대책 반영. ③ GAP 판정 전에는 디렉토리를 만들지 않는다
serverless-opendart/   외부 조회 작업자·FIFO 요청·TTL 결과함. 기본 0개, 별도 state
serverless-mlops/      합성 정량 특징의 온디맨드 challenger. 기본 0개, 별도 state
workplace-images/      Windows 검토 단말 이미지 정의. 기본 0개, 정의 stage 12개
workplace-endpoints/   승인 이미지 기반 Windows 3대. 기본 0개, 배치 stage 9개
```

`tobe/` 디렉토리는 **번들에 포함되어 있지 않다.** "생성 금지"라고 하면서 빈 디렉토리를
만들어 두는 것은 모순이라는 검수 지적(P1)을 반영했다.

## tobe/ 생성 조건과 규칙

`docs/current/CONTROL_ASSESSMENT.yaml` 에 `remediation_approved: true` 항목이 존재해야 한다.

**비교 원칙 — 리소스 목록이 같아야 하는 것이 아니다.**

```
업무 기능 변경        0건
AI 서비스 기능 변경   0건
합성데이터·모델·테스트 동일
─────────────────────────
통제 목적 변경        허용
통제용 리소스 추가    허용   (AWS Config · Secrets Manager · CMK ·
                             CloudTrail 데이터이벤트 · WAF 커스텀 규칙 · 로그/알람)
```

**신규 리소스 필수 태그**

```hcl
tags = {
  jk_layer    = "tobe"
  control_id  = "A.7.2"        # ISO/IEC 42001 통제 ID
  gap_id      = "GAP-CFG-01"   # EXPECTED_FINDINGS 의 ID
  evidence_id = "EV-014"
}
```

세 태그가 없는 신규 리소스는 CI 실패. 대시보드 추적성이 여기서 나온다.

## 격리된 `serverless-mlops/` 시연 루트

`serverless-mlops/`는 `asis/` 110-resource mock plan이나 `lab/`의 1-EC2 계약에
합쳐지지 않는 별도 state 루트다. 기본 `deployment_stage=disabled`는 리소스 0개이며,
사람의 정확한 활성화 문구 없이는 bootstrap/runtime 계획이 닫힌다.

이 루트는 EC2 내부의 합성 회원·기업 DB에서 만든 **숫자 특징 스냅샷**만 S3로 받아
온디맨드 Lambda에서 challenger를 학습한다. DB 포트를 열거나 DB URL을 Terraform state에
넣지 않으며 SageMaker, 자동 스케줄, 자동 모델 승격을 사용하지 않는다. AWS에서 실행됐다는
증거는 별도의 승인된 배포·호출 영수증이 생기기 전까지 주장하지 않는다.

## 격리된 OpenDART·업무 단말 루트

`serverless-opendart/`는 API 요청을 FIFO queue로 받고 VPC 밖 Lambda가 OpenDART를 조회한 뒤
TTL DynamoDB 결과함에 둔다. 기존 인증 API만 결과를 회수·검증해 기업 DB에 반영하므로
작업자에 기업 DB 자격증명이나 직접 연결을 주지 않는다. DynamoDB의 지연 삭제와 무관하게
API가 만료시각을 직접 확인하고 현재 pending request에 대한 CAS에 성공할 때만 반영한다.
`score_effect=NONE` 경계는 유지한다.

`workplace-images/`와 `workplace-endpoints/`는 각각 Windows Server 2022 Desktop 기반 보안성
검토용 이미지 정의와 승인 이미지 3대의 배치 계약이다. Windows 11 업무 PC와 동일하다고
주장하지 않으며, macOS는 Apple 하드웨어·라이선스·EC2 Mac Dedicated Host 비용 때문에 이
Terraform에서 생성하지 않는다. 이 세 루트는 외부에서 준비한 암호화 S3 backend, S3 lockfile,
루트별 고정 state key와 사람의 saved-plan 승인 없이는 apply 대상으로 사용할 수 없다. OpenDART
Lambda digest는 plan의 `image_uri`와, Windows endpoint AMI는 별도 image receipt와 다시 대조한다.
현재 AWS 생성 증거는 없다.

생성 계획은 `scripts/Invoke-ApprovedTerraform.ps1`, 제거 계획은
`scripts/Invoke-ApprovedTerraformTeardown.ps1`이 다룬다. 제거도 일반 `terraform destroy`를
바로 실행하지 않고 allowlist 안의 delete-only saved plan을 별도로 만들며, 사람이 그 정확한
SHA-256을 승인한 뒤에만 saved plan을 적용한다. 적용 후에도 별도 잔존 자원 관찰 전에는 0자원이라고
주장하지 않는다. OpenDART ECR은 승인된 teardown 때 이미지를 함께 제거하도록 선언했지만,
Image Builder 실행으로 생긴 AMI·snapshot은 정의 state 밖 산출물이므로 별도 승인형 artifact
cleanup과 사후 inventory 확인이 필요하다.
