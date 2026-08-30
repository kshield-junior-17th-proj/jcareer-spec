"""Validate and record a human decision without activating a challenger model.

The receipt records human input only. It does not infer model quality,
compliance, fairness, or release readiness.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Mapping


REVIEW_SCHEMA_VERSION = "jcareer-synthetic-challenger-human-review-v1"
PENDING_REVIEW_STATE = "TRAINED_PENDING_HUMAN_REVIEW"
RECORDED_REVIEW_STATE = "HUMAN_INPUT_RECORDED"
HUMAN_INPUT_NOT_RECORDED = "NOT_RECORDED"
DECISION_SCOPE = "synthetic_challenger_review_record_only_not_release_authorization"
EXPECTED_MODEL_STATE = "TRAINED_SYNTHETIC_RUNTIME_DATA_NOT_APPROVED"
REVIEW_DECISIONS = frozenset({"APPROVED", "REJECTED"})
EXPECTED_ARTIFACT_FILES = frozenset(
    {
        "ranking_dataset.csv",
        "dataset_manifest.json",
        "source_read_receipt.json",
        "challenger_model.json",
        "evaluation_observations.json",
        "pipeline_run_receipt.json",
    }
)
APPROVER_REF_PATTERN = re.compile(r"syn-approver-[0-9a-f]{16,64}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
VERSION_ID_PATTERN = re.compile(r"[^\x00-\x1f\x7f]{1,1024}")


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def validate_artifact_bindings(
    value: object,
    *,
    run_id: str,
) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict) or set(value) != EXPECTED_ARTIFACT_FILES:
        raise ValueError("review requires the exact six versioned artifact bindings")
    validated: dict[str, dict[str, str]] = {}
    for name in sorted(EXPECTED_ARTIFACT_FILES):
        binding = value.get(name)
        if not isinstance(binding, dict) or set(binding) != {
            "key",
            "sha256",
            "version_id",
        }:
            raise ValueError(f"review artifact binding is invalid: {name}")
        key = binding.get("key")
        expected_key = f"mlops/runs/{run_id}/{name}"
        if key != expected_key:
            raise ValueError(f"review artifact key is invalid: {name}")
        digest = binding.get("sha256")
        if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
            raise ValueError(f"review artifact hash is invalid: {name}")
        version_id = binding.get("version_id")
        if (
            not isinstance(version_id, str)
            or version_id == "null"
            or VERSION_ID_PATTERN.fullmatch(version_id) is None
        ):
            raise ValueError(f"review artifact version is invalid: {name}")
        validated[name] = {
            "key": expected_key,
            "sha256": digest,
            "version_id": version_id,
        }
    return validated


def build_review_receipt(
    *,
    run_id: str,
    approver_ref: object,
    decision: object,
    submitted_artifact_bindings: object,
    expected_artifact_bindings: object,
    recorded_at: str,
) -> tuple[dict[str, object], str]:
    approver = str(approver_ref or "").strip()
    if APPROVER_REF_PATTERN.fullmatch(approver) is None:
        raise ValueError("review requires a bounded synthetic approver reference")
    human_decision = str(decision or "").strip().upper()
    if human_decision not in REVIEW_DECISIONS:
        raise ValueError("review decision must be APPROVED or REJECTED")
    submitted = validate_artifact_bindings(submitted_artifact_bindings, run_id=run_id)
    expected = validate_artifact_bindings(expected_artifact_bindings, run_id=run_id)
    if submitted != expected:
        raise ValueError("review artifact bindings do not match the pending run")
    if not recorded_at:
        raise ValueError("review recorded_at is required")

    receipt: dict[str, object] = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "run_id": run_id,
        "synthetic_only": True,
        "source_state": PENDING_REVIEW_STATE,
        "recorded_state": RECORDED_REVIEW_STATE,
        "human_input_state": RECORDED_REVIEW_STATE,
        "approver_ref": approver,
        "decision": human_decision,
        "decision_scope": DECISION_SCOPE,
        "decision_semantics": "human_input_record_only_not_model_quality_compliance_or_release_assessment",
        "artifact_bindings": submitted,
        "recorded_at": recorded_at,
        "runtime_ranking_wired": False,
        "automatic_model_activation": False,
        "release_authorized": False,
        "model_artifacts_modified": False,
        "model_quality_conclusion": None,
        "compliance_conclusion": None,
        "fairness_conclusion": None,
        "human_interpretation_required": True,
    }
    receipt_sha256 = hashlib.sha256(canonical_json(receipt).encode("utf-8")).hexdigest()
    return receipt, receipt_sha256


def decode_stored_artifact_bindings(
    value: object,
    *,
    run_id: str,
) -> dict[str, dict[str, str]]:
    if not isinstance(value, str):
        raise ValueError("pending run is missing stored artifact bindings")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("pending run artifact bindings are invalid") from exc
    return validate_artifact_bindings(parsed, run_id=run_id)


def string_item_value(item: Mapping[str, object], key: str) -> str:
    attribute = item.get(key)
    if not isinstance(attribute, dict) or not isinstance(attribute.get("S"), str):
        raise ValueError(f"pending run is missing state field: {key}")
    return str(attribute["S"])
