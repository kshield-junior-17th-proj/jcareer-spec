#!/usr/bin/env bash
# V2.1 가드레일 회귀 시험.
#   A~D : V1 에서 뚫렸던 20건 (유지)
#   E~K : V2 독립 적대 테스트에서 뚫린 것 + 검수 §6 부정 시험 21건
set -uo pipefail
cd "$(dirname "$0")/.."
S=scripts; F=tests/fixtures
PASS=0; FAIL=0
if command -v python3 >/dev/null 2>&1; then
  :
elif command -v python >/dev/null 2>&1; then
  python3 () { python "$@"; }
elif command -v python.exe >/dev/null 2>&1; then
  python3 () { python.exe "$@"; }
elif command -v py >/dev/null 2>&1; then
  python3 () { py -3 "$@"; }
else
  printf 'Python 3 실행 파일을 찾을 수 없습니다. python3, python, python.exe 또는 py -3이 필요합니다.\n' >&2
  exit 127
fi
if command -v node >/dev/null 2>&1; then
  JS_RUNTIME=node
elif command -v node.exe >/dev/null 2>&1; then
  JS_RUNTIME=node.exe
else
  JS_RUNTIME=node
fi
run () { local want=$1; shift; local desc=$1; shift
  out=$("$@" 2>&1); got=$?
  if [ "$got" = "$want" ]; then printf '  PASS  [exit %s] %s\n' "$got" "$desc"; PASS=$((PASS+1))
  else printf '  FAIL  [exit %s, 기대 %s] %s\n' "$got" "$want" "$desc"
       printf '%s\n' "$out" | sed 's/^/        /'; FAIL=$((FAIL+1)); fi; }
grepfail () { local want=$1 desc=$2 pat=$3 file=$4
  if grep -qE "$pat" "$file"; then got=1; else got=0; fi
  if [ "$got" = "$want" ]; then printf '  PASS  [%s] %s\n' "$got" "$desc"; PASS=$((PASS+1))
  else printf '  FAIL  [%s, 기대 %s] %s :: /%s/ in %s\n' "$got" "$want" "$desc" "$pat" "$file"; FAIL=$((FAIL+1)); fi; }

echo "== A. raw 무결성 (locked) — V1 회귀 =="
run 0 "정상"           python3 $S/check_raw_hashes.py $F/manifest/ok
run 1 "해시 미기입"     python3 $S/check_raw_hashes.py $F/manifest/blank
run 1 "선언 파일 누락"   python3 $S/check_raw_hashes.py $F/manifest/missing
run 1 "미선언 파일 존재" python3 $S/check_raw_hashes.py $F/manifest/extra
run 1 "중복 경로"       python3 $S/check_raw_hashes.py $F/manifest/dup
run 1 "해시 변조"       python3 $S/check_raw_hashes.py $F/manifest/tamper
run 1 "구 스키마 files: → 실패" python3 $S/check_raw_hashes.py $F/manifest/legacy
run 1 "tracked_files 키 부재 → 실패" python3 $S/check_raw_hashes.py $F/manifest21/no_tracked

echo "== B. 인용 앵커 — V1 회귀 =="
run 0 "정상 + placeholder 무시" python3 $S/check_citations.py --root $F/citations/pos --mode strict --scan docs/current
run 1 "파일명 불일치·없는 절"    python3 $S/check_citations.py --root $F/citations/neg --mode strict --scan docs/current

echo "== C. EXPECTED_FINDINGS — V1 회귀 =="
run 1 "스캐너 비어있음 → SCANNER 실패" python3 $S/check_expected_findings.py --layer t --plan $F/expected_findings/plan_asis_good.json --spec $F/expected_findings/spec_filled.yaml --scanner $F/expected_findings/scanner_empty.json --tfdir $F/expected_findings/tf_with_anchors --out /tmp/t1.json
run 0 "스캐너 채워짐 → 통과"          python3 $S/check_expected_findings.py --layer t --plan $F/expected_findings/plan_asis_good.json --spec $F/expected_findings/spec_filled.yaml --scanner $F/expected_findings/scanner_filled.json --tfdir $F/expected_findings/tf_with_anchors --out /tmp/t2.json
run 1 "AS-IS 를 '개선'함 → 실패"       python3 $S/check_expected_findings.py --layer t --plan $F/expected_findings/plan_asis_agent_fixed.json --spec $F/expected_findings/spec_filled.yaml --scanner $F/expected_findings/scanner_filled.json --tfdir $F/expected_findings/tf_with_anchors --out /tmp/t3.json
run 1 "근거주석이 .md 에만 → 실패"     python3 $S/check_expected_findings.py --layer t --plan $F/expected_findings/plan_asis_good.json --spec $F/expected_findings/spec_filled.yaml --scanner $F/expected_findings/scanner_filled.json --tfdir $F/expected_findings/tf_no_anchors --out /tmp/t4.json
run 1 "rule_id 미기입 명세 → 실패"     python3 $S/check_expected_findings.py --layer t --plan $F/expected_findings/plan_asis_good.json --spec context/proposals/docs-current/EXPECTED_FINDINGS.yaml --scanner $F/expected_findings/scanner_filled.json --tfdir $F/expected_findings/tf_with_anchors --out /tmp/t5.json

