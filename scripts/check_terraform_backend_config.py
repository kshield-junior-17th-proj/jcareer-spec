#!/usr/bin/env python3
"""Fail closed unless a deployment uses the reviewed S3 state/lock shape."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


EXPECTED_KEYS = {
    "serverless-opendart": "jcareer/asis-lab/serverless-opendart/terraform.tfstate",
    "workplace-images": "jcareer/asis-lab/workplace-images/terraform.tfstate",
    "workplace-endpoints": "jcareer/asis-lab/workplace-endpoints/terraform.tfstate",
}
ALLOWED_FIELDS = {"bucket", "key", "region", "encrypt", "use_lockfile"}
ASSIGNMENT = re.compile(r'^([a-z_]+)\s*=\s*(?:"([^"]*)"|(true|false))\s*$')
BUCKET = re.compile(r"^(?!\d+\.\d+\.\d+\.\d+$)[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
FORBIDDEN = re.compile(
    r"(?i)(access_key|secret_key|session_token|token|password|credential|"
    r"sse_customer_key|role_arn|arn:aws|(?:AKIA|ASIA)[A-Z0-9]{16})"
)


def parse_config(source: str) -> tuple[dict[str, str | bool], list[str]]:
    values: dict[str, str | bool] = {}
    errors: list[str] = []
    if FORBIDDEN.search(source):
        errors.append("backend config contains a credential or disallowed identity field")
    for number, raw in enumerate(source.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = ASSIGNMENT.fullmatch(line)
        if match is None:
            errors.append(f"backend config line {number} is not a simple assignment")
            continue
        key, quoted, boolean = match.groups()
        if key in values:
            errors.append(f"backend config field {key} is duplicated")
            continue
        values[key] = quoted if quoted is not None else boolean == "true"
    return values, errors


def audit_backend_config(source: str, root: str) -> list[str]:
    if root not in EXPECTED_KEYS:
        return ["Terraform root is not allowlisted for remote state"]
    values, errors = parse_config(source)
    if set(values) != ALLOWED_FIELDS:
        errors.append("backend config must contain only bucket/key/region/encrypt/use_lockfile")
    bucket = values.get("bucket")
    if not isinstance(bucket, str) or not BUCKET.fullmatch(bucket):
        errors.append("backend bucket name is missing or invalid")
    if values.get("key") != EXPECTED_KEYS[root]:
        errors.append("backend state key does not match the selected Terraform root")
    if values.get("region") != "ap-northeast-2":
        errors.append("backend Region must be ap-northeast-2")
    if values.get("encrypt") is not True:
        errors.append("backend encryption must be enabled")
    if values.get("use_lockfile") is not True:
        errors.append("S3 state locking must be enabled")
    return errors


def canonical_backend_sha256(source: str, root: str) -> str:
    """Hash one validated logical backend independent of formatting/comments."""
    errors = audit_backend_config(source, root)
    if errors:
        raise ValueError("backend config is not valid for canonical hashing")
    values, parse_errors = parse_config(source)
    if parse_errors:
        raise ValueError("backend config could not be parsed for canonical hashing")
    payload = {"root": root, **values}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--terraform-root", required=True, choices=sorted(EXPECTED_KEYS))
    parser.add_argument("--print-canonical-sha256", action="store_true")
    args = parser.parse_args()
    try:
        source = Path(args.config).read_text(encoding="utf-8")
        errors = audit_backend_config(source, args.terraform_root)
    except OSError as exc:
        print(f"backend config check failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    for error in errors:
        print(f"backend config check failed: {error}", file=sys.stderr)
    if not errors and args.print_canonical_sha256:
        print(canonical_backend_sha256(source, args.terraform_root))
    elif not errors:
        print("Terraform remote backend contract: PASS (S3 encryption and lockfile enabled)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
