# 보안성 검토용 endpoint review 대장 — Windows 3 + macOS 3

> **이 대장의 단말은 존재하지 않는다.** 조달·구축·이미지 배포·클라우드 생성 중 어느 것도 하지 않았다.
> AWS 자원은 이 팩에 하나도 없고 Terraform 이 관리하지도 않는다.
> 아래 표의 상태값은 **관찰 상태**일 뿐이며 통제의 충족 여부나 위험 수준을 뜻하지 않는다.
> 그 판단은 사람이 `docs/current/**` 에서 정한다.

| 항목 | 값 |
|---|---|
| 기계판독 원본 | `fleet/inventory/endpoint_review_pack.yaml` |
| 상류 계약 | `src/runtime/contracts/endpoint_test_sample.yaml` |
| 팩 상태 | `NOT_EXECUTED` |
| 실물 존재 | 없음 (`devices_exist: false`) |
| 조달 상태 | `NOT_PROCURED` |
| AWS 관리 | 없음 |
| Terraform 관리 | 없음 |
| 검증기 | `scripts/check_fleet_endpoint_review.py` |

## 두 계층을 섞지 않는다

| 계층 | 규모 | 성격 |
|---|---|---|
| 시나리오 inventory | Windows 100 + macOS 80 = 180 | 문서로만 존재. 진단 대상 설정 |
| 이 검토 표본 | Windows 3 + macOS 3 = 6 | 검토 슬롯. 모집단 대표성 없음 (`representative_of_fleet: false`) |

6대는 180대를 대표하지 않는다. 보고서에서 6대의 기록을 180대의 상태로 확장해 쓰지 않는다.

## 가명 자산 ID

실제 단말 식별자(시리얼·MAC·호스트명·사용자명)를 쓰지 않는다.
ID 는 아래 식으로만 만들며 입력에 실데이터가 들어가지 않는다.

```
asset_id = "JC-EP-" + {WIN|MAC} + "-" + sha256("jcareer-fleet-endpoint-review-v1|" + profile_id)[:12].upper()
```

같은 profile_id 는 항상 같은 asset_id 로 재현된다. 검증기가 매 실행마다 재계산해 대조하므로
손으로 고쳐 넣은 값은 통과하지 못한다.

## 단말 대장

| asset_id | profile_id | OS | 합성 페르소나 | 허용 flow | os | browser | edr | vpn |
|---|---|---|---|---|---|---|---|---|
| JC-EP-WIN-542091DC6225 | WIN-01 | windows | candidate | candidate-journey | NOT_OBSERVED | NOT_OBSERVED | NOT_OBSERVED | NOT_OBSERVED |
| JC-EP-WIN-3215639865F3 | WIN-02 | windows | recruiter | recruiter-journey | NOT_OBSERVED | NOT_OBSERVED | NOT_OBSERVED | NOT_OBSERVED |
| JC-EP-WIN-9E36EE01E8CA | WIN-03 | windows | administrator | admin-audit-read | NOT_OBSERVED | NOT_OBSERVED | NOT_OBSERVED | NOT_OBSERVED |
| JC-EP-MAC-1476861A2E2C | MAC-01 | macos | candidate | candidate-journey | NOT_OBSERVED | NOT_OBSERVED | NOT_OBSERVED | NOT_OBSERVED |
| JC-EP-MAC-6F1B42196499 | MAC-02 | macos | recruiter | recruiter-journey | NOT_OBSERVED | NOT_OBSERVED | NOT_OBSERVED | NOT_OBSERVED |
| JC-EP-MAC-F2ACFD9242C4 | MAC-03 | macos | administrator | admin-audit-read | NOT_OBSERVED | NOT_OBSERVED | NOT_OBSERVED | NOT_OBSERVED |

`NOT_OBSERVED` 는 "문제 없음"이 아니라 **아직 아무것도 보지 않았다**는 뜻이다.
팩 상태가 `NOT_EXECUTED` 인 동안 이 열은 다른 값이 될 수 없고, 검증기가 이를 강제한다.

## 시나리오 문서가 선언한 posture

측정값이 아니다. 사람이 쓴 시나리오 문서의 선언을 그대로 옮긴 것이며 위 6대의 관찰과 섞지 않는다.

| OS 군 | os | browser | edr | vpn |
|---|---|---|---|---|
| windows | AD_JOINED | NOT_DECLARED | NOT_ADOPTED | MFA_VPN_DECLARED |
| macos | NOT_AD_JOINED_LOCAL_ACCOUNT | NOT_DECLARED | NOT_ADOPTED | MFA_VPN_DECLARED |

근거: `fleet/README.md#시나리오-inventory--구축하지-않는다`, `context/raw/SCENARIO_FACTS-가상고객사J사.md#9.3`

## 사람이 정할 것

검증기는 아래를 대신 정하지 않는다. 값이 비어 있는 것은 결함이 아니라 대기 상태다.

- OS·브라우저 버전과 EDR·VPN 제품의 실제 선정
- 이미지 소유·출처·승인 (macOS 는 `fleet/README.md` 상 이미지 배포 자체가 불가)
- 관찰 방법과 실행 승인 (`method_ref`)
- 관찰 결과가 통제상 무엇을 뜻하는지에 대한 판단
