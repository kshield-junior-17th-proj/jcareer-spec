#!/usr/bin/env python3
"""Bind three Windows endpoints to one reviewed AMI and immutable source bundle."""

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
    "decision",
    "image_build_ref",
    "reviewer_ref",
    "reviewed_at",
    "expires_at",
    "ami_id",
    "image_source_sha256",
    "build_observation_sha256",
    "synthetic_data_only",
    "notes",
}
SOURCE_PATHS = (
    "fleet/images/endpoint_image_contract.yaml",
    "fleet/images/windows/build-component.yaml",
    "fleet/images/windows/test-component.yaml",
    "fleet/images/windows/Configure-JCareerSession.ps1",
    "fleet/images/windows/Remove-JCareerSession.ps1",
)
OBSERVATION_KEYS = {
    "schema_version",
    "observation_state",
    "approval_ref",
    "image_build_ref",
    "pipeline_arn_sha256",
    "pipeline_configuration_sha256",
    "image_build_arn_sha256",
    "definition_apply_receipt_sha256",
    "image_source_sha256",
    "client_token_sha256",
    "region",
    "ami_id",
    "ami_count",
    "snapshot_count",
    "ami_private",
    "storage_encrypted",
    "lineage_tags_verified",
    "image_tests_enabled",
    "residual_build_instance_count",
    "ami_launch_permission_count",
    "snapshot_create_volume_permission_count",
    "sharing_permissions_verified",
    "observed_at",
    "synthetic_data_only",
    "human_release_recorded",
    "raw_arn_or_account_included",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
AMI_ID = re.compile(r"^ami-[0-9a-f]{8,17}$")
IMAGE_REF = re.compile(r"^IMAGE-[A-Z0-9_-]{8,64}$")
REVIEWER_REF = re.compile(r"^reviewer:[a-z0-9_-]{6,64}$")


def parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None


def source_bundle_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for relative in SOURCE_PATHS:
        data = (root / relative).read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
    return digest.hexdigest()


def _walk_modules(module: object):
    if not isinstance(module, dict):
        return
    for resource in module.get("resources", []) or []:
        if isinstance(resource, dict):
            yield resource
    for child in module.get("child_modules", []) or []:
        yield from _walk_modules(child)


def planned_endpoint_binding(plan: object) -> tuple[set[str], set[str]]:
    if not isinstance(plan, dict):
        return set(), set()
    root = ((plan.get("planned_values") or {}).get("root_module") or {})
    amis: set[str] = set()
    refs: set[str] = set()
    for resource in _walk_modules(root):
        if not str(resource.get("address", "")).startswith("aws_instance.windows["):
            continue
        values = resource.get("values")
        if not isinstance(values, dict):
            continue
        if isinstance(values.get("ami"), str):
            amis.add(values["ami"])
        tags = values.get("tags")
        if isinstance(tags, dict) and isinstance(tags.get("jk_image_build_ref"), str):
            refs.add(tags["jk_image_build_ref"])
    return amis, refs


def audit_receipt(
    payload: object,
    *,
    root: Path,
    plan: object | None,
    build_observation: object | None,
    build_observation_sha256: str | None,
    require_approved: bool,
    now: datetime,
) -> list[str]:
    if not isinstance(payload, dict):
        return ["image receipt must be an object"]
    errors: list[str] = []
    if set(payload) != EXPECTED_KEYS:
        errors.append("image receipt keys differ from the exact v2 schema")
    if payload.get("schema_version") != "jcareer-windows-image-receipt-v2":
        errors.append("image receipt schema version is invalid")
    serialized = json.dumps(payload, ensure_ascii=False)
    for pattern, label in (
        (r"(?<!\d)\d{12}(?!\d)", "account identifier"),
        (r"arn:aws", "AWS ARN"),
        (r"(?:AKIA|ASIA)[A-Z0-9]{16}", "access key"),
        (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "email address"),
    ):
        if re.search(pattern, serialized, re.IGNORECASE):
            errors.append(f"image receipt contains a prohibited {label}")
    if payload.get("decision") == "PENDING_HUMAN_IMAGE_REVIEW" and not require_approved:
        if any(
            payload.get(key)
            for key in (
                "image_build_ref",
                "reviewer_ref",
                "reviewed_at",
                "expires_at",
                "ami_id",
                "image_source_sha256",
                "build_observation_sha256",
            )
        ):
            errors.append("pending image example must not contain release bindings")
        return errors
    if payload.get("decision") != "APPROVED_FOR_SYNTHETIC_ENDPOINT_DEMO":
        errors.append("the image has not been human-approved for the endpoint demo")
        return errors
    image_ref = payload.get("image_build_ref")
    reviewer_ref = payload.get("reviewer_ref")
    ami_id = payload.get("ami_id")
    source_hash = payload.get("image_source_sha256")
    if not isinstance(image_ref, str) or not IMAGE_REF.fullmatch(image_ref):
        errors.append("image_build_ref is invalid")
    if not isinstance(reviewer_ref, str) or not REVIEWER_REF.fullmatch(reviewer_ref):
        errors.append("reviewer_ref is invalid")
    if not isinstance(ami_id, str) or not AMI_ID.fullmatch(ami_id):
        errors.append("AMI identifier is invalid")
    if not isinstance(source_hash, str) or not SHA256.fullmatch(source_hash):
        errors.append("image source SHA-256 is invalid")
    else:
        try:
            current_source_hash = source_bundle_sha256(root)
        except OSError:
            errors.append("image source bundle is incomplete")
        else:
            if not hmac.compare_digest(source_hash, current_source_hash):
                errors.append("image receipt does not match the current image source bundle")
    reviewed_at = parse_time(payload.get("reviewed_at"))
    expires_at = parse_time(payload.get("expires_at"))
    if reviewed_at is None or expires_at is None:
        errors.append("image review timestamps must be timezone-aware ISO-8601 values")
    elif not (reviewed_at <= now < expires_at):
        errors.append("image review is not currently within its validity window")
    elif expires_at - reviewed_at > timedelta(days=30):
        errors.append("image review validity must not exceed 30 days")
    if payload.get("synthetic_data_only") is not True:
        errors.append("image receipt must retain the synthetic-data-only boundary")
    recorded_observation_hash = payload.get("build_observation_sha256")
    if not isinstance(recorded_observation_hash, str) or not SHA256.fullmatch(recorded_observation_hash):
        errors.append("build observation SHA-256 is missing or invalid")
    elif build_observation_sha256 is None or not hmac.compare_digest(
        recorded_observation_hash, build_observation_sha256
    ):
        errors.append("image receipt does not bind the supplied build observation")
    if not isinstance(build_observation, dict):
        errors.append("a build observation is required")
    else:
        if set(build_observation) != OBSERVATION_KEYS:
            errors.append("build observation keys differ from the exact v1 schema")
        observation_text = json.dumps(build_observation, ensure_ascii=False)
        if re.search(r"(?<!\d)\d{12}(?!\d)|arn:aws|(?:AKIA|ASIA)[A-Z0-9]{16}", observation_text, re.IGNORECASE):
            errors.append("build observation contains a prohibited raw identifier")
        observation_checks = {
            "schema_version": "jcareer-windows-image-build-observation-v1",
            "observation_state": "AVAILABLE_PENDING_HUMAN_REVIEW",
            "image_build_ref": image_ref,
            "image_source_sha256": source_hash,
            "region": "ap-northeast-2",
            "ami_id": ami_id,
            "ami_count": 1,
            "ami_private": True,
            "storage_encrypted": True,
            "lineage_tags_verified": True,
            "image_tests_enabled": True,
            "residual_build_instance_count": 0,
            "ami_launch_permission_count": 0,
            "snapshot_create_volume_permission_count": 0,
            "sharing_permissions_verified": True,
            "synthetic_data_only": True,
            "human_release_recorded": False,
            "raw_arn_or_account_included": False,
        }
        for key, expected in observation_checks.items():
            if build_observation.get(key) != expected:
                errors.append(f"build observation field does not match release boundary: {key}")
    if plan is None:
        errors.append("an endpoint saved-plan JSON document is required")
    else:
        amis, refs = planned_endpoint_binding(plan)
        if amis != {ami_id}:
            errors.append("endpoint plan AMI does not match the reviewed image receipt")
        if refs != {image_ref}:
            errors.append("endpoint plan image reference does not match the reviewed receipt")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--plan-json")
    parser.add_argument("--build-observation")
    parser.add_argument("--require-approved", action="store_true")
    parser.add_argument("--now")
    args = parser.parse_args()
    try:
        root = Path(args.root).resolve()
        payload = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
        plan = (
            json.loads(Path(args.plan_json).read_text(encoding="utf-8"))
            if args.plan_json
            else None
        )
        build_observation = (
            json.loads(Path(args.build_observation).read_text(encoding="utf-8-sig"))
            if args.build_observation
            else None
        )
        build_observation_hash = (
            hashlib.sha256(Path(args.build_observation).read_bytes()).hexdigest()
            if args.build_observation
            else None
        )
        now = parse_time(args.now) if args.now else datetime.now(timezone.utc)
        if now is None:
            raise ValueError("--now must be timezone-aware")
        errors = audit_receipt(
            payload,
            root=root,
            plan=plan,
            build_observation=build_observation,
            build_observation_sha256=build_observation_hash,
            require_approved=args.require_approved,
            now=now,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"image receipt check failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    for error in errors:
        print(f"image receipt check failed: {error}", file=sys.stderr)
    if not errors:
        print("Windows image receipt contract: PASS (review consumed, not made)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
