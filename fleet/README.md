# fleet — 업무망 단말 (CONFLICT_MATRIX C-05 RESOLVED)

## 두 층을 섞지 않는다

```
시나리오 inventory (진단 대상)   Windows 100 + macOS 80 = 180대   문서로만 존재 · ₩0
실제 lab 운용 (재현)             팀원 수만큼 N대                  골든 이미지 + 실물
```

보고서에서 "180대를 운용했다"고 쓰지 않는다. inventory 는 J사 설정이고 실물은 N대다.

## 시나리오 inventory — 구축하지 않는다

`context/raw/SCENARIO_FACTS-가상고객사J사.md#9.3` 의 180대는 ① 진단 대상 계층이다.

```
Windows 100대   AD 도메인 가입 · 전통 백신
macOS   80대    AD 미가입 · 로컬 계정 · 백신 미적용
공통            UTM · VPN(MFA) · EDR 미도입
                망분리 미적용 · §6의2 위험분석 미실시 → 면제 요건도 미충족
```

## 실제 운용 — 골든 이미지 + 팀원 단말

| 대상 | 실물 | 산출물 |
|---|---|---|
| Windows | 골든 이미지 1개 + 팀원 단말 N대 | `windows/` 이미지 정의·기준선 |
| **macOS** | **이미지 배포 불가** — Apple 라이선스상 Apple 하드웨어에서만 실행 | 팀원 Mac 1대를 샘플로. 없으면 `OUT_OF_REPRODUCTION_SCOPE` |
| 자산 대장 | `inventory/` 합성 180건 | 분기 1회 수기 갱신 GAP 재현 |

## 이 구성이 여는 진단 항목

1. **경로 D 악화** — 개발 42·AI개발 8 이 운영 이력서 덤프를 복원하는 단말이
   AD 미가입 + EDR 없음 + 백신 없음이면 중앙 통제가 하나도 걸리지 않는다 (`GAP-EP-01` · `R-14`)
2. **망분리 면제 논증이 두 겹으로 무너진다** — 위험분석 미실시 + 이기종 80대 보호조치 부재 (`GAP-NET-01`)
3. **자산 대장 수기 갱신이 치명적** — 단일 플랫폼이면 버티지만 이기종이면 못 버틴다

## 금지

```
- 180대를 실제로 조달하거나 클라우드에 생성하지 않는다
  (EC2 Mac 은 Dedicated Host · 최소 24시간 할당. 크레딧으로 성립하지 않는다)
- 팀원 단말에 실제 개인정보를 올리지 않는다
- macOS 이미지를 굽거나 배포하지 않는다
```

## 보안성 검토용 합성 review pack — Windows 3 + macOS 3

180대(시나리오)와 6대(검토 표본)는 다른 계층이다. 6대는 180대를 대표하지 않는다.

| 산출물 | 경로 |
|---|---|
| 기계판독 pack | `fleet/inventory/endpoint_review_pack.yaml` |
| 데모용 대장 | `fleet/inventory/ENDPOINT_REVIEW_INVENTORY.md` |
| fail-closed 검증기 | `scripts/check_fleet_endpoint_review.py` |
| 경계 회귀 | `tests/test_fleet_endpoint_review.py` |

pack 은 상류 계약 `src/runtime/contracts/endpoint_test_sample.yaml` 의 6개 profile
(WIN-01~03 · MAC-01~03)에 결속한다. 두 파일이 갈라지면 검증기가 실패한다.

```
실물 단말      없음   devices_exist: false · NOT_PROCURED
AWS 자원       없음   aws_managed: false · Terraform 비관리
posture 관찰   없음   os/browser/edr/vpn 전량 NOT_OBSERVED
자산 ID        가명   sha256(namespace|profile_id)[:12] — 실기기 식별자 입력 없음
```

검증기는 파일이 없거나 파싱되지 않으면 통과시키지 않는다. 미실행 상태에서
`recorded_value`·`method_ref` 를 채우거나 관찰 상태를 바꾸면 거부한다.
AWS 자원 식별자·MAC/IP/UUID/이메일 모양과 판정 어휘가 데이터에 들어와도 거부한다.

검증기는 통제 판정을 하지 않는다. OS·브라우저 버전, EDR·VPN 제품 선정, 이미지
소유·출처·승인, 관찰 방법과 실행 승인은 사람이 정한다.

## 배포 준비 소스 — 아직 이미지·단말은 없음

`images/endpoint_image_contract.yaml`은 WIN-01~03과 MAC-01~03의 이미지·접속 경계를 묶는다.
Windows 구성·검사 component와 consultant 세션 shortcut 도구는 `images/windows/`에 있고,
macOS의 Apple 하드웨어용 준비·관찰 스크립트는 `images/macos/`에 있다. 어떤 파일에도
사용자 자격증명, AWS 키, Slack token, OpenDART 키 또는 preview token을 굽지 않는다.

Terraform은 `terraform/workplace-images`에서 Windows 이미지 정의만, 승인 후
`terraform/workplace-endpoints`에서 t3.small Windows 검토 단말 3대만 만들도록 분리했다.
두 루트 모두 기본 stage가 0-resource이고 실제 build·배포·접속 관찰은 아직 없다. macOS는
물리 Mac+MDM을 우선 경로로 남겼으며 EC2 Mac은 별도 사람 예외 없이는 대상이 아니다.
