#!/usr/bin/env python3
"""terraform/asis 작성 계약 검사.

무자격증명 plan 을 위해 필요한 두 가지를 강제한다.

1. data source 금지
   plan 시점에 실제 AWS API 를 호출하므로 자격증명 없이 깨진다.
   aws_iam_policy_document 만 예외 (로컬 계산).
2. mock provider 블록
   skip_credentials_validation / skip_requesting_account_id / skip_metadata_api_check

리소스가 100개를 넘어가면 에이전트가 관행대로 data source 를 쓴다.
문서 규칙만으로는 못 막는다.
"""
import pathlib, re, sys

ALLOWED_DATA = {"aws_iam_policy_document"}
DATA_BLOCK = re.compile(r'^\s*data\s+"([^"]+)"\s+"([^"]+)"\s*\{', re.M)
REQUIRED_PROVIDER_FLAGS = (
    "skip_credentials_validation",
    "skip_requesting_account_id",
    "skip_metadata_api_check",
)


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                        pathlib.Path(__file__).resolve().parent.parent).resolve()
    layer = sys.argv[2] if len(sys.argv) > 2 else "terraform/asis"
    base = root / layer
    if not base.exists():
        print(f"{layer} 없음 — 검사 생략 (Phase 1 이전)")
        return 0

    tf = sorted(base.rglob("*.tf"))
    if not tf:
        print(f"{layer} 에 .tf 없음 — 검사 생략")
        return 0

    errs = []
    provider_text = ""
    for f in tf:
        text = f.read_text(encoding="utf-8", errors="replace")
        rel = f.relative_to(root).as_posix()
        for m in DATA_BLOCK.finditer(text):
            dtype = m.group(1)
            if dtype in ALLOWED_DATA:
                continue
            line = text[:m.start()].count("\n") + 1
            errs.append((rel, line,
                         f'data "{dtype}" 금지 — 자격증명 없는 plan 에서 실패한다. '
                         f'variable 로 대체하라'))
        if re.search(r'provider\s+"aws"\s*\{', text):
            provider_text += text

    if provider_text:
        for flag in REQUIRED_PROVIDER_FLAGS:
            if flag not in provider_text:
                errs.append(("provider", 0, f'provider "aws" 에 {flag} = true 가 없다'))
    else:
        errs.append(("provider", 0, 'provider "aws" 블록을 찾지 못했다'))

    print(f"{layer} 계약 검사 · .tf {len(tf)}개")
    for rel, line, why in errs:
        loc = f"file={rel},line={line}" if line else ""
        print(f"::error {loc}::{why}")
    if errs:
        print(f"::error::{layer} 작성 계약 위반 {len(errs)}건")
        return 1
    print("data source 없음 · mock provider 설정 확인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
