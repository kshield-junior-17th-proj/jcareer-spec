"""AWS Lambda adapter for one-shot synthetic runtime challenger training."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from export_runtime_training import SYNTHETIC_ATTESTATION
from run_runtime_pipeline import run_pipeline, validate_run_id
from run_snapshot_pipeline import (
    SNAPSHOT_FILENAMES,
    expected_snapshot_prefix,
    run_snapshot_pipeline,
)


logger = logging.getLogger("jcareer.synthetic_mlops")
SERVERLESS_ENABLE_VALUE = "JCAREER_SYNTHETIC_SERVERLESS_MLOPS"
SOURCE_MODE_RUNTIME_DB = "runtime_db"
SOURCE_MODE_FEATURE_SNAPSHOT = "feature_snapshot"
DEFAULT_FEATURE_SNAPSHOT_ROOT = "mlops/sources"
SNAPSHOT_MAX_BYTES = {
    "ranking_dataset.csv": 8 * 1024 * 1024,
    "dataset_manifest.json": 512 * 1024,
    "source_read_receipt.json": 512 * 1024,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _string_item(values: Mapping[str, object]) -> dict[str, dict[str, str]]:
    return {str(key): {"S": str(value)} for key, value in values.items()}


def _event_detail(event: object) -> dict[str, object]:
    if not isinstance(event, dict):
        raise ValueError("event must be an object")
    detail = event.get("detail")
    if detail is None:
        return event
    if not isinstance(detail, dict):
        raise ValueError("event detail must be an object")
    return detail


def _required(environment: Mapping[str, str], key: str) -> str:
    value = environment.get(key, "").strip()
    if not value:
        raise ValueError(f"required environment setting is missing: {key}")
    return value


def _put_run_state(
    dynamodb_client: object,
    table_name: str,
    *,
    run_id: str,
    state: str,
    created_at: str,
    detail: Mapping[str, object] | None = None,
    create_only: bool = False,
) -> None:
    values: dict[str, object] = {
        "run_id": run_id,
        "state": state,
        "created_at": created_at,
        "updated_at": _now(),
        "synthetic_only": "true",
        "runtime_ranking_wired": "false",
        "automatic_model_activation": "false",
        "approval_state": "HUMAN_DECISION_NOT_RECORDED",
    }
    if detail:
        values.update(detail)
    arguments: dict[str, object] = {
        "TableName": table_name,
        "Item": _string_item(values),
    }
    if create_only:
        arguments["ConditionExpression"] = "attribute_not_exists(run_id)"
    dynamodb_client.put_item(**arguments)


def _read_snapshot_body(response: object, *, filename: str) -> bytes:
    if not isinstance(response, dict):
        raise RuntimeError("feature snapshot store returned an invalid response")
    content_length = response.get("ContentLength")
    limit = SNAPSHOT_MAX_BYTES[filename]
    if isinstance(content_length, int) and content_length > limit:
        raise ValueError(f"feature snapshot object exceeds size limit: {filename}")
    stream = response.get("Body")
    if stream is None or not hasattr(stream, "read"):
        raise RuntimeError("feature snapshot object body is unavailable")
    body = stream.read(limit + 1)
    if not isinstance(body, bytes):
        raise RuntimeError("feature snapshot object body must be bytes")
    if len(body) > limit:
        raise ValueError(f"feature snapshot object exceeds size limit: {filename}")
    return body


def _download_feature_snapshot(
    *,
    detail: Mapping[str, object],
    environment: Mapping[str, str],
    s3_client: object,
    run_id: str,
) -> dict[str, bytes]:
    bucket = _required(environment, "MLOPS_FEATURE_SNAPSHOT_BUCKET")
    configured_root = environment.get(
        "MLOPS_FEATURE_SNAPSHOT_ROOT", DEFAULT_FEATURE_SNAPSHOT_ROOT
    )
    expected_prefix = expected_snapshot_prefix(configured_root, run_id)
    requested_prefix = str(detail.get("source_prefix") or expected_prefix)
    if requested_prefix != expected_prefix:
        raise ValueError("feature snapshot source_prefix must match the bounded run prefix")

    files: dict[str, bytes] = {}
    for filename in SNAPSHOT_FILENAMES:
        response = s3_client.get_object(
            Bucket=bucket,
            Key=f"{expected_prefix}{filename}",
        )
        files[filename] = _read_snapshot_body(response, filename=filename)
    return files


def run_serverless_pipeline(
    event: object,
    *,
    environment: Mapping[str, str],
    s3_client: object,
    dynamodb_client: object,
    work_root: Path = Path("/tmp/jcareer-synthetic-mlops"),
) -> dict[str, object]:
    if environment.get("ALLOW_SYNTHETIC_MLOPS_RUN") != SERVERLESS_ENABLE_VALUE:
        raise ValueError("serverless synthetic MLOps execution is disabled")
    if environment.get("MLOPS_SYNTHETIC_ATTESTATION") != SYNTHETIC_ATTESTATION:
        raise ValueError("synthetic runtime attestation is required")

    detail = _event_detail(event)
    action = str(detail.get("action") or "train_challenger")
    if action != "train_challenger":
        raise ValueError("unsupported serverless MLOps action")
    run_id = validate_run_id(str(detail.get("run_id") or f"run-{uuid.uuid4()}"))
    source_mode = str(
        detail.get("source_mode")
        or environment.get("MLOPS_SOURCE_MODE")
        or SOURCE_MODE_RUNTIME_DB
    )
    if source_mode not in {SOURCE_MODE_RUNTIME_DB, SOURCE_MODE_FEATURE_SNAPSHOT}:
        raise ValueError("unsupported serverless MLOps source_mode")
    artifact_bucket = _required(environment, "MLOPS_ARTIFACT_BUCKET")
    run_table = _required(environment, "MLOPS_RUN_TABLE")
    epochs = int(environment.get("MLOPS_EPOCHS", "320"))
    created_at = _now()
    _put_run_state(
        dynamodb_client,
        run_table,
        run_id=run_id,
        state="RUNNING",
        created_at=created_at,
        detail={"source_mode": source_mode},
        create_only=True,
    )

    try:
        if source_mode == SOURCE_MODE_RUNTIME_DB:
            artifacts = run_pipeline(
                member_database_url=_required(environment, "MEMBER_DATABASE_URL"),
                company_database_url=_required(environment, "COMPANY_DATABASE_URL"),
                output_root=work_root / run_id,
                synthetic_attestation=SYNTHETIC_ATTESTATION,
                run_id=run_id,
                epochs=epochs,
            )
        else:
            snapshot_files = _download_feature_snapshot(
                detail=detail,
                environment=environment,
                s3_client=s3_client,
                run_id=run_id,
            )
            artifacts = run_snapshot_pipeline(
                snapshot_files=snapshot_files,
                output_root=work_root / run_id,
                run_id=run_id,
                epochs=epochs,
            )
        for name, path in sorted(artifacts.items()):
            body = path.read_bytes()
            key = f"mlops/runs/{run_id}/{path.name}"
            put_arguments: dict[str, object] = {
                "Bucket": artifact_bucket,
                "Key": key,
                "Body": body,
                "ContentType": (
                    "text/csv; charset=utf-8"
                    if path.suffix == ".csv"
                    else "application/json"
                ),
                "ServerSideEncryption": "AES256",
            }
            kms_key_id = environment.get("MLOPS_ARTIFACT_KMS_KEY_ID", "").strip()
            if kms_key_id:
                put_arguments["ServerSideEncryption"] = "aws:kms"
                put_arguments["SSEKMSKeyId"] = kms_key_id
            response = s3_client.put_object(**put_arguments)
            if not isinstance(response, dict):
                raise RuntimeError("artifact store returned an invalid response")

        prefix = f"mlops/runs/{run_id}/"
        _put_run_state(
            dynamodb_client,
            run_table,
            run_id=run_id,
            state="TRAINED_PENDING_HUMAN_REVIEW",
            created_at=created_at,
            detail={
                "artifact_prefix": prefix,
                "artifact_count": len(artifacts),
                "model_state": "TRAINED_SYNTHETIC_RUNTIME_DATA_NOT_APPROVED",
                "source_mode": source_mode,
            },
        )
        return {
            "run_id": run_id,
            "state": "TRAINED_PENDING_HUMAN_REVIEW",
            "artifact_prefix": prefix,
            "artifact_count": len(artifacts),
            "runtime_ranking_wired": False,
            "automatic_model_activation": False,
            "source_mode": source_mode,
        }
    except Exception as exc:
        logger.error("synthetic_mlops_run_failed error_type=%s", type(exc).__name__)
        _put_run_state(
            dynamodb_client,
            run_table,
            run_id=run_id,
            state="FAILED_SAFE",
            created_at=created_at,
            detail={"error_type": type(exc).__name__},
        )
        raise


def lambda_handler(event: object, _context: object) -> dict[str, object]:
    import boto3

    return run_serverless_pipeline(
        event,
        environment=os.environ,
        s3_client=boto3.client("s3"),
        dynamodb_client=boto3.client("dynamodb"),
    )
