#!/usr/bin/env python3
"""PowerShell 스크립트 정적 계약 검사 — V2.1 (검수 V2-P0-03).

이 환경에 PowerShell 런타임이 없어 실동작을 시험할 수 없다.
대신 fail-closed 에 필요한 구조가 **소스에 존재하는지** 정적으로 검증한다.
런타임 검증은 여전히 사람이 Windows 에서 수행해야 한다 (BUNDLE_AUDIT §4).
"""
import pathlib, re, sys

REQUIRED = {
    "MIGRATION_PRE_AUDIT.ps1": [
        (r'\$ErrorActionPreference\s*=\s*"Stop"', "ErrorActionPreference=Stop"),
        (r'Assert-Native|LASTEXITCODE', "native exit code 확인"),
        (r'git bundle create', "bundle 생성"),
        (r'git bundle verify', "bundle 검증"),
        (r'Get-FileHash', "파일 SHA256 기록"),
        (r'Assert-PathSafety|PathSafety', "경로 안전성 검사"),
        (r'symbolic-ref|DEFAULT_BRANCH', "기본 브랜치 확인"),
    ],
    "MIGRATION_FLATTEN.ps1": [
        (r'\$ErrorActionPreference\s*=\s*"Stop"', "ErrorActionPreference=Stop"),
        (r'PRE_AUDIT_APPROVED', "사람 승인 파일 요구"),
        (r'Assert-Native|LASTEXITCODE', "native exit code 확인"),
        (r'Assert-PathSafety|PathSafety', "Source/Staging 중첩 경로 금지"),
        (r'Get-FileHash', "전후 SHA 비교"),
        (r'ApprovedNestedRepos|approved_nested', "승인된 nested repo 만 해체"),
        (r'throw ', "실패 시 non-zero 종료"),
    ],
}
FORBIDDEN = [
    (r'Remove-Item[^\n]*\$Source', "원본 경로에서 삭제"),
    (r'\|\s*Out-Null\s*$', None),   # 정보용, 실패 아님
]


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                        pathlib.Path(__file__).resolve().parent.parent).resolve()
    errs = []
    for name, checks in REQUIRED.items():
        f = root / "migration" / name
        if not f.is_file():
            errs.append(f"{name} 없음"); continue
        text = f.read_text(encoding="utf-8", errors="replace")
        for rx, desc in checks:
            if not re.search(rx, text):
                errs.append(f"{name}: {desc} 누락")
        for rx, desc in FORBIDDEN:
            if desc and re.search(rx, text, re.M):
                errs.append(f"{name}: 금지 패턴 — {desc}")
    print(f"PS1 정적 계약 검사 · {len(REQUIRED)}개 파일")
    for e in errs:
        print(f"::error::{e}")
    if errs:
        return 1
    print("정적 계약 충족 (런타임 검증은 별도 — BUNDLE_AUDIT §4)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
