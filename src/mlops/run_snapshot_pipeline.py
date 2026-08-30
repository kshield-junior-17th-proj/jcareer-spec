"""Train a challenger from a bounded, feature-only S3 snapshot.

The caller is responsible for downloading the three allowed snapshot objects.
This module validates their cross-file contract before training and never
activates or wires the resulting model into ranking.
"""

from __future__ import annotations

import hashlib
import csv
import io
import json
import re
from pathlib import Path

from export_runtime_training import (
    COMPANY_SOURCE_FIELDS,
    COMPANY_SOURCE_CONTRACT,
    DIRECT_OR_FREE_TEXT_FIELDS_NOT_PERSISTED,
    FEATURE_SCHEMA_VERSION,
    FIELDNAMES,
    MEMBER_SOURCE_FIELDS,
    PROJECT_TEXT_FIELDS,
    RECEIPT_SCHEMA_VERSION,
    SCHEMA_VERSION,
    SYNTHETIC_ATTESTATION,
    TRAINING_FEATURES,
)
from generate_synthetic_training import write_artifact
from run_runtime_pipeline import RUN_SCHEMA_VERSION, validate_run_id
from train_challenger import train_from_manifest


SNAPSHOT_FILENAMES = (
    "ranking_dataset.csv",
    "dataset_manifest.json",
    "source_read_receipt.json",
)
SNAPSHOT_ROOT_PATTERN = re.compile(
    r"[a-zA-Z0-9][a-zA-Z0-9._-]*(?:/[a-zA-Z0-9][a-zA-Z0-9._-]*){0,7}"
)
HEX_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
RUNTIME_REFERENCE_PATTERNS = {
    "candidate_ref": re.compile(r"syn-candidate-db-[0-9a-f]{20}"),
    "job_ref": re.compile(r"syn-job-db-[0-9a-f]{20}"),
    "company_ref": re.compile(r"syn-company-db-[0-9a-f]{20}"),
}
MANIFEST_KEYS = {
    "schema_version",
    "feature_schema_version",
    "synthetic_only",
    "synthetic_attestation",
    "member_data_used",
    "company_customer_data_used",
    "company_source_contract",
    "purpose",
    "source_runtime_db_wired",
    "company_source_contract",
    "ranking_runtime_wired",
    "runtime_wired",
    "row_count",
    "candidate_count",
    "company_count",
    "dataset_file",
    "dataset_sha256",
    "source_receipt_file",
    "source_digest",
    "field_roles",
    "label_semantics",
    "excluded_unresolved_status_counts",
    "dangling_reference_counts",
    "direct_or_free_text_fields_not_persisted",
    "human_decision_required_before_runtime_use",
}
RECEIPT_KEYS = {
    "schema_version",
    "feature_schema_version",
    "synthetic_only",
    "synthetic_attestation",
    "source_runtime_db_wired",
    "member_source_fields_read",
    "company_source_fields_read",
    "source_record_counts",
    "dangling_reference_counts",
    "source_digest",
    "raw_source_values_persisted",
    "name_and_email_role",
    "self_intro_role",
    "project_text_role",
    "project_fields_used",
    "privacy_core_role",
    "training_feature_allowlist",
    "limitations",
    "human_interpretation_required",
}


def validate_snapshot_root(snapshot_root: str) -> str:
    normalized = snapshot_root.strip().strip("/")
    if not normalized or len(normalized) > 240:
        raise ValueError("feature snapshot root must be a bounded non-empty prefix")
    if SNAPSHOT_ROOT_PATTERN.fullmatch(normalized) is None:
        raise ValueError("feature snapshot root contains an unsafe path segment")
    return normalized


def expected_snapshot_prefix(snapshot_root: str, run_id: str) -> str:
    return f"{validate_snapshot_root(snapshot_root)}/{validate_run_id(run_id)}/"