echo "== D. lab 비용 — V1 회귀 =="
run 0 "EC2 1대 정상"   python3 $S/check_lab_budget.py --plan $F/lab2/ok.json
run 1 "EC2 0대"        python3 $S/check_lab_budget.py --plan $F/lab/plan_zero.json
run 1 "EC2 2대"        python3 $S/check_lab_budget.py --plan $F/lab/plan_two.json
run 1 "EC2 100대"      python3 $S/check_lab_budget.py --plan $F/lab/plan_hundred.json
run 1 "16TB io2 EBS"   python3 $S/check_lab_budget.py --plan $F/lab/plan_io2.json
run 1 "NAT Gateway"    python3 $S/check_lab_budget.py --plan $F/lab/plan_nat.json
run 1 "m5.4xlarge"     python3 $S/check_lab_budget.py --plan $F/lab/plan_bigtype.json

echo "== E. Phase 0 preflight (V2-P0-01) =="
run 0 "선행조건 충족"                              python3 $S/preflight_phase0.py $F/preflight/ok
run 1 "존재하지 않는 docs/current 문서를 요구 → 실패" python3 $S/preflight_phase0.py $F/preflight/bad
grepfail 0 "TASK-000 이 MANIFEST 직접 수정을 지시하지 않음" 'MANIFEST\.yaml 에 (직접 )?(sha256 을 )?채운다' context/handoffs/TASK-000-migration-audit.md

echo "== F. MANIFEST lifecycle (V2-P0-02) =="
run 0 "locked 정상 (external/excluded 부재 상태)" python3 $S/check_raw_hashes.py $F/manifest21/locked_ok
run 1 "draft + --require-locked → 실패"          python3 $S/check_raw_hashes.py $F/manifest21/draft_ok --require-locked
run 1 "알 수 없는 manifest_state → 실패"          python3 $S/check_raw_hashes.py $F/manifest21/unknown_state
run 1 "반입 금지 파일이 저장소에 존재 → 실패"       python3 $S/check_raw_hashes.py $F/manifest21/excluded_present

echo "== G. 인용 앵커 다중행 YAML (V2-P0-04) =="
run 0 "다중행 anchors/evidence 정상"        python3 $S/check_citations.py --root $F/citations2/ok  --mode strict --scan docs/current
run 1 "다중행 anchors 의 없는 파일/절 → 실패" python3 $S/check_citations.py --root $F/citations2/bad --mode strict --scan docs/current

