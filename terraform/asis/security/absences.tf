# terraform/asis/security — 의도적 미선언 대장
#
# 이 파일에는 리소스가 없다. 주석만 있다.
#
# 왜 필요한가: 검사기는 .tf 주석 또는 terraform/asis/ABSENCE_MANIFEST.md 에서만
# GAP ID 를 인정한다 (scripts/check_expected_findings.py · anchor_in_tf).
# 주석이 없으면 「의도적 미선언」과 「그냥 빠뜨림」을 구분하지 못해 실패한다.
# ABSENCE_MANIFEST.md 는 공유 파일이고 사람이 관리하므로 에이전트는 건드리지 않는다.
#
# 원칙: GAP 근거 주석은 근거가 드러나는 코드 옆에 둔다. 이 파일은 그 자리가 없는 것만 맡고,
# 나머지는 어디에 있는지 가리키기만 한다. 같은 설명을 두 곳에 쓰지 않는다.
#
#   GAP-EGRESS-01  terraform/asis/security/endpoints.tf 하단
#   GAP-SEC-01     terraform/asis/security/iam.tf · ECS task execution role 뒤
#   GAP-KMS-01     terraform/asis/security/iam.tf · ECS task role 의 S3 정책문 안
#   GAP-CFG-01     terraform/asis/security/iam.tf 하단
#   GAP-WAF-01     아래
#
# ──────────────────────────────────────────────────────────────────────────────
# GAP-WAF-01 [ABSENCE] WAF 자유서술 입력 커스텀 규칙 없음 — 관리형 규칙셋만
# 근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2
#       (엣지 · Q01 — AWSManagedRulesCommonRuleSet + SQLi 적용, 이력서 본문·자기소개서에
#        적용되는 커스텀 규칙 미수립)
#       context/raw/인프라컨텍스트-외부협업용.md#2.2
#
# 소유는 edge 모듈이다 (terraform/asis/edge/ · aws_wafv2_web_acl). 여기서는 교차 참조만 한다.
# security 모듈은 aws_wafv2_* 를 일절 선언하지 않는다 — regex_pattern_set 도,
# regex_pattern_set_reference_statement 를 담은 rule 블록도 만들지 않는다.
#   aws_wafv2_regex_pattern_set — 의도적 미선언
#   WAF 커스텀 regex 규칙 블록  — 의도적 미선언
# 이 리소스들을 선언하지 않는 것이 AS-IS 다. 추가하지 말 것.