def _load_json_object(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def validate_feature_snapshot(dataset_directory: Path) -> dict[str, object]:
    manifest = _load_json_object(
        dataset_directory / "dataset_manifest.json", "dataset manifest"
    )
    receipt = _load_json_object(
        dataset_directory / "source_read_receipt.json", "source read receipt"
    )
    if set(manifest) != MANIFEST_KEYS:
        raise ValueError("feature snapshot manifest fields do not match the allowlist")
    if set(receipt) != RECEIPT_KEYS:
        raise ValueError("feature snapshot receipt fields do not match the allowlist")

    required_manifest = {
        "schema_version": SCHEMA_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "synthetic_only": True,
        "synthetic_attestation": SYNTHETIC_ATTESTATION,
        "member_data_used": True,
        "company_customer_data_used": True,
        "company_source_contract": COMPANY_SOURCE_CONTRACT,
        "purpose": "synthetic_runtime_challenger_training_demonstration",
        "source_runtime_db_wired": True,
        "company_source_contract": COMPANY_SOURCE_CONTRACT,
        "ranking_runtime_wired": False,
        "runtime_wired": False,
        "dataset_file": "ranking_dataset.csv",
        "source_receipt_file": "source_read_receipt.json",
        "field_roles": {
            "training_features": TRAINING_FEATURES,
            "label": "pipeline_progression_proxy",
            "evaluation_only": ["evaluation_group"],
            "logical_identifiers_not_features": [
                "candidate_ref",
                "job_ref",
                "company_ref",
            ],
            "split": "split",
        },
        "label_semantics": "historical_pipeline_progression_proxy_not_candidate_quality_or_hiring_probability",
        "direct_or_free_text_fields_not_persisted": DIRECT_OR_FREE_TEXT_FIELDS_NOT_PERSISTED,
        "human_decision_required_before_runtime_use": True,
    }
    for key, expected in required_manifest.items():
        if manifest.get(key) != expected:
            raise ValueError(f"feature snapshot manifest rejects {key}")

    required_receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "synthetic_only": True,
        "synthetic_attestation": SYNTHETIC_ATTESTATION,
        "source_runtime_db_wired": True,
        "member_source_fields_read": MEMBER_SOURCE_FIELDS,
        "company_source_fields_read": COMPANY_SOURCE_FIELDS,
        "raw_source_values_persisted": False,
        "name_and_email_role": "lineage_digest_input_only_not_model_features",
        "self_intro_role": "read_then_derived_to_overlap_features_raw_text_not_persisted",
        "project_text_role": "reviewed_fields_read_then_derived_to_overlap_features_raw_text_not_persisted",
        "project_fields_used": PROJECT_TEXT_FIELDS,
        "privacy_core_role": "synthetic_lifecycle_filter_not_model_training_consent",
        "training_feature_allowlist": TRAINING_FEATURES,
        "limitations": [
            "application status is a proxy and can reproduce historical recruiter behavior",
            "synthetic runtime data does not establish production model quality",
            "token-overlap features can be gamed by copying job or company terms",
            "rows from multiple synthetic company tenants are pooled only for a platform-wide demo",
            "synthetic document passed/not_passed outcomes are not used as training labels",
            "seed identity/profile markers do not cryptographically bind in-place job text",
            "no automatic release, compliance conclusion, or fairness conclusion is produced",
        ],
        "human_interpretation_required": True,
    }
    for key, expected in required_receipt.items():
        if receipt.get(key) != expected:
            raise ValueError(f"feature snapshot receipt rejects {key}")

    excluded_counts = manifest.get("excluded_unresolved_status_counts")
    if (
        not isinstance(excluded_counts, dict)
        or set(excluded_counts) != {"applied"}
        or type(excluded_counts["applied"]) is not int
        or excluded_counts["applied"] < 0
    ):
        raise ValueError("feature snapshot excluded status counts are invalid")
    dangling_counts = manifest.get("dangling_reference_counts")
    if (
        not isinstance(dangling_counts, dict)
        or set(dangling_counts)
        != {"member_missing", "job_missing"}
        or any(type(value) is not int or value < 0 for value in dangling_counts.values())
        or receipt.get("dangling_reference_counts") != dangling_counts
    ):
        raise ValueError("feature snapshot dangling reference counts are invalid")
    source_counts = receipt.get("source_record_counts")
    if (
        not isinstance(source_counts, dict)
        or set(source_counts)
        != {
            "candidate_resume_records",
            "application_records",
            "privacy_core_events",
            "job_company_records",
            "exported_resolved_rows",
        }
        or any(type(value) is not int or value < 0 for value in source_counts.values())
        or source_counts["exported_resolved_rows"] != manifest.get("row_count")
    ):
        raise ValueError("feature snapshot source record counts are invalid")
    for count_name in ("row_count", "candidate_count", "company_count"):
        count = manifest.get(count_name)
        if type(count) is not int or count <= 0:
            raise ValueError(f"feature snapshot {count_name} is invalid")

    source_digest = manifest.get("source_digest")
    if not isinstance(source_digest, str) or HEX_SHA256_PATTERN.fullmatch(source_digest) is None:
        raise ValueError("feature snapshot source digest is invalid")
    if receipt.get("source_digest") != source_digest:
        raise ValueError("feature snapshot source digest does not match receipt")

    dataset_content = (dataset_directory / "ranking_dataset.csv").read_bytes()
    dataset_digest = hashlib.sha256(dataset_content).hexdigest()
    if manifest.get("dataset_sha256") != dataset_digest:
        raise ValueError("feature snapshot dataset SHA-256 does not match manifest")
    try:
        rows = csv.DictReader(io.StringIO(dataset_content.decode("utf-8")))
        if rows.fieldnames != FIELDNAMES:
            raise ValueError("feature snapshot dataset columns do not match the allowlist")
        for line_number, row in enumerate(rows, start=2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(
                    f"feature snapshot row {line_number} has extra or missing fields"
                )
            for field, pattern in RUNTIME_REFERENCE_PATTERNS.items():
                if pattern.fullmatch(str(row.get(field, ""))) is None:
                    raise ValueError(
                        f"feature snapshot row {line_number} has an invalid synthetic reference"
                    )
    except UnicodeDecodeError as exc:
        raise ValueError("feature snapshot dataset must be UTF-8") from exc
    return manifest


def run_snapshot_pipeline(
    *,
    snapshot_files: dict[str, bytes],
    output_root: Path,
    run_id: str,
    epochs: int = 320,
) -> dict[str, Path]:
    validate_run_id(run_id)
    if set(snapshot_files) != set(SNAPSHOT_FILENAMES):
        raise ValueError("feature snapshot must contain exactly the three allowed files")

    dataset_directory = output_root / "dataset"
    for filename in SNAPSHOT_FILENAMES:
        body = snapshot_files[filename]
        if not isinstance(body, bytes):
            raise ValueError("feature snapshot object body must be bytes")
        write_artifact(dataset_directory / filename, body, overwrite=False)

    manifest = validate_feature_snapshot(dataset_directory)
    trained = train_from_manifest(
        manifest_path=dataset_directory / "dataset_manifest.json",
        output_directory=output_root / "model",
        epochs=epochs,
        overwrite=False,
    )
    artifacts: dict[str, Path] = {
        "dataset": dataset_directory / "ranking_dataset.csv",
        "manifest": dataset_directory / "dataset_manifest.json",
        "receipt": dataset_directory / "source_read_receipt.json",
        **trained,
    }
    run_receipt_path = output_root / "pipeline_run_receipt.json"
    run_receipt = {
        "schema_version": RUN_SCHEMA_VERSION,
        "run_id": run_id,
        "execution_mode": "ON_DEMAND_SERVERLESS_FEATURE_SNAPSHOT",
        "source_mode": "feature_snapshot",
        "synthetic_only": True,
        "source_runtime_db_wired": True,
        "source_runtime_db_read_in_this_execution": False,
        "source_snapshot_validated": True,
        "source_dataset_sha256": manifest["dataset_sha256"],
        "source_digest": manifest["source_digest"],
        "challenger_trained": True,
        "runtime_ranking_wired": False,
        "automatic_model_activation": False,
        "approval_state": "HUMAN_DECISION_NOT_RECORDED",
        "model_state": "TRAINED_SYNTHETIC_RUNTIME_DATA_NOT_APPROVED",
        "artifact_sha256": {
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in sorted(artifacts.items())
        },
        "human_decision_required_before_any_runtime_use": True,
    }
    write_artifact(
        run_receipt_path,
        (json.dumps(run_receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        overwrite=False,
    )
    artifacts["run_receipt"] = run_receipt_path
    return artifacts
