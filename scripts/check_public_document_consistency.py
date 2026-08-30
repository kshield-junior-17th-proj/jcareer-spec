#!/usr/bin/env python3
"""Fail when public J-Career documents drift across generated surfaces."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
failures: list[str] = []
passed = 0


def text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def require(relative: str, marker: str, label: str) -> None:
    global passed
    if marker not in text(relative):
        failures.append(f"{label}: required marker missing in {relative}")
        return
    passed += 1


def forbid(relative: str, marker: str, label: str) -> None:
    global passed
    if marker in text(relative):
        failures.append(f"{label}: stale marker remains in {relative}")
        return
    passed += 1


report = json.loads(text("terraform/asis/validation-report.json"))
pdf_check = next(
    (item for item in report.get("checks", []) if item.get("check") == "pdf_page_objects"),
    {},
)
if report.get("failed") == 0 and pdf_check.get("status") == "PASS":
    passed += 1
else:
    failures.append("PDF source binding is not PASS")

for marker in (
    "AS-IS 기준선",
    "AWS 검증 Lab",
    "애플리케이션 여섯 서비스",
    "<strong>Bedrock 직접 합성 호출</strong>",
    "<strong>Bedrock 전체 연결 경로</strong>",
    "OpenDART",
    "MLOps",
    "업무 단말",
    "컨설턴트 대시보드",
):
    require("index.html", marker, f"separate status: {marker}")

require("src/runtime/VERIFICATION.md", "2026-08-28 19:04 KST~2026-08-29", "historical Lab timestamp")
require("src/runtime/VERIFICATION.md", "2026-08-30, 재시도 최종 확인 21:17 KST", "latest Lab timestamp")
require("terraform/lab/DEPLOYMENT_OBSERVATION_2026-08-30.md", "서로 다른 실행이다", "Lab attempts separated")
require("terraform/lab/DEPLOYMENT_OBSERVATION_2026-08-30.md", "Terraform 상태 모두 0", "latest AWS residual inventory")
require("src/runtime/VERIFICATION.md", "39개 셀·8개 연결", "public diagram count")
require("src/runtime/VERIFICATION.md", "77개 셀·23개 연결은 원본 작업 트리의 별도 상세 도면 기록", "separate detailed diagram")

require("mlops/index.html", "서버리스 경계 시험</td><td>19/19 PASS", "MLOps boundary count")
require("mlops/index.html", "합성 MLOps 단위시험</td><td>22/22 PASS", "MLOps unit count")
require("terraform/README.md", "정의 stage 12개", "workplace image stage count")
require("terraform/asis/JCAREER_ASIS_FLOW.md", "전체 source/static/fixture 검사 115건", "current static runner")
require("terraform/asis/architecture.html", "전체 source/static/fixture 검사 115건", "generated architecture runner")
require("index.html", "웹 요청 검사", "WAF declaration wording")
forbid("index.html", "공격 차단", "WAF effect overclaim")
require("terraform/asis/build-spec.mjs", "<dt>기준일</dt><dd>2026-08-30</dd>", "spec date")
require("terraform/asis/build-spec.mjs", "AS-IS 미적용 · 검증 Lab 별도", "spec deployment boundary")
require("terraform/asis/JCAREER_ASIS_SYSTEM_SPEC.md", "결속 시험 28건", "dashboard check count")
require("terraform/asis/JCAREER_ASIS_SYSTEM_SPEC.md", "승인된 복사본 반입이나 운영 배포를 확인한 결과는 아님", "dashboard evidence boundary")
forbid("terraform/asis/JCAREER_ASIS_SYSTEM_SPEC.md", "APPROVE, PASS를 받았다", "agent approval overclaim")
require("assets/JCAREER_PLATFORM_ANIMATED.spec.json", "실물 미관찰", "endpoint observation boundary")
require("dashboard/README.md", "검토용 복사본(`snapshot`)", "dashboard Korean glossary")
require("dashboard/README.md", "승인 반입(`ingestion`)", "dashboard ingestion term")
require("terraform/serverless-opendart/README.md", "기본 비활성 상태에서 0개, 준비 단계에서 8개, 실행 단계에서 11개", "OpenDART Korean summary")
require("terraform/asis/README.md", "기록된 모의 계획에는 생성 예정 항목이 110개", "AS-IS exact count")
forbid("terraform/asis/README.md", "대략 100~150개", "AS-IS approximate count")

for failure in failures:
    print(f"FAIL {failure}")
print(f"PASS={passed} FAIL={len(failures)}")
raise SystemExit(1 if failures else 0)
