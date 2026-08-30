# terraform — 3분할

```
asis/   전체 다이어그램의 선언적 AS-IS 모델. validate·plan·정적분석만. apply 금지
lab/    t3.small 중심 실제 재현환경. 측정 5건 실행. apply 허용 (가드레일 있음)
tobe/   사람이 승인한 보완대책 반영. ③ GAP 판정 전에는 디렉토리를 만들지 않는다
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
