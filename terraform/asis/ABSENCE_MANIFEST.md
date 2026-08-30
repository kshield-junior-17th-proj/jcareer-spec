# ABSENCE_MANIFEST — 의도적으로 선언하지 않은 리소스

`EXPECTED_FINDINGS.yaml` 의 `type: ABSENCE` 항목은 **리소스가 없는 것이 AS-IS** 다.
검사기는 이 파일 또는 `.tf` 주석에서 GAP ID 를 찾아
「의도적 미선언」과 「그냥 빠뜨림」을 구분한다. (V1 은 아무 `.md` 에만 있어도 통과했다.)

| GAP ID | 미선언 리소스 | 근거 |
|---|---|---|
| GAP-CFG-01 | `aws_config_configuration_recorder` · `aws_config_delivery_channel` | `context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2` |
| GAP-SEC-01 | `aws_secretsmanager_secret` · `aws_secretsmanager_secret_version` | `context/raw/SCENARIO_FACTS-가상고객사J사.md#5.2` |
| GAP-KMS-01 | `aws_kms_key` | `context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2` |
| GAP-EGRESS-01 | `aws_networkfirewall_firewall` · `aws_route53_resolver_firewall_rule_group` | `context/proposals/docs-current/CURRENT_DECISIONS_DELTA.md#D-07` |
| GAP-WAF-01 | WAF 커스텀 regex 규칙 블록 | `context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2` |

**이 표의 리소스를 추가하면 AS-IS 가 사라지고 CI 가 실패한다.**