echo "== H. 스캐너 스키마·주소 (V2-P0-05) =="
run 0 "tfsec 정상 주소 일치"           python3 $S/check_expected_findings.py --layer t --plan $F/ef2/plan.json --spec $F/ef2/spec_tfsec.yaml   --scanner $F/ef2/scanner_ok.json            --tfdir $F/ef2/tf --out /tmp/h1.json
run 0 "checkov 정상 스키마 파싱"        python3 $S/check_expected_findings.py --layer t --plan $F/ef2/plan.json --spec $F/ef2/spec_checkov.yaml --scanner $F/ef2/scanner_checkov.json       --tfdir $F/ef2/tf --out /tmp/h2.json
run 1 "scanner resource 빈 문자열 → 실패" python3 $S/check_expected_findings.py --layer t --plan $F/ef2/plan.json --spec $F/ef2/spec_tfsec.yaml   --scanner $F/ef2/scanner_empty_resource.json --tfdir $F/ef2/tf --out /tmp/h3.json
run 1 "같은 rule_id 다른 주소 → 실패"     python3 $S/check_expected_findings.py --layer t --plan $F/ef2/plan.json --spec $F/ef2/spec_tfsec.yaml   --scanner $F/ef2/scanner_wrong_addr.json    --tfdir $F/ef2/tf --out /tmp/h4.json
run 1 "checkov 비정상 스키마 → 설명 가능한 실패" python3 $S/check_expected_findings.py --layer t --plan $F/ef2/plan.json --spec $F/ef2/spec_checkov.yaml --scanner $F/ef2/scanner_checkov_bad.json --tfdir $F/ef2/tf --out /tmp/h5.json
run 1 "최상위가 object 아님 → 설명 가능한 실패" python3 $S/check_expected_findings.py --layer t --plan $F/ef2/plan.json --spec $F/ef2/spec_tfsec.yaml   --scanner $F/ef2/scanner_not_object.json   --tfdir $F/ef2/tf --out /tmp/h6.json
run 1 "finding id 중복 → 실패"           python3 $S/check_expected_findings.py --layer t --plan $F/ef2/plan.json --spec $F/ef2/spec_dup_id.yaml   --scanner $F/ef2/scanner_ok.json            --tfdir $F/ef2/tf --out /tmp/h7.json
run 0 "WAF 규칙 1개 (custom 없음) → 통과"  python3 $S/check_expected_findings.py --layer t --plan $F/ef2/plan_waf_ok.json         --spec $F/ef2/spec_waf.yaml --tfdir $F/ef2/tf --out /tmp/h8.json
run 1 "WAF 두 번째 규칙에 custom → 실패"    python3 $S/check_expected_findings.py --layer t --plan $F/ef2/plan_waf_second_rule.json --spec $F/ef2/spec_waf.yaml --tfdir $F/ef2/tf --out /tmp/h9.json

echo "== I. lab allowlist·리전·EBS (V2-P0-06) =="
run 1 "SageMaker (allowlist 밖) → 실패" python3 $S/check_lab_budget.py --plan $F/lab2/sagemaker.json
run 1 "region 변수 참조 → 실패"          python3 $S/check_lab_budget.py --plan $F/lab2/region_var.json
run 1 "region 미지정 → 실패"             python3 $S/check_lab_budget.py --plan $F/lab2/region_missing.json
run 1 "region 타 리전 → 실패"            python3 $S/check_lab_budget.py --plan $F/lab2/region_other.json
run 1 "root EBS 미명세 → 실패"           python3 $S/check_lab_budget.py --plan $F/lab2/no_root.json
run 1 "root io2 → 실패"                 python3 $S/check_lab_budget.py --plan $F/lab2/root_io2.json
run 1 "root 500GB → 실패"               python3 $S/check_lab_budget.py --plan $F/lab2/root_big.json
run 1 "ebs_block_device 16TB → 실패"     python3 $S/check_lab_budget.py --plan $F/lab2/ebs_block_big.json

echo "== L. asis 작성 계약 (무자격증명 plan) =="
run 0 "mock provider + policy_document 만 → 통과" python3 $S/check_asis_contract.py $F/asis_contract/ok
run 1 "data source 사용 → 실패"                  python3 $S/check_asis_contract.py $F/asis_contract/datasource
run 1 "provider skip_* 플래그 없음 → 실패"        python3 $S/check_asis_contract.py $F/asis_contract/noflags
run 0 ".tf 없으면 생략 (Phase 1 이전)"            python3 $S/check_asis_contract.py $F/asis_contract/empty

echo "== M. lab 키 주입 경로 =="
run 1 "관리형 SSM Parameter는 현 lab allowlist 밖 → 실패" python3 $S/check_lab_budget.py --plan $F/lab2/ok_with_ssm.json
run 1 "Secrets Manager 는 allowlist 밖 → 실패"    python3 $S/check_lab_budget.py --plan $F/lab2/secretsmanager.json

echo "== J. 공급망 (V2-P0-08) =="
run 0 "SHA 고정 워크플로 통과"             python3 $S/check_action_pinning.py $F/pinning/pinned
run 1 "태그/main/master + curl|bash → 실패" python3 $S/check_action_pinning.py $F/pinning/unpinned

