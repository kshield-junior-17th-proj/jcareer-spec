#!/usr/bin/env python3
"""Validate human approvals for one Image Builder run or its artifact cleanup."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from check_windows_image_receipt import source_bundle_sha256


SHA256 = re.compile(r"^[0-9a-f]{64}$")
APPROVAL_REF = re.compile(r"^APPROVAL-[A-Z0-9_-]{8,64}$")
REVIEWER_REF = re.compile(r"^reviewer:[a-z0-9_-]{6,64}$")
IMAGE_REF = re.compile(r"^IMAGE-[A-Z0-9_-]{8,64}$")
AWS_REGION = re.compile(r"^[a-z]{2}(?:-gov)?-[a-z]+-[0-9]+$")
AMI_ID = re.compile(r"^ami-[0-9a-f]+$")
SNAPSHOT_ID = re.compile(r"^snap-[0-9a-f]+$")
BUILD_KEYS = {
    "schema_version",
    "scope",
    "decision",
    "approval_ref",
    "reviewer_ref",
    "approved_at",
    "expires_at",
    "backend_config_sha256",
    "definition_apply_receipt_sha256",
    "pipeline_arn_sha256",
    "pipeline_configuration_sha256",
    "image_source_sha256",
    "image_build_ref",
    "client_token_sha256",
    "expected_region",
    "expected_ami_count",
    "max_executions",
    "poll_deadline_at",
    "cancel_on_deadline",
    "cleanup_deadline_at",
    "synthetic_data_only",
    "notes",
}
CLEANUP_KEYS = {
    "schema_version",
    "scope",
    "decision",
    "approval_ref",
    "reviewer_ref",
    "approved_at",
    "expires_at",
    "backend_config_sha256",
    "build_observation_sha256",
    "secure_inventory_sha256",
    "image_build_ref",
    "expected_ami_count",
    "expected_snapshot_count",
    "include_amis",
    "include_snapshots",
    "endpoint_disposition_observation_sha256",
    "endpoint_teardown_receipt_sha256",
    "synthetic_data_only",
    "notes",
}
RECOVERY_KEYS = {
    "schema_version",
    "scope",
    "decision",
    "approval_ref",
    "reviewer_ref",
    "approved_at",
    "expires_at",
    "backend_config_sha256",
    "endpoint_backend_config_sha256",
    "build_observation_sha256",
    "secure_inventory_sha256",
    "endpoint_disposition_observation_sha256",
    "endpoint_teardown_receipt_sha256",
    "image_build_ref",
    "expected_ami_count",
    "expected_snapshot_count",
    "expected_live_image_state",
    "expected_scoped_residual_ami_count",
    "expected_scoped_residual_snapshot_count",
    "mutation_authorized",
    "lifecycle_success_assertion_authorized",
    "synthetic_data_only",
    "notes",
}
ENDPOINT_DISPOSITION_KEYS = {
    "schema_version",
    "scope",
    "observation_mode",
    "observed_at",
    "endpoint_backend_config_sha256",
    "image_build_ref",
    "ami_set_sha256",
    "endpoint_terraform_state_resource_count",
    "active_instance_count",
    "endpoint_teardown_receipt_sha256",
    "raw_identifiers_included",
    "whole_account_zero_claimed",
}
ENDPOINT_TEARDOWN_KEYS = {
    "schema_version",
    "scope",
    "approval_ref",
    "saved_plan_sha256",
    "backend_config_sha256",
    "completed_at",
    "result",
    "resource_identifiers_included",
    "post_teardown_inventory_observed",
    "protected_input_snapshot_count",
    "local_snapshot_cleanup_observed",
}
DEFINITION_APPLY_RECEIPT_KEYS = {
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
DEFINITION_APPLY_PROTECTED_INPUT_SNAPSHOT_COUNT = 7
ENDPOINT_TEARDOWN_PROTECTED_INPUT_SNAPSHOT_COUNT = 10


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None


def audit_definition_apply_receipt(
    payload: object, *, backend_hash: str | None
) -> list[str]:
    if not isinstance(payload, dict):
        return ["definition apply receipt must be an object"]
    errors: list[str] = []
    if set(payload) != DEFINITION_APPLY_RECEIPT_KEYS:
        errors.append("definition apply receipt keys differ from the exact schema")
    if payload.get("schema_version") != "jcareer-redacted-terraform-apply-receipt-v1":
        errors.append("definition apply receipt schema is invalid")
    if payload.get("scope") != "workplace-windows-image":
        errors.append("definition apply receipt scope is invalid")
    if payload.get("result") != "APPLY_COMMAND_COMPLETED":
        errors.append("definition apply receipt does not record a completed apply command")
    if payload.get("resource_identifiers_included") is not False:
        errors.append("definition apply receipt must remain redacted")
    if payload.get("runtime_smoke_completed") is not False:
        errors.append("definition apply receipt must not claim a runtime smoke test")
    if payload.get("artifact_sha256") is not None:
        errors.append("definition apply receipt must not carry a Lambda artifact digest")
    if payload.get("build_observation_sha256") is not None:
        errors.append("definition apply receipt must not carry a build observation digest")
    if (
        payload.get("protected_input_snapshot_count")
        != DEFINITION_APPLY_PROTECTED_INPUT_SNAPSHOT_COUNT
    ):
        errors.append("definition apply receipt protected input snapshot count is invalid")
    if payload.get("local_snapshot_cleanup_observed") is not True:
        errors.append("definition apply receipt does not confirm protected input cleanup")
    approval_ref = payload.get("approval_ref")
    if not isinstance(approval_ref, str) or not APPROVAL_REF.fullmatch(approval_ref):
        errors.append("definition apply receipt approval_ref is invalid")
    saved_plan_hash = payload.get("saved_plan_sha256")
    if not isinstance(saved_plan_hash, str) or not SHA256.fullmatch(saved_plan_hash):
        errors.append("definition apply receipt saved plan digest is invalid")
    recorded_backend_hash = payload.get("backend_config_sha256")
    if (
        not isinstance(recorded_backend_hash, str)
        or not SHA256.fullmatch(recorded_backend_hash)
        or not isinstance(backend_hash, str)
        or not SHA256.fullmatch(backend_hash)
        or not hmac.compare_digest(recorded_backend_hash, backend_hash)
    ):
        errors.append("definition apply receipt backend binding is invalid")
    if parse_time(payload.get("completed_at")) is None:
        errors.append("definition apply receipt completion time must be timezone-aware")
    return errors


def _base_errors(payload: object, keys: set[str], schema: str, scope: str) -> list[str]:
    if not isinstance(payload, dict):
        return ["approval record must be an object"]
    errors: list[str] = []
    if set(payload) != keys:
        errors.append("approval record keys differ from the exact schema")
    if payload.get("schema_version") != schema:
        errors.append("approval schema version is invalid")
    if payload.get("scope") != scope:
        errors.append("approval scope is invalid")
    serialized = json.dumps(payload, ensure_ascii=False)
    for pattern, label in (
        (r"(?<!\d)\d{12}(?!\d)", "account identifier"),
        (r"arn:aws", "AWS ARN"),
        (r"(?:AKIA|ASIA)[A-Z0-9]{16}", "access key"),
        (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "email address"),
    ):
        if re.search(pattern, serialized, re.IGNORECASE):
            errors.append(f"approval record contains a prohibited {label}")
    return errors


def _human_binding_errors(payload: dict[str, object], now: datetime) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload.get("approval_ref"), str) or not APPROVAL_REF.fullmatch(payload["approval_ref"]):
        errors.append("approval_ref is invalid")
    if not isinstance(payload.get("reviewer_ref"), str) or not REVIEWER_REF.fullmatch(payload["reviewer_ref"]):
        errors.append("reviewer_ref is invalid")
    approved_at = parse_time(payload.get("approved_at"))
    expires_at = parse_time(payload.get("expires_at"))
    if approved_at is None or expires_at is None:
        errors.append("approval timestamps must be timezone-aware")
    elif not (approved_at <= now < expires_at):
        errors.append("approval is outside its validity window")
    elif expires_at - approved_at > timedelta(hours=24):
        errors.append("approval validity must not exceed 24 hours")
    return errors


def _hash_binding(errors: list[str], payload: dict[str, object], key: str, actual: str | None) -> None:
    recorded = payload.get(key)
    if not isinstance(recorded, str) or not SHA256.fullmatch(recorded):
        errors.append(f"{key} is missing or invalid")
    elif actual is None or not hmac.compare_digest(recorded, actual):
        errors.append(f"{key} does not match the supplied artifact")


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _region_bound_ami_set_sha256(artifacts: object) -> str | None:
    if not isinstance(artifacts, list):
        return None
    normalized: list[str] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            return None
        region = artifact.get("region")
        ami_id = artifact.get("ami_id")
        if not isinstance(region, str) or not isinstance(ami_id, str):
            return None
        normalized.append(f"{region}:{ami_id}")
    return _text_sha256("\n".join(sorted(normalized)))


def _inventory_artifact_errors(inventory: dict[str, object]) -> list[str]:
    errors: list[str] = []
    artifacts = inventory.get("ami_artifacts")
    if inventory.get("inventory_complete") is not True:
        errors.append("secure inventory is not marked complete")
    if not isinstance(artifacts, list) or len(artifacts) > 8:
        return errors + ["secure inventory must contain 0..8 region-bound AMI artifacts"]

    flattened_amis: list[str] = []
    flattened_snapshots: list[str] = []
    region_bound_amis: list[str] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict) or set(artifact) != {"region", "ami_id", "snapshot_ids"}:
            errors.append("secure inventory AMI artifact keys are invalid")
            continue
        region = artifact.get("region")
        ami_id = artifact.get("ami_id")
        snapshot_ids = artifact.get("snapshot_ids")
        if not isinstance(region, str) or not AWS_REGION.fullmatch(region):
            errors.append("secure inventory artifact region is invalid")
        if not isinstance(ami_id, str) or not AMI_ID.fullmatch(ami_id):
            errors.append("secure inventory artifact AMI is invalid")
        else:
            flattened_amis.append(ami_id)
            if isinstance(region, str) and AWS_REGION.fullmatch(region):
                region_bound_amis.append(f"{region}:{ami_id}")
        if not isinstance(snapshot_ids, list) or not snapshot_ids:
            errors.append("secure inventory artifact must contain snapshots")
        elif any(not isinstance(value, str) or not SNAPSHOT_ID.fullmatch(value) for value in snapshot_ids):
            errors.append("secure inventory artifact snapshot is invalid")
        elif len(set(snapshot_ids)) != len(snapshot_ids):
            errors.append("secure inventory artifact contains duplicate snapshots")
        else:
            flattened_snapshots.extend(snapshot_ids)

    if len(set(region_bound_amis)) != len(region_bound_amis):
        errors.append("secure inventory contains duplicate region-bound AMIs")

    ami_ids = inventory.get("ami_ids")
    snapshot_ids = inventory.get("snapshot_ids")
    if (
        not isinstance(ami_ids, list)
        or any(not isinstance(value, str) or not AMI_ID.fullmatch(value) for value in ami_ids)
        or sorted(ami_ids) != sorted(flattened_amis)
    ):
        errors.append("secure inventory flattened AMI set differs from its artifacts")
    if (
        not isinstance(snapshot_ids, list)
        or any(not isinstance(value, str) or not SNAPSHOT_ID.fullmatch(value) for value in snapshot_ids)
        or sorted(snapshot_ids) != sorted(flattened_snapshots)
    ):
        errors.append("secure inventory flattened snapshot set differs from its artifacts")
    return errors


def audit_cleanup_artifact_binding(
    observation: object, inventory: object
) -> list[str]:
    """Prove that the redacted observation and private inventory describe one build."""
    if not isinstance(observation, dict) or not isinstance(inventory, dict):
        return ["build observation and secure inventory must be objects"]
    errors: list[str] = []
    if observation.get("schema_version") != "jcareer-windows-image-build-observation-v1":
        errors.append("build observation schema is invalid")
    if inventory.get("schema_version") != "jcareer-windows-image-private-inventory-v2":
        errors.append("secure inventory schema is invalid")
    observation_state = observation.get("observation_state")
    if observation_state not in {
        "AVAILABLE_PENDING_HUMAN_REVIEW",
        "ARTIFACTS_DISCOVERED_VALIDATION_FAILED",
        "TERMINAL_NONRELEASABLE_INVENTORY_COMPLETE",
        "AVAILABLE_WITHOUT_DISCOVERABLE_ARTIFACTS",
    }:
        errors.append("cleanup requires a complete terminal artifact inventory observation")
    if observation.get("human_release_recorded") is not False:
        errors.append("build observation must not impersonate a human release")
    if observation.get("raw_arn_or_account_included") is not False:
        errors.append("redacted build observation contains raw identifiers")
    if observation_state == "AVAILABLE_PENDING_HUMAN_REVIEW" and (
        observation.get("ami_launch_permission_count") != 0
        or observation.get("snapshot_create_volume_permission_count") != 0
        or observation.get("sharing_permissions_verified") is not True
    ):
        errors.append("build observation does not verify zero AMI/snapshot sharing permissions")
    if inventory.get("contains_account_scoped_identifiers") is not True:
        errors.append("secure inventory identifier boundary is invalid")
    errors.extend(_inventory_artifact_errors(inventory))
    inventory_state = inventory.get("last_observed_build_state")
    if observation_state == "TERMINAL_NONRELEASABLE_INVENTORY_COMPLETE":
        if inventory_state not in {"FAILED", "CANCELLED", "DEPRECATED", "DISABLED"}:
            errors.append("terminal non-releasable observation does not match inventory build state")
    elif observation_state in {
        "AVAILABLE_PENDING_HUMAN_REVIEW",
        "ARTIFACTS_DISCOVERED_VALIDATION_FAILED",
        "AVAILABLE_WITHOUT_DISCOVERABLE_ARTIFACTS",
    } and inventory_state != "AVAILABLE":
        errors.append("available-build observation does not match inventory build state")

    image_build_ref = inventory.get("image_build_ref")
    if not isinstance(image_build_ref, str) or not IMAGE_REF.fullmatch(image_build_ref):
        errors.append("secure inventory image_build_ref is invalid")
    elif observation.get("image_build_ref") != image_build_ref:
        errors.append("build observation and secure inventory refs differ")

    build_arn = inventory.get("image_build_version_arn")
    pipeline_arn = inventory.get("pipeline_arn")
    if not isinstance(build_arn, str) or not build_arn.startswith("arn:aws:imagebuilder:"):
        errors.append("secure inventory build ARN is invalid")
    elif observation.get("image_build_arn_sha256") != _text_sha256(build_arn):
        errors.append("build observation does not bind the secure inventory build ARN")
    if not isinstance(pipeline_arn, str) or not pipeline_arn.startswith("arn:aws:imagebuilder:"):
        errors.append("secure inventory pipeline ARN is invalid")
    elif observation.get("pipeline_arn_sha256") != _text_sha256(pipeline_arn):
        errors.append("build observation does not bind the secure inventory pipeline ARN")

    ami_ids = inventory.get("ami_ids")
    snapshot_ids = inventory.get("snapshot_ids")
    if not isinstance(ami_ids, list) or len(ami_ids) > 8:
        errors.append("secure inventory must contain 0..8 AMIs")
    elif observation.get("ami_count") != len(ami_ids):
        errors.append("build observation AMI count does not match the secure inventory")
    elif observation_state == "AVAILABLE_PENDING_HUMAN_REVIEW" and (
        len(ami_ids) != 1 or observation.get("ami_id") != ami_ids[0]
    ):
        errors.append("releasable build observation AMI does not match the secure inventory")
    elif observation.get("ami_id") not in ["", *ami_ids]:
        errors.append("validation-failed build observation AMI differs from the secure inventory")
    if observation_state == "AVAILABLE_WITHOUT_DISCOVERABLE_ARTIFACTS" and ami_ids != []:
        errors.append("artifact-free available observation has one or more inventory AMIs")
    if not isinstance(snapshot_ids, list):
        errors.append("secure inventory snapshots must be a list")
    elif observation.get("snapshot_count") != len(snapshot_ids):
        errors.append("build observation snapshot count does not match the secure inventory")
    return errors


def audit_endpoint_disposition(
    payload: object,
    *,
    now: datetime,
    inventory: object,
    endpoint_backend_hash: str | None,
    endpoint_teardown: object | None,
    endpoint_teardown_hash: str | None,
) -> list[str]:
    """Require a recent, AMI-scoped zero-active-endpoint observation before cleanup."""
    if not isinstance(payload, dict):
        return ["endpoint disposition observation must be an object"]
    errors: list[str] = []
    if set(payload) != ENDPOINT_DISPOSITION_KEYS:
        errors.append("endpoint disposition keys differ from the exact schema")
    if payload.get("schema_version") != "jcareer-windows-endpoint-disposition-observation-v1":
        errors.append("endpoint disposition schema is invalid")
    if payload.get("scope") != "workplace-windows-endpoint-disposition":
        errors.append("endpoint disposition scope is invalid")
    if not isinstance(inventory, dict):
        return errors + ["secure inventory must be an object"]
    image_build_ref = inventory.get("image_build_ref")
    artifacts = inventory.get("ami_artifacts")
    if payload.get("image_build_ref") != image_build_ref:
        errors.append("endpoint disposition image ref does not match the secure inventory")
    region_bound_hash = _region_bound_ami_set_sha256(artifacts)
    if region_bound_hash is None or payload.get("ami_set_sha256") != region_bound_hash:
        errors.append("endpoint disposition region-bound AMI set does not match the secure inventory")
    if payload.get("endpoint_backend_config_sha256") != endpoint_backend_hash:
        errors.append("endpoint disposition backend binding does not match")
    observed_at = parse_time(payload.get("observed_at"))
    if observed_at is None or observed_at > now + timedelta(minutes=5) or now - observed_at > timedelta(hours=2):
        errors.append("endpoint disposition must be a recent timezone-aware observation")
    if payload.get("endpoint_terraform_state_resource_count") != 0:
        errors.append("endpoint Terraform state is not empty")
    if payload.get("active_instance_count") != 0:
        errors.append("active instances still reference the approved AMI set")
    if payload.get("raw_identifiers_included") is not False:
        errors.append("endpoint disposition must be redacted")
    if payload.get("whole_account_zero_claimed") is not False:
        errors.append("endpoint disposition must remain scoped to the approved AMI set")

    recorded_teardown = payload.get("endpoint_teardown_receipt_sha256")
    mode = payload.get("observation_mode")
    if endpoint_teardown is None:
        if mode != "EMPTY_STATE_AND_SCOPED_ACTIVE_ZERO" or recorded_teardown not in {"", None}:
            errors.append("endpoint disposition without teardown receipt has an invalid mode")
    else:
        if mode != "TEARDOWN_RECEIPT_AND_SCOPED_ACTIVE_ZERO":
            errors.append("endpoint disposition teardown mode is invalid")
        if not isinstance(recorded_teardown, str) or not isinstance(endpoint_teardown_hash, str) or not hmac.compare_digest(recorded_teardown, endpoint_teardown_hash):
            errors.append("endpoint disposition teardown receipt hash does not match")
        if not isinstance(endpoint_teardown, dict) or set(endpoint_teardown) != ENDPOINT_TEARDOWN_KEYS:
            errors.append("endpoint teardown receipt keys differ from the exact schema")
        elif (
            endpoint_teardown.get("schema_version") != "jcareer-redacted-terraform-teardown-receipt-v1"
            or endpoint_teardown.get("scope") not in {
                "workplace-windows-endpoints-teardown",
                "workplace-windows-endpoints-recovery-teardown",
            }
            or endpoint_teardown.get("result") != "DELETE_ONLY_PLAN_APPLIED"
            or endpoint_teardown.get("backend_config_sha256") != endpoint_backend_hash
            or endpoint_teardown.get("resource_identifiers_included") is not False
            or endpoint_teardown.get("post_teardown_inventory_observed") is not False
            or endpoint_teardown.get("protected_input_snapshot_count")
            != ENDPOINT_TEARDOWN_PROTECTED_INPUT_SNAPSHOT_COUNT
            or endpoint_teardown.get("local_snapshot_cleanup_observed") is not True
        ):
            errors.append("endpoint teardown receipt content is invalid")
        if isinstance(endpoint_teardown, dict):
            approval_ref = endpoint_teardown.get("approval_ref")
            if not isinstance(approval_ref, str) or not APPROVAL_REF.fullmatch(
                approval_ref
            ):
                errors.append("endpoint teardown receipt approval_ref is invalid")
            saved_plan_hash = endpoint_teardown.get("saved_plan_sha256")
            if not isinstance(saved_plan_hash, str) or not SHA256.fullmatch(
                saved_plan_hash
            ):
                errors.append("endpoint teardown receipt saved plan digest is invalid")
            if parse_time(endpoint_teardown.get("completed_at")) is None:
                errors.append(
                    "endpoint teardown receipt completion time must be timezone-aware"
                )
    return errors


def audit_build_approval(
    payload: object,
    *,
    now: datetime,
    root: Path,
    backend_hash: str | None,
    definition_receipt: object,
    definition_receipt_hash: str | None,
    pipeline_hash: str | None,
    pipeline_configuration_hash: str | None,
    client_token_hash: str | None,
    require_approved: bool,
) -> list[str]:
    errors = _base_errors(
        payload,
        BUILD_KEYS,
        "jcareer-windows-image-build-approval-v1",
        "workplace-windows-image-build",
    )
    if not isinstance(payload, dict):
        return errors
    if payload.get("decision") == "PENDING_HUMAN_DECISION" and not require_approved:
        if any(
            payload.get(key)
            for key in (
                "approval_ref",
                "reviewer_ref",
                "approved_at",
                "expires_at",
                "backend_config_sha256",
                "definition_apply_receipt_sha256",
                "pipeline_arn_sha256",
                "pipeline_configuration_sha256",
                "image_source_sha256",
                "image_build_ref",
                "client_token_sha256",
                "poll_deadline_at",
                "cleanup_deadline_at",
            )
        ):
            errors.append("pending build example must not contain operation bindings")
        return errors
    if payload.get("decision") != "APPROVED_FOR_SINGLE_IMAGE_BUILD":
        errors.append("a human has not approved one image build")
        return errors
    errors.extend(_human_binding_errors(payload, now))
    errors.extend(
        audit_definition_apply_receipt(
            definition_receipt,
            backend_hash=backend_hash,
        )
    )
    for key, actual in (
        ("backend_config_sha256", backend_hash),
        ("definition_apply_receipt_sha256", definition_receipt_hash),
        ("pipeline_arn_sha256", pipeline_hash),
        ("pipeline_configuration_sha256", pipeline_configuration_hash),
        ("client_token_sha256", client_token_hash),
    ):
        _hash_binding(errors, payload, key, actual)
    try:
        source_hash = source_bundle_sha256(root)
    except OSError:
        source_hash = None
    _hash_binding(errors, payload, "image_source_sha256", source_hash)
    if not isinstance(payload.get("image_build_ref"), str) or not IMAGE_REF.fullmatch(payload["image_build_ref"]):
        errors.append("image_build_ref is invalid")
    if payload.get("expected_region") != "ap-northeast-2":
        errors.append("expected_region must be ap-northeast-2")
    if payload.get("expected_ami_count") != 1 or payload.get("max_executions") != 1:
        errors.append("approval must authorize exactly one execution and one AMI")
    if payload.get("cancel_on_deadline") is not True or payload.get("synthetic_data_only") is not True:
        errors.append("deadline cancellation and synthetic-only boundaries are required")
    approved_at = parse_time(payload.get("approved_at"))
    poll_deadline = parse_time(payload.get("poll_deadline_at"))
    cleanup_deadline = parse_time(payload.get("cleanup_deadline_at"))
    if approved_at is None or poll_deadline is None or cleanup_deadline is None:
        errors.append("build and cleanup deadlines must be timezone-aware")
    elif not (now < poll_deadline <= approved_at + timedelta(hours=4)):
        errors.append("poll deadline must be future and within four hours of approval")
    elif not (poll_deadline < cleanup_deadline <= approved_at + timedelta(days=7)):
        errors.append("cleanup deadline must follow polling and be within seven days")
    return errors


def audit_cleanup_approval(
    payload: object,
    *,
    now: datetime,
    backend_hash: str | None,
    observation_hash: str | None,
    inventory_hash: str | None,
    image_build_ref: str | None,
    ami_count: int | None,
    snapshot_count: int | None,
    endpoint_disposition_hash: str | None,
    endpoint_teardown_hash: str | None,
    require_approved: bool,
) -> list[str]:
    errors = _base_errors(
        payload,
        CLEANUP_KEYS,
        "jcareer-windows-image-cleanup-approval-v1",
        "workplace-windows-image-artifact-cleanup",
    )
    if not isinstance(payload, dict):
        return errors
    if payload.get("decision") == "PENDING_HUMAN_DECISION" and not require_approved:
        if any(
            payload.get(key)
            for key in (
                "approval_ref",
                "reviewer_ref",
                "approved_at",
                "expires_at",
                "backend_config_sha256",
                "build_observation_sha256",
                "secure_inventory_sha256",
                "image_build_ref",
                "endpoint_disposition_observation_sha256",
                "endpoint_teardown_receipt_sha256",
            )
        ):
            errors.append("pending cleanup example must not contain operation bindings")
        return errors
    if payload.get("decision") != "APPROVED_FOR_IMAGE_ARTIFACT_CLEANUP":
        errors.append("a human has not approved image artifact cleanup")
        return errors
    errors.extend(_human_binding_errors(payload, now))
    for key, actual in (
        ("backend_config_sha256", backend_hash),
        ("build_observation_sha256", observation_hash),
        ("secure_inventory_sha256", inventory_hash),
        ("endpoint_disposition_observation_sha256", endpoint_disposition_hash),
    ):
        _hash_binding(errors, payload, key, actual)
    if payload.get("image_build_ref") != image_build_ref or not isinstance(image_build_ref, str):
        errors.append("cleanup image_build_ref does not match the secure inventory")
    if payload.get("expected_ami_count") != ami_count or not isinstance(ami_count, int):
        errors.append("cleanup AMI count does not match the secure inventory")
    if payload.get("expected_snapshot_count") != snapshot_count or not isinstance(snapshot_count, int):
        errors.append("cleanup snapshot count does not match the secure inventory")
    if payload.get("include_amis") is not True or payload.get("include_snapshots") is not True:
        errors.append("cleanup must include both AMIs and snapshots")
    recorded_endpoint = payload.get("endpoint_teardown_receipt_sha256")
    if endpoint_teardown_hash is None:
        if recorded_endpoint not in {"", None}:
            errors.append("unexpected endpoint teardown receipt binding")
    elif not isinstance(recorded_endpoint, str) or not hmac.compare_digest(recorded_endpoint, endpoint_teardown_hash):
        errors.append("endpoint teardown receipt binding does not match")
    if payload.get("synthetic_data_only") is not True:
        errors.append("cleanup approval must retain the synthetic-only boundary")
    return errors


def audit_recovery_approval(
    payload: object,
    *,
    now: datetime,
    backend_hash: str | None,
    endpoint_backend_hash: str | None,
    observation_hash: str | None,
    inventory_hash: str | None,
    image_build_ref: str | None,
    ami_count: int | None,
    snapshot_count: int | None,
    endpoint_disposition_hash: str | None,
    endpoint_teardown_hash: str | None,
    require_approved: bool,
) -> list[str]:
    errors = _base_errors(
        payload,
        RECOVERY_KEYS,
        "jcareer-windows-image-cleanup-recovery-approval-v1",
        "workplace-windows-image-artifact-cleanup-recovery-observation",
    )
    if not isinstance(payload, dict):
        return errors
    if payload.get("decision") == "PENDING_HUMAN_DECISION" and not require_approved:
        bound = RECOVERY_KEYS - {
            "schema_version",
            "scope",
            "decision",
            "expected_live_image_state",
            "expected_scoped_residual_ami_count",
            "expected_scoped_residual_snapshot_count",
            "mutation_authorized",
            "lifecycle_success_assertion_authorized",
            "synthetic_data_only",
            "notes",
        }
        if any(payload.get(key) for key in bound):
            errors.append("pending recovery example must not contain operation bindings")
        return errors
    if payload.get("decision") != "APPROVED_FOR_READ_ONLY_DELETED_RECOVERY":
        errors.append("a human has not approved read-only deleted-state recovery observation")
        return errors
    errors.extend(_human_binding_errors(payload, now))
    for key, actual in (
        ("backend_config_sha256", backend_hash),
        ("endpoint_backend_config_sha256", endpoint_backend_hash),
        ("build_observation_sha256", observation_hash),
        ("secure_inventory_sha256", inventory_hash),
        ("endpoint_disposition_observation_sha256", endpoint_disposition_hash),
    ):
        _hash_binding(errors, payload, key, actual)
    if payload.get("image_build_ref") != image_build_ref or not isinstance(image_build_ref, str):
        errors.append("recovery image_build_ref does not match the secure inventory")
    if payload.get("expected_ami_count") != ami_count or not isinstance(ami_count, int):
        errors.append("recovery AMI count does not match the secure inventory")
    if payload.get("expected_snapshot_count") != snapshot_count or not isinstance(snapshot_count, int):
        errors.append("recovery snapshot count does not match the secure inventory")
    if (
        payload.get("expected_live_image_state") != "DELETED"
        or payload.get("expected_scoped_residual_ami_count") != 0
        or payload.get("expected_scoped_residual_snapshot_count") != 0
    ):
        errors.append("recovery approval must expect DELETED and exact scoped residual zero")
    if (
        payload.get("mutation_authorized") is not False
        or payload.get("lifecycle_success_assertion_authorized") is not False
        or payload.get("synthetic_data_only") is not True
    ):
        errors.append("recovery approval must remain read-only, non-assertive, and synthetic-only")
    recorded_teardown = payload.get("endpoint_teardown_receipt_sha256")
    if endpoint_teardown_hash is None:
        if recorded_teardown not in {"", None}:
            errors.append("unexpected endpoint teardown receipt binding")
    elif not isinstance(recorded_teardown, str) or not hmac.compare_digest(
        recorded_teardown, endpoint_teardown_hash
    ):
        errors.append("endpoint teardown receipt binding does not match")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="operation", required=True)
    build = sub.add_parser("build")
    cleanup = sub.add_parser("cleanup")
    recovery = sub.add_parser("recovery")
    for item in (build, cleanup, recovery):
        item.add_argument("--approval", required=True)
        item.add_argument("--backend-config-sha256", required=True)
        item.add_argument("--require-approved", action="store_true")
        item.add_argument("--now")
    build.add_argument("--root", default=".")
    build.add_argument("--definition-apply-receipt", required=True)
    build.add_argument("--pipeline-arn-sha256", required=True)
    build.add_argument("--pipeline-configuration-sha256", required=True)
    build.add_argument("--client-token-sha256", required=True)
    for item in (cleanup, recovery):
        item.add_argument("--build-observation", required=True)
        item.add_argument("--secure-inventory", required=True)
        item.add_argument("--endpoint-backend-config", required=True)
        item.add_argument("--endpoint-disposition-observation", required=True)
        item.add_argument("--endpoint-teardown-receipt")
    args = parser.parse_args()
    try:
        payload = json.loads(Path(args.approval).read_text(encoding="utf-8-sig"))
        now = parse_time(args.now) if args.now else datetime.now(timezone.utc)
        if now is None:
            raise ValueError("--now must be timezone-aware")
        if args.operation == "build":
            definition_receipt_bytes = Path(args.definition_apply_receipt).read_bytes()
            definition_receipt = json.loads(
                definition_receipt_bytes.decode("utf-8-sig")
            )
            errors = audit_build_approval(
                payload,
                now=now,
                root=Path(args.root).resolve(),
                backend_hash=args.backend_config_sha256,
                definition_receipt=definition_receipt,
                definition_receipt_hash=hashlib.sha256(
                    definition_receipt_bytes
                ).hexdigest(),
                pipeline_hash=args.pipeline_arn_sha256,
                pipeline_configuration_hash=args.pipeline_configuration_sha256,
                client_token_hash=args.client_token_sha256,
                require_approved=args.require_approved,
            )
        else:
            inventory = json.loads(Path(args.secure_inventory).read_text(encoding="utf-8-sig"))
            observation = json.loads(Path(args.build_observation).read_text(encoding="utf-8-sig"))
            disposition = json.loads(Path(args.endpoint_disposition_observation).read_text(encoding="utf-8-sig"))
            endpoint_backend_hash = file_sha256(Path(args.endpoint_backend_config))
            if args.endpoint_teardown_receipt:
                endpoint_teardown_bytes = Path(
                    args.endpoint_teardown_receipt
                ).read_bytes()
                endpoint_teardown = json.loads(
                    endpoint_teardown_bytes.decode("utf-8-sig")
                )
                endpoint_hash = hashlib.sha256(endpoint_teardown_bytes).hexdigest()
            else:
                endpoint_teardown = None
                endpoint_hash = None
            errors = audit_cleanup_artifact_binding(observation, inventory)
            errors.extend(
                audit_endpoint_disposition(
                    disposition,
                    now=now,
                    inventory=inventory,
                    endpoint_backend_hash=endpoint_backend_hash,
                    endpoint_teardown=endpoint_teardown,
                    endpoint_teardown_hash=endpoint_hash,
                )
            )
            inventory_object = inventory if isinstance(inventory, dict) else {}
            ami_values = inventory_object.get("ami_ids")
            snapshot_values = inventory_object.get("snapshot_ids")
            approval_arguments = {
                "payload": payload,
                "now": now,
                "backend_hash": args.backend_config_sha256,
                "observation_hash": file_sha256(Path(args.build_observation)),
                "inventory_hash": file_sha256(Path(args.secure_inventory)),
                "image_build_ref": inventory_object.get("image_build_ref"),
                "ami_count": len(ami_values) if isinstance(ami_values, list) else None,
                "snapshot_count": len(snapshot_values) if isinstance(snapshot_values, list) else None,
                "endpoint_disposition_hash": file_sha256(Path(args.endpoint_disposition_observation)),
                "endpoint_teardown_hash": endpoint_hash,
                "require_approved": args.require_approved,
            }
            if args.operation == "cleanup":
                approval_errors = audit_cleanup_approval(**approval_arguments)
            else:
                approval_errors = audit_recovery_approval(
                    **approval_arguments,
                    endpoint_backend_hash=endpoint_backend_hash,
                )
            errors = approval_errors + errors
    except (OSError, ValueError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        print(f"image operation approval check failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    for error in errors:
        print(f"image operation approval check failed: {error}", file=sys.stderr)
    if not errors:
        print("Windows image operation approval: PASS (human decision consumed, not made)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
