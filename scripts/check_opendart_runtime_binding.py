#!/usr/bin/env python3
"""Validate the redacted receipt used to wire an existing OpenDART runtime.

This consumes evidence from a prior human-approved Terraform apply.  It does not
call AWS and it does not infer that the remote resources are currently usable;
the deployment wrapper separately checks the exact remote state and outputs.
"""

from __future__ import annotations

import argparse
import hmac
import json
import re
import sys
from datetime import datetime
from pathlib import Path


SHA256 = re.compile(r"^[0-9a-f]{64}$")
APPROVAL_REF = re.compile(r"^APPROVAL-[A-Z0-9_-]{8,64}$")
EXPECTED_KEYS = {
    "schema_version",
    "scope",
    "approval_ref",
    "saved_plan_sha256",
    "backend_config_sha256",
    "artifact_sha256",
    "build_observation_sha256",
    "completed_at",
    "result",
    "resource_identifiers_included",
    "runtime_smoke_completed",
    "protected_input_snapshot_count",
    "local_snapshot_cleanup_observed",
}
EXPECTED_PROTECTED_INPUT_SNAPSHOT_COUNT = 7


def audit_receipt(payload: object, *, backend_config_sha256: str) -> list[str]:
    if not isinstance(payload, dict):
        return ["OpenDART apply receipt must be an object"]
    errors: list[str] = []
    if set(payload) != EXPECTED_KEYS:
        errors.append("OpenDART apply receipt keys differ from the exact v1 schema")
    if payload.get("schema_version") != "jcareer-redacted-terraform-apply-receipt-v1":
        errors.append("OpenDART apply receipt schema is invalid")
    if payload.get("scope") != "serverless-opendart":
        errors.append("OpenDART apply receipt scope is invalid")
    if payload.get("result") != "APPLY_COMMAND_COMPLETED":
        errors.append("OpenDART apply receipt does not record a completed apply command")
    if payload.get("resource_identifiers_included") is not False:
        errors.append("OpenDART apply receipt must remain redacted")
    if payload.get("runtime_smoke_completed") is not False:
        errors.append("apply receipt must not impersonate a later runtime observation")
    if (
        payload.get("protected_input_snapshot_count")
        != EXPECTED_PROTECTED_INPUT_SNAPSHOT_COUNT
    ):
        errors.append("OpenDART apply receipt protected input snapshot count is invalid")
    if payload.get("local_snapshot_cleanup_observed") is not True:
        errors.append("OpenDART apply receipt does not confirm protected input cleanup")
    if payload.get("build_observation_sha256") is not None:
        errors.append("OpenDART apply receipt must not carry a Windows build observation")
    completed_at = payload.get("completed_at")
    try:
        completed_moment = datetime.fromisoformat(str(completed_at).replace("Z", "+00:00"))
    except ValueError:
        completed_moment = None
    if completed_moment is None or completed_moment.tzinfo is None:
        errors.append("OpenDART apply receipt completion time must be timezone-aware")
    if not isinstance(payload.get("approval_ref"), str) or not APPROVAL_REF.fullmatch(
        str(payload.get("approval_ref"))
    ):
        errors.append("OpenDART apply receipt lacks a pseudonymous approval reference")
    for key in ("saved_plan_sha256", "artifact_sha256"):
        value = payload.get(key)
        if not isinstance(value, str) or not SHA256.fullmatch(value):
            errors.append(f"OpenDART apply receipt {key} is invalid")
    recorded_backend = payload.get("backend_config_sha256")
    if not isinstance(recorded_backend, str) or not SHA256.fullmatch(recorded_backend):
        errors.append("OpenDART apply receipt backend binding is invalid")
    elif not SHA256.fullmatch(backend_config_sha256) or not hmac.compare_digest(
        recorded_backend, backend_config_sha256
    ):
        errors.append("OpenDART apply receipt is not bound to this backend configuration")
    rendered = json.dumps(payload, ensure_ascii=False)
    for pattern, label in (
        (r"(?<!\d)\d{12}(?!\d)", "AWS account identifier"),
        (r"arn:(?:aws|aws-us-gov|aws-cn):", "AWS ARN"),
        (r"(?:AKIA|ASIA)[A-Z0-9]{16}", "AWS access key"),
    ):
        if re.search(pattern, rendered, re.IGNORECASE):
            errors.append(f"OpenDART apply receipt contains a prohibited {label}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--backend-config-sha256", required=True)
    args = parser.parse_args()
    try:
        payload = json.loads(Path(args.receipt).read_text(encoding="utf-8-sig"))
        errors = audit_receipt(
            payload, backend_config_sha256=args.backend_config_sha256.lower()
        )
    except (OSError, json.JSONDecodeError) as exc:
        print(f"OpenDART runtime binding check failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    for error in errors:
        print(f"OpenDART runtime binding check failed: {error}", file=sys.stderr)
    if not errors:
        print("OpenDART runtime receipt/backend binding: PASS (AWS state not observed)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