echo "== K. plan sanitize · PS1 계약 · CI 구조 (V2-P0-03/07/09) =="
run 0 "sanitize 실행"                    python3 $S/sanitize_plan.py --plan $F/sanitize/plan_with_secret.json --out /tmp/sane.json
grepfail 0 "sanitized 결과에 민감값 미포함" 'SUPER-SECRET-VALUE' /tmp/sane.json
run 0 "PS1 정적 계약 (bundle verify·승인·SHA비교·경로안전)" python3 $S/check_ps1_contract.py .
grepfail 1 "required-gate job 이 항상 실행"        'if: always\(\)' .github/workflows/ci.yml
grepfail 1 "required-gate 가 모든 job 을 needs"    'needs: \[boundaries, integrity, validators, secrets, terraform\]' .github/workflows/ci.yml
grepfail 0 "원본 plan JSON artifact 업로드 없음"    'upload-artifact' .github/workflows/ci.yml
grepfail 1 "plan JSON 즉시 삭제"                   'rm -f plan_asis.json' .github/workflows/ci.yml
grepfail 0 "워크플로에 path filter 없음(pending 방지)" '^\s+paths:' .github/workflows/ci.yml

echo "== N. 양면 런타임 ↔ Terraform 소스 계약 =="
run 0 "향후 lab AWS-free 정적 경계" python3 $S/check_lab_static.py --root .
run 0 "향후 lab 정적 경계 회귀" python3 tests/test_lab_static.py
run 0 "미실행 endpoint·앱 artifact manifest" python3 $S/check_runtime_manifests.py --root .
run 0 "미실행 manifest 경계 회귀" python3 tests/test_runtime_manifests.py
run 0 "API source surface inventory" python3 $S/check_api_surface_contract.py --root .
run 0 "API surface drift·우회 회귀" python3 tests/test_api_surface_contract.py
run 0 "33개 API source effect inventory" python3 $S/check_api_effects_contract.py --root .
run 0 "API effect fingerprint·순서 회귀" python3 tests/test_api_effects_contract.py
run 0 "33개 API source 반환·직접 예외 inventory" python3 $S/check_api_wire_shapes.py --root .
run 0 "API 반환·직접 예외 drift 회귀" python3 tests/test_api_wire_shapes.py
run 0 "미실행 위험 관찰·영수증 source 계약" python3 $S/check_runtime_evidence_contracts.py --root .
run 0 "위험 관찰·영수증 schema 회귀" python3 tests/test_runtime_evidence_contracts.py
run 0 "지원자·기업 고객 표면과 미배선 선언 일치" python3 $S/check_runtime_infra_contract.py .
run 0 "소스 계약 추출·truth-table 회귀" python3 tests/test_runtime_infra_contract.py
run 0 "API 경계·응답 계약" python3 src/runtime/tests/api_boundary_contract.py
run 0 "8/28 멘토 요구사항 source 계약" python3 src/runtime/tests/mentor_feedback_contract.py
run 0 "합성 MLOps 생성·학습 계약" python3 src/mlops/tests/test_synthetic_pipeline.py
run 0 "serverless MLOps isolated Terraform boundary" python3 $S/check_serverless_mlops_static.py --root .
run 0 "serverless MLOps boundary mutation tests" python3 tests/test_serverless_mlops_static.py
run 0 "Bedrock 응답 parser 계약" python3 src/runtime/tests/bedrock_response_contract.py
run 0 "OpenDART 공개 스냅샷 adapter 계약" python3 src/runtime/tests/opendart_contract.py
run 0 "OpenDART 기업 tenant·last-known-good API 경계" python3 src/runtime/tests/opendart_api_contract.py
run 0 "OpenDART 온디맨드 Lambda 작업자 계약" python3 src/runtime/tests/opendart_worker_contract.py
run 0 "브라우저 API 응답 decoder 계약" "$JS_RUNTIME" src/runtime/web/tests/api-client-contract.mjs
run 0 "양면 웹 정적 계약" "$JS_RUNTIME" src/runtime/web/tests/static-contract.mjs
run 0 "웹 대비·협폭 source 계약" "$JS_RUNTIME" src/runtime/web/tests/contrast-contract.mjs
run 0 "컨설턴트 snapshot validator·renderer lanes" "$JS_RUNTIME" --test dashboard/tests/*.test.mjs
run 0 "컨설턴트 dashboard 정적 경계" "$JS_RUNTIME" dashboard/tests/verify-static.mjs
run 0 "AWS draw.io 구조·경계 계약" python3 $S/check_asis_diagram.py terraform/asis/JCAREER_ASIS_2AZ.drawio
run 0 "AWS draw.io validator 회귀" python3 tests/test_asis_diagram.py

echo
echo "결과: PASS=$PASS  FAIL=$FAIL  (합계 $((PASS+FAIL)))"
[ "$FAIL" = 0 ]
