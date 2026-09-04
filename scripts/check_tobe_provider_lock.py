from __future__ import annotations

import argparse
import re
from pathlib import Path


LOCK_RELATIVE = Path("terraform/tobe-ai-security/.terraform.lock.hcl")
AWS_PROVIDER = "registry.terraform.io/hashicorp/aws"
EXPECTED_VERSION = "6.59.0"


def validate_lock(path: Path) -> list[str]:
    if not path.is_file():
        return [f"Terraform init did not produce {path}"]

    text = path.read_text(encoding="utf-8")
    match = re.search(
        rf'provider\s+"{re.escape(AWS_PROVIDER)}"\s*\{{(?P<body>.*?)\n\}}',
        text,
        re.S,
    )
    if not match:
        return [f"lock file does not contain {AWS_PROVIDER}"]

    body = match.group("body")
    problems: list[str] = []
    version = re.search(r'^\s*version\s*=\s*"([^"]+)"', body, re.M)
    if not version or version.group(1) != EXPECTED_VERSION:
        problems.append(f"AWS provider lock selection must equal {EXPECTED_VERSION}")
    if not re.search(r'^\s*hashes\s*=\s*\[\s*"(?:h1|zh):', body, re.M):
        problems.append("AWS provider lock selection must include a checksum")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    problems = validate_lock(args.root.resolve() / LOCK_RELATIVE)
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}")
        return 1
    print(f"TO-BE AWS provider lock selection PASS ({EXPECTED_VERSION})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
