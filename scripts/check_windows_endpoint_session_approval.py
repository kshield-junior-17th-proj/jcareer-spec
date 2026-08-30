#!/usr/bin/env python3
"""Validate a human approval for three short-lived Windows consultant sessions."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit


SHA256 = re.compile(r"^[0-9a-f]{64}$")
APPROVAL_REF = re.compile(r"^APPROVAL-[A-Z0-9_-]{8,64}$")
REVIEWER_REF = re.compile(r"^reviewer:[a-z0-9_-]{6,64}$")
SESSION_REF = re.compile(r"^SESSION-[A-Z0-9_-]{8,64}$")
KEYS = {
    "schema_version",
    "scope",
    "decision",
    "approval_ref",
    "reviewer_ref",
    "approved_at",
    "expires_at",
    "session_expires_at",
    "endpoint_backend_config_sha256",
    "endpoint_apply_receipt_sha256",
    "image_receipt_sha256",
    "build_observation_sha256",
    "preview_url_sha256",
    "preview_bootstrap_token_sha256",
    "configure_script_sha256",
    "remove_script_sha256",
    "access_mode",
    "bootstrap_delivery_method",
    "credential_method",
    "max_sessions",
    "sessions",
    "synthetic_data_only",
    "notes",
}
SESSION_KEYS = {"endpoint_ref", "session_ref", "local_port"}
ENDPOINT_APPLY_RECEIPT_KEYS = {
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
ENDPOINT_APPLY_PROTECTED_INPUT_SNAPSHOT_COUNT = 10


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None


def _bind_hash(
    errors: list[str], payload: dict[str, object], key: str, actual: str
) -> None:
    recorded = payload.get(key)
    if not isinstance(recorded, str) or not SHA256.fullmatch(recorded):
        errors.append(f"{key} is missing or invalid")
    elif not hmac.compare_digest(recorded, actual):
        errors.append(f"{key} does not match the supplied input")


def _endpoint_apply_receipt_errors(
    payload: object,
    *,
    endpoint_backend_hash: str,
    build_observation_hash: str,
) -> list[str]:
    if not isinstance(payload, dict):
        return ["endpoint apply receipt must be an object"]
    errors: list[str] = []
    if set(payload) != ENDPOINT_APPLY_RECEIPT_KEYS:
        errors.append("endpoint apply receipt keys differ from the exact schema")
    if payload.get("schema_version") != "jcareer-redacted-terraform-apply-receipt-v1":
        errors.append("endpoint apply receipt schema is invalid")
    if payload.get("scope") != "workplace-windows-endpoints":
        errors.append("endpoint apply receipt scope is invalid")
    if payload.get("result") != "APPLY_COMMAND_COMPLETED":
        errors.append("endpoint apply receipt does not record a completed apply command")
    if payload.get("resource_identifiers_included") is not False:
        errors.append("endpoint apply receipt must remain redacted")
    if payload.get("runtime_smoke_completed") is not False:
        errors.append("endpoint apply receipt must not claim a runtime smoke test")
    if payload.get("artifact_sha256") is not None:
        errors.append("endpoint apply receipt must not carry a Lambda artifact digest")
    if (
        payload.get("protected_input_snapshot_count")
        != ENDPOINT_APPLY_PROTECTED_INPUT_SNAPSHOT_COUNT
    ):
        errors.append("endpoint apply receipt protected input snapshot count is invalid")
    if payload.get("local_snapshot_cleanup_observed") is not True:
        errors.append("endpoint apply receipt does not confirm protected input cleanup")
    approval_ref = payload.get("approval_ref")
    if not isinstance(approval_ref, str) or not APPROVAL_REF.fullmatch(approval_ref):
        errors.append("endpoint apply receipt approval_ref is invalid")
    saved_plan_hash = payload.get("saved_plan_sha256")
    if not isinstance(saved_plan_hash, str) or not SHA256.fullmatch(saved_plan_hash):
        errors.append("endpoint apply receipt saved plan digest is invalid")
    recorded_backend_hash = payload.get("backend_config_sha256")
    if (
        not isinstance(recorded_backend_hash, str)
        or not SHA256.fullmatch(recorded_backend_hash)
        or not SHA256.fullmatch(endpoint_backend_hash)
        or not hmac.compare_digest(recorded_backend_hash, endpoint_backend_hash)
    ):
        errors.append("endpoint apply receipt backend binding is invalid")
    recorded_observation_hash = payload.get("build_observation_sha256")
    if (
        not isinstance(recorded_observation_hash, str)
        or not SHA256.fullmatch(recorded_observation_hash)
        or not SHA256.fullmatch(build_observation_hash)
        or not hmac.compare_digest(recorded_observation_hash, build_observation_hash)
    ):
        errors.append("endpoint apply receipt build observation binding is invalid")
    if parse_time(payload.get("completed_at")) is None:
        errors.append("endpoint apply receipt completion time must be timezone-aware")
    return errors


def audit_approval(
    payload: object,
    *,
    now: datetime,
    endpoint_backend_hash: str,
    endpoint_apply_receipt: object,
    endpoint_apply_receipt_hash: str,
    image_receipt: object,
    image_receipt_hash: str,
    build_observation: object,
    build_observation_hash: str,
    preview_url: str,
    preview_bootstrap_token_hash: str,
    configure_script_hash: str,
    remove_script_hash: str,
    require_approved: bool,
) -> list[str]:
    if not isinstance(payload, dict):
        return ["session approval must be an object"]
    errors: list[str] = []
    if set(payload) != KEYS:
        errors.append("session approval keys differ from the exact schema")
    if payload.get("schema_version") != "jcareer-windows-endpoint-session-approval-v1":
        errors.append("session approval schema is invalid")
    if payload.get("scope") != "workplace-windows-consultant-session":
        errors.append("session approval scope is invalid")
    serialized = json.dumps(payload, ensure_ascii=False)
    for pattern, label in (
        (r"(?<!\d)\d{12}(?!\d)", "account identifier"),
        (r"arn:aws", "AWS ARN"),
        (r"(?:AKIA|ASIA)[A-Z0-9]{16}", "access key"),
        (r"https://", "raw preview URL"),
    ):
        if re.search(pattern, serialized, re.IGNORECASE):
            errors.append(f"session approval contains a prohibited {label}")

    if payload.get("decision") == "PENDING_HUMAN_DECISION" and not require_approved:
        bound_keys = KEYS - {
            "schema_version",
            "scope",
            "decision",
            "access_mode",
            "bootstrap_delivery_method",
            "credential_method",
            "max_sessions",
            "sessions",
            "synthetic_data_only",
            "notes",
        }
        if any(payload.get(key) for key in bound_keys) or payload.get("sessions"):
            errors.append("pending session example must not contain operation bindings")
        return errors
    if payload.get("decision") != "APPROVED_FOR_THREE_WINDOWS_CONSULTANT_SESSIONS":
        errors.append("a human has not approved the three consultant sessions")
        return errors
    if not isinstance(payload.get("approval_ref"), str) or not APPROVAL_REF.fullmatch(payload["approval_ref"]):
        errors.append("approval_ref is invalid")
    if not isinstance(payload.get("reviewer_ref"), str) or not REVIEWER_REF.fullmatch(payload["reviewer_ref"]):
        errors.append("reviewer_ref is invalid")

    approved_at = parse_time(payload.get("approved_at"))
    expires_at = parse_time(payload.get("expires_at"))
    session_expires_at = parse_time(payload.get("session_expires_at"))
    if approved_at is None or expires_at is None or session_expires_at is None:
        errors.append("approval and session timestamps must be timezone-aware")
    elif not (approved_at <= now < session_expires_at <= expires_at):
        errors.append("session timing is outside the approval window")
    elif expires_at - approved_at > timedelta(hours=24):
        errors.append("session approval validity must not exceed 24 hours")
    elif session_expires_at - now > timedelta(hours=8):
        errors.append("consultant session must expire within eight hours")

    for key, actual in (
        ("endpoint_backend_config_sha256", endpoint_backend_hash),
        ("endpoint_apply_receipt_sha256", endpoint_apply_receipt_hash),
        ("image_receipt_sha256", image_receipt_hash),
        ("build_observation_sha256", build_observation_hash),
        ("preview_url_sha256", text_sha256(preview_url)),
        ("preview_bootstrap_token_sha256", preview_bootstrap_token_hash),
        ("configure_script_sha256", configure_script_hash),
        ("remove_script_sha256", remove_script_hash),
    ):
        _bind_hash(errors, payload, key, actual)

    errors.extend(
        _endpoint_apply_receipt_errors(
            endpoint_apply_receipt,
            endpoint_backend_hash=endpoint_backend_hash,
            build_observation_hash=build_observation_hash,
        )
    )
    if not isinstance(image_receipt, dict) or (
        image_receipt.get("schema_version") != "jcareer-windows-image-receipt-v2"
        or image_receipt.get("decision") != "APPROVED_FOR_SYNTHETIC_ENDPOINT_DEMO"
        or image_receipt.get("synthetic_data_only") is not True
        or image_receipt.get("build_observation_sha256") != build_observation_hash
    ):
        errors.append("image release receipt content is invalid")
    if not isinstance(build_observation, dict) or (
        build_observation.get("schema_version")
        != "jcareer-windows-image-build-observation-v1"
        or build_observation.get("observation_state")
        != "AVAILABLE_PENDING_HUMAN_REVIEW"
        or build_observation.get("image_build_ref")
        != (image_receipt.get("image_build_ref") if isinstance(image_receipt, dict) else None)
        or build_observation.get("ami_id")
        != (image_receipt.get("ami_id") if isinstance(image_receipt, dict) else None)
        or build_observation.get("human_release_recorded") is not False
        or build_observation.get("raw_arn_or_account_included") is not False
    ):
        errors.append("build observation content is invalid")

    try:
        parsed_preview = urlsplit(preview_url)
    except ValueError:
        parsed_preview = None
    if (
        parsed_preview is None
        or parsed_preview.scheme != "https"
        or not parsed_preview.hostname
        or parsed_preview.username
        or parsed_preview.password
        or parsed_preview.path != "/jobs"
        or parsed_preview.query
        or parsed_preview.fragment
    ):
        errors.append("preview URL must be credential-free HTTPS at the approved /jobs path")

    if payload.get("access_mode") != "SSM_TUNNELED_RDP":
        errors.append("session access mode must remain SSM-tunneled RDP")
    if payload.get("bootstrap_delivery_method") != "RDP_CLIPBOARD_ONE_TIME":
        errors.append("preview bootstrap must use the one-time RDP clipboard method")
    if payload.get("credential_method") != "OPERATOR_HELD_EC2_WINDOWS_PASSWORD":
        errors.append("credential method is outside the reviewed demo boundary")
    if payload.get("max_sessions") != 3:
        errors.append("approval must authorize exactly three sessions")
    sessions = payload.get("sessions")
    if not isinstance(sessions, list) or len(sessions) != 3:
        errors.append("approval must contain exactly three session bindings")
    else:
        endpoint_refs: set[str] = set()
        session_refs: set[str] = set()
        ports: set[int] = set()
        for row in sessions:
            if not isinstance(row, dict) or set(row) != SESSION_KEYS:
                errors.append("session binding keys differ from the exact schema")
                continue
            endpoint_ref = row.get("endpoint_ref")
            session_ref = row.get("session_ref")
            port = row.get("local_port")
            if endpoint_ref not in {"WIN-01", "WIN-02", "WIN-03"}:
                errors.append("session endpoint_ref is invalid")
            if not isinstance(session_ref, str) or not SESSION_REF.fullmatch(session_ref):
                errors.append("session_ref is invalid")
            if not isinstance(port, int) or port < 33901 or port > 33999:
                errors.append("session local port is outside the reviewed range")
            if isinstance(endpoint_ref, str):
                endpoint_refs.add(endpoint_ref)
            if isinstance(session_ref, str):
                session_refs.add(session_ref)
            if isinstance(port, int):
                ports.add(port)
        if endpoint_refs != {"WIN-01", "WIN-02", "WIN-03"}:
            errors.append("session approval does not bind all three endpoint refs")
        if len(session_refs) != 3 or len(ports) != 3:
            errors.append("session refs and local ports must be unique")
    if payload.get("synthetic_data_only") is not True:
        errors.append("session approval must retain the synthetic-only boundary")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approval", required=True)
    parser.add_argument("--endpoint-backend-config", required=True)
    parser.add_argument("--endpoint-apply-receipt", required=True)
    parser.add_argument("--image-receipt", required=True)
    parser.add_argument("--build-observation", required=True)
    parser.add_argument("--preview-url", required=True)
    parser.add_argument("--preview-bootstrap-token-sha256", required=True)
    parser.add_argument("--configure-script", required=True)
    parser.add_argument("--remove-script", required=True)
    parser.add_argument("--require-approved", action="store_true")
    parser.add_argument("--now")
    args = parser.parse_args()
    try:
        approval = json.loads(Path(args.approval).read_text(encoding="utf-8"))
        endpoint_receipt = json.loads(
            Path(args.endpoint_apply_receipt).read_text(encoding="utf-8-sig")
        )
        image_receipt = json.loads(
            Path(args.image_receipt).read_text(encoding="utf-8-sig")
        )
        observation = json.loads(
            Path(args.build_observation).read_text(encoding="utf-8-sig")
        )
        now = parse_time(args.now) if args.now else datetime.now(timezone.utc)
        if now is None:
            raise ValueError("--now must be timezone-aware")
        if not SHA256.fullmatch(args.preview_bootstrap_token_sha256):
            raise ValueError("--preview-bootstrap-token-sha256 must be lowercase SHA-256")
        errors = audit_approval(
            approval,
            now=now,
            endpoint_backend_hash=file_sha256(Path(args.endpoint_backend_config)),
            endpoint_apply_receipt=endpoint_receipt,
            endpoint_apply_receipt_hash=file_sha256(Path(args.endpoint_apply_receipt)),
            image_receipt=image_receipt,
            image_receipt_hash=file_sha256(Path(args.image_receipt)),
            build_observation=observation,
            build_observation_hash=file_sha256(Path(args.build_observation)),
            preview_url=args.preview_url,
            preview_bootstrap_token_hash=args.preview_bootstrap_token_sha256,
            configure_script_hash=file_sha256(Path(args.configure_script)),
            remove_script_hash=file_sha256(Path(args.remove_script)),
            require_approved=args.require_approved,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"endpoint session approval check failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    for error in errors:
        print(f"endpoint session approval check failed: {error}", file=sys.stderr)
    if not errors:
        print("Windows endpoint session approval: PASS (human decision consumed, not made)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
