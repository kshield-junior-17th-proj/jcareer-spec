#!/usr/bin/env python3
"""Phase 0 선행조건 검사 — V2.1 (검수 V2-P0-01).

V2 결함: BOOTSTRAP_PROMPT 와 TASK-000 이 존재하지 않는 docs/current 문서를 첫 읽기 대상으로
         지정했다. Orca 는 시작 즉시 중단하거나 초안을 현행으로 오인한다.

V2.1: Phase 0 읽기 목록을 실제 존재하는 4개로 제한하고, 시작 전에 이 스크립트로 확인한다.
"""
import pathlib, sys

REQUIRED = [
    "AGENTS.md",
    "context/MANIFEST.yaml",
    "CONFLICT_MATRIX.md",
    "context/handoffs/TASK-000-migration-audit.md",
]
MUST_NOT_BE_REQUIRED = [
    "docs/current/AUTHORITY_MAP.md",
    "docs/current/CURRENT_SCOPE.md",
    "docs/current/CURRENT_DECISIONS.md",
    "docs/current/SCENARIO_FACTS.md",
]
PREAUDIT_HINT = "migration/PRE_AUDIT_APPROVED.json"


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                        pathlib.Path(__file__).resolve().parent.parent).resolve()
    errs, warns = [], []

    for r in REQUIRED:
        if not (root / r).is_file():
            errs.append(f"Phase 0 선행 파일 없음: {r}")

    # Phase 0 구간이 존재하지 않는 승인 문서를 필독으로 지정하고 있지 않은지 역검사.
    # BOOTSTRAP_PROMPT 의 Phase 1 절은 승격 후 시점을 다루므로 검사에서 제외한다.
    for doc, cut in ((root / "BOOTSTRAP_PROMPT.md", "## Phase 1"),
                     (root / "context/handoffs/TASK-000-migration-audit.md", None)):
        if not doc.is_file():
            continue
        text = doc.read_text(encoding="utf-8", errors="replace")
        if cut and cut in text:
            text = text.split(cut, 1)[0]
        for bad in MUST_NOT_BE_REQUIRED:
            if bad in text and not (root / bad).is_file():
                errs.append(f"{doc.name} Phase 0 구간이 존재하지 않는 문서를 요구함: {bad}")

    if not (root / PREAUDIT_HINT).is_file():
        warns.append(f"{PREAUDIT_HINT} 없음 — PRE_AUDIT 사람 승인이 아직입니다. "
                     f"Phase 0 은 시작할 수 있으나 FLATTEN 은 금지입니다")

    print(f"Phase 0 preflight · 필수 {len(REQUIRED)}건 검사")
    for w in warns:
        print(f"::warning::{w}")
    for e in errs:
        print(f"::error::{e}")
    if errs:
        print("::error::Phase 0 을 시작할 수 없습니다.")
        return 1
    print("Phase 0 선행조건 충족")
    return 0


if __name__ == "__main__":
    sys.exit(main())
