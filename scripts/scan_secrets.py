#!/usr/bin/env python3
"""자체 비밀정보 스캔 — 외부 Action 의존 없이 돌아간다.

V2 는 gitleaks-action(@v2 태그)을 썼다. 공급망 고정 요구(V2-P0-08)와 충돌해서
자체 구현으로 대체했다. gitleaks 보다 탐지 범위가 좁으므로, 검증한 릴리스와
SHA256 을 고정해 gitleaks 를 추가하는 것은 Phase 1 과제로 남긴다.
값은 절대 출력하지 않는다. 경로와 줄 번호만 보고한다.
"""
import os, pathlib, re, sys

PATTERNS = [
    ("AWS Access Key",   re.compile(r'\b(?:AKIA|ASIA|AIDA|AROA)[0-9A-Z]{16}\b')),
    ("Private Key",      re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----')),
    ("OpenAI-style Key", re.compile(r'\bsk-[A-Za-z0-9_\-]{20,}\b')),
    ("Slack Token",      re.compile(r'\bxox[baprs]-[A-Za-z0-9-]{10,}\b')),
    ("GitHub PAT",       re.compile(r'\bgh[pousr]_[A-Za-z0-9]{30,}\b')),
    ("Google API Key",   re.compile(r'\bAIza[0-9A-Za-z_\-]{35}\b')),
    ("AWS Secret",       re.compile(r'aws_secret_access_key\s*[=:]\s*["\']?[A-Za-z0-9/+=]{40}')),
]
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".terraform"}
SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".xlsx", ".woff", ".woff2"}
# 이 스캐너 자신과 감사 문서는 패턴 문자열을 포함하므로 제외
SELF = {"scripts/scan_secrets.py", "SENSITIVE_DATA_FINDINGS.md",
        "migration/MIGRATION_PRE_AUDIT.ps1", "BUNDLE_AUDIT.md"}


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                        pathlib.Path(__file__).resolve().parent.parent).resolve()
    if not root.is_dir():
        print("::error::비밀정보 스캔 대상은 존재하는 디렉터리여야 합니다")
        return 2
    hits, scanned = [], 0
    for directory, child_directories, filenames in os.walk(root, topdown=True, followlinks=False):
        directory_path = pathlib.Path(directory)
        child_directories[:] = sorted(
            name
            for name in child_directories
            if name not in SKIP_DIRS and not (directory_path / name).is_symlink()
        )
        for filename in sorted(filenames):
            p = directory_path / filename
            if p.is_symlink() or p.suffix.lower() in SKIP_SUFFIX:
                continue
            rel = p.relative_to(root).as_posix()
            if rel in SELF:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="strict")
            except Exception:
                continue
            scanned += 1
            for i, line in enumerate(text.splitlines(), 1):
                for name, rx in PATTERNS:
                    if rx.search(line):
                        hits.append((rel, i, name))
    print(f"비밀정보 스캔 · 파일 {scanned}개 · 탐지 {len(hits)}건")
    for rel, i, name in hits:
        print(f"::error file={rel},line={i}::{name} 패턴 탐지 [값 미출력]")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
