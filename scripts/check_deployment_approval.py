#!/usr/bin/env python3
"""Validate a human deployment record without making the approval decision."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


EXPECTED_KEYS = {
    "schema_version",
    "scope",
    "decision",
    "approval_ref",
    "reviewer_ref",
    "approved_at",
    "expires_at",
    "saved_plan_sha256",
    "backend_config_sha256",
    "provider_account_sha256",
    "lambda_image_sha256",
    "notes",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
PLACEHOLDER_SHA256 = re.compile(r"^([0-9a-f])\1{63}$")
HASH_FIELDS = {
    "saved_plan_sha256",
    "backend_config_sha256",
    "provider_account_sha256",
    "lambda_image_sha256",
}
APPROVAL_REF = re.compile(r"^APPROVAL-[A-Z0-9_-]{8,64}$")
REVIEWER_REF = re.compile(r"^reviewer:[a-z0-9_-]{6,64}$")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _walk_modules(module: object):
    if not isinstance(module, dict):
        return
    for resource in module.get("resources", []) or []:
        if isinstance(resource, dict):
            yield resource
    for child in module.get("child_modules", []) or []:
        yield from _walk_modules(child)


def planned_lambda_image_sha256(plan: object) -> str | None:
    if not isinstance(plan, dict):
        return None
    root = ((plan.get("planned_values") or {}).get("root_module") or {})
    matches = [
        resource
        for resource in _walk_modules(root)
        if resource.get("address") == "aws_lambda_function.worker[0]"
    ]
    if len(matches) != 1:
        return None
    values = matches[0].get("values")
    image_uri = values.get("image_uri") if isinstance(values, dict) else None
    if not isinstance(image_uri, str):
        return None
    match = re.search(r"@sha256:([0-9a-f]{64})$", image_uri)
    return match.group(1) if match else None


def planned_deployment_stage(plan: object) -> str | None:
    if not isinstance(plan, dict):
        return None
    outputs = ((plan.get("planned_values") or {}).get("outputs") or {})
    stage = outputs.get("deployment_stage") if isinstance(outputs, dict) else None
    value = stage.get("value") if isinstance(stage, dict) else None
    return value if isinstance(value, str) else None


def parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def audit_approval(
    payload: object,
    *,
    scope: str,
    require_approved: bool,
    now: datetime,
    plan_sha256: str | None = None,
    backend_config_sha256: str | None = None,
    provider_account_sha256: str | None = None,
    artifact_sha256: str | None = None,
    planned_artifact_sha256: str | None = None,
    deployment_stage: str | None = None,
) -> list[str]:
    if not isinstance(payload, dict):
        return ["approval record must be an object"]
    errors: list[str] = []
    if set(payload) != EXPECTED_KEYS:
        errors.append("approval record keys differ from the exact v3 schema")
    if payload.get("schema_version") != "jcareer-deployment-approval-v3":
        errors.append("approval schema version is invalid")
    if payload.get("scope") != scope:
        errors.append("approval scope does not match the requested deployment")
    # Digest text can legitimately contain twelve consecutive decimal characters.
    # Exclude hash-only fields from raw-identifier scanning; their dedicated strict
    # SHA-256 validation below still rejects raw account identifiers in those slots.
    text = json.dumps(
        {key: value for key, value in payload.items() if key not in HASH_FIELDS},
        ensure_ascii=False,
    )
    for pattern, label in (
        (r"(?<!\d)\d{12}(?!\d)", "account identifier"),
        (r"arn:aws", "AWS ARN"),
        (r"(?:AKIA|ASIA)[A-Z0-9]{16}", "access key"),
        (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "email address"),
    ):
        if re.search(pattern, text, re.IGNORECASE):
            errors.append(f"approval record contains a prohibited {label}")

    decision = payload.get("decision")
    if decision == "PENDING_HUMAN_DECISION" and not require_approved:
        if any(
            payload.get(key)
            for key in (
                "approval_ref",
                "reviewer_ref",
                "approved_at",
                "expires_at",
                "saved_plan_sha256",
                "backend_config_sha256",
                "provider_account_sha256",
                "lambda_image_sha256",
            )
        ):
            errors.append("pending example must not contain approval bindings")
        return errors
    if decision != "APPROVED_FOR_EXACT_PLAN":
        errors.append("a human has not approved this exact saved plan")
        return errors

    approval_ref = payload.get("approval_ref")
    reviewer_ref = payload.get("reviewer_ref")
    if not isinstance(approval_ref, str) or not APPROVAL_REF.fullmatch(approval_ref):
        errors.append("approval_ref is not a pseudonymous approval reference")
    if not isinstance(reviewer_ref, str) or not REVIEWER_REF.fullmatch(reviewer_ref):
        errors.append("reviewer_ref is not a pseudonymous reviewer reference")
    approved_at = parse_time(payload.get("approved_at"))
    expires_at = parse_time(payload.get("expires_at"))
    if approved_at is None or expires_at is None:
        errors.append("approval timestamps must be timezone-aware ISO-8601 values")
    elif not (approved_at <= now < expires_at):
        errors.append("approval is not currently within its validity window")
    elif expires_at - approved_at > timedelta(hours=24):
        errors.append("approval validity must not exceed 24 hours")

    recorded_plan = payload.get("saved_plan_sha256")
    if not isinstance(recorded_plan, str) or not SHA256.fullmatch(recorded_plan):
        errors.append("saved plan SHA-256 is missing or invalid")
    elif plan_sha256 is None or not hmac.compare_digest(recorded_plan, plan_sha256):
        errors.append("approval is not bound to the supplied saved plan")
    recorded_backend = payload.get("backend_config_sha256")
    if not isinstance(recorded_backend, str) or not SHA256.fullmatch(recorded_backend):
        errors.append("backend configuration SHA-256 is missing or invalid")
    elif backend_config_sha256 is None or not hmac.compare_digest(
        recorded_backend, backend_config_sha256
    ):
        errors.append("approval is not bound to the supplied backend configuration")
    recorded_provider_account = payload.get("provider_account_sha256")
    if (
        not isinstance(recorded_provider_account, str)
        or not SHA256.fullmatch(recorded_provider_account)
        or PLACEHOLDER_SHA256.fullmatch(recorded_provider_account)
    ):
        errors.append("provider account SHA-256 is missing, invalid, or placeholder-like")
    elif (
        not isinstance(provider_account_sha256, str)
        or not SHA256.fullmatch(provider_account_sha256)
        or PLACEHOLDER_SHA256.fullmatch(provider_account_sha256)
        or not hmac.compare_digest(recorded_provider_account, provider_account_sha256)
    ):
        errors.append("approval is not bound to the supplied provider account digest")
    recorded_artifact = payload.get("lambda_image_sha256")
    if scope == "serverless-opendart" and deployment_stage == "runtime":
        if not isinstance(recorded_artifact, str) or not SHA256.fullmatch(recorded_artifact):
            errors.append("Lambda image SHA-256 is missing or invalid")
        elif artifact_sha256 is None or not hmac.compare_digest(
            recorded_artifact, artifact_sha256
        ):
            errors.append("approval is not bound to the supplied Lambda image digest")
        elif planned_artifact_sha256 is None or not hmac.compare_digest(
            recorded_artifact, planned_artifact_sha256
        ):
            errors.append("approval Lambda digest does not match the saved plan image URI")
    elif scope == "serverless-opendart" and deployment_stage == "bootstrap":
        if recorded_artifact not in {"", None} or artifact_sha256 not in {"", None}:
            errors.append("bootstrap approval must not carry a Lambda image digest")
    elif scope == "serverless-opendart":
        errors.append("serverless approval requires a bootstrap or runtime saved plan")
    elif recorded_artifact not in {"", None}:
        errors.append("non-Lambda approval must leave lambda_image_sha256 empty")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approval", required=True)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--plan")
    parser.add_argument("--plan-json")
    parser.add_argument("--backend-config-sha256")
    parser.add_argument("--provider-account-sha256")
    parser.add_argument("--artifact-sha256")
    parser.add_argument("--require-approved", action="store_true")
    parser.add_argument("--now")
    args = parser.parse_args()
    try:
        payload = json.loads(Path(args.approval).read_text(encoding="utf-8"))
        now = parse_time(args.now) if args.now else datetime.now(timezone.utc)
        if now is None:
            raise ValueError("--now must be a timezone-aware ISO-8601 value")
        plan_hash = file_sha256(Path(args.plan)) if args.plan else None
        planned_artifact_hash = None
        deployment_stage = None
        if args.scope == "serverless-opendart":
            if not args.plan_json:
                raise ValueError("serverless-opendart requires --plan-json")
            plan_document = json.loads(Path(args.plan_json).read_text(encoding="utf-8"))
            deployment_stage = planned_deployment_stage(plan_document)
            planned_artifact_hash = planned_lambda_image_sha256(plan_document)
        errors = audit_approval(
            payload,
            scope=args.scope,
            require_approved=args.require_approved,
            now=now,
            plan_sha256=plan_hash,
            backend_config_sha256=args.backend_config_sha256,
            provider_account_sha256=args.provider_account_sha256,
            artifact_sha256=args.artifact_sha256,
            planned_artifact_sha256=planned_artifact_hash,
            deployment_stage=deployment_stage,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"approval check failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    for error in errors:
        print(f"approval check failed: {error}", file=sys.stderr)
    if not errors:
        print("deployment approval record contract: PASS (human decision consumed, not made)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
