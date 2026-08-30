"""AWS Lambda adapter for one-shot synthetic runtime challenger training."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from export_runtime_training import SYNTHETIC_ATTESTATION
from review_challenger import (
    DECISION_SCOPE,
    EXPECTED_ARTIFACT_FILES,
    EXPECTED_MODEL_STATE,
    HUMAN_INPUT_NOT_RECORDED,
    PENDING_REVIEW_STATE,
    RECORDED_REVIEW_STATE,
    build_review_receipt,
    canonical_json,
    decode_stored_artifact_bindings,
    string_item_value,
)
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
TRAIN_ACTION = "train_challenger"
REVIEW_ACTION = "record_human_review"


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
        "release_authorized": "false",
        "human_input_state": HUMAN_INPUT_NOT_RECORDED,
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


def _get_run_item(
    dynamodb_client: object,
    table_name: str,
    run_id: str,
) -> dict[str, object]:
    response = dynamodb_client.get_item(
        TableName=table_name,
        Key={"run_id": {"S": run_id}},
        ConsistentRead=True,
    )
    if not isinstance(response, dict) or not isinstance(response.get("Item"), dict):
        raise ValueError("pending review run was not found")
    return response["Item"]


def _transition_run_to_pending(
    dynamodb_client: object,
    table_name: str,
    *,
    run_id: str,
    source_mode: str,
    artifact_prefix: str,
    artifact_bindings_json: str,
) -> dict[str, object]:
    updated_at = _now()
    values = _string_item(
        {
            ":pending_state": PENDING_REVIEW_STATE,
            ":running_state": "RUNNING",
            ":not_recorded": HUMAN_INPUT_NOT_RECORDED,
            ":synthetic_true": "true",
            ":artifact_count": "6",
            ":model_state": EXPECTED_MODEL_STATE,
            ":false": "false",
            ":source_mode": source_mode,
            ":artifact_prefix": artifact_prefix,
            ":artifact_bindings": artifact_bindings_json,
            ":updated_at": updated_at,
        }
    )
    response = dynamodb_client.update_item(
        TableName=table_name,
        Key={"run_id": {"S": run_id}},
        UpdateExpression=(
            "SET #state = :pending_state, updated_at = :updated_at, "
            "artifact_prefix = :artifact_prefix, artifact_count = :artifact_count, "
            "artifact_bindings = :artifact_bindings, model_state = :model_state"
        ),
        ConditionExpression=(
            "#state = :running_state AND human_input_state = :not_recorded "
            "AND synthetic_only = :synthetic_true AND source_mode = :source_mode "
            "AND runtime_ranking_wired = :false AND automatic_model_activation = :false "
            "AND release_authorized = :false AND attribute_not_exists(artifact_bindings) "
            "AND attribute_not_exists(model_state) AND attribute_not_exists(decision)"
        ),
        ExpressionAttributeNames={"#state": "state"},
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )
    if not isinstance(response, dict) or not isinstance(response.get("Attributes"), dict):
        raise RuntimeError("pending training state transition returned no attributes")
    attributes = response["Attributes"]
    _require_item_invariants(
        attributes,
        state=PENDING_REVIEW_STATE,
        human_input_state=HUMAN_INPUT_NOT_RECORDED,
    )
    if (
        string_item_value(attributes, "source_mode") != source_mode
        or string_item_value(attributes, "artifact_prefix") != artifact_prefix
        or string_item_value(attributes, "artifact_bindings") != artifact_bindings_json
    ):
        raise RuntimeError("pending training state transition returned conflicting attributes")
    return attributes


def _require_item_invariants(
    item: Mapping[str, object],
    *,
    state: str,
    human_input_state: str,
) -> None:
    expected = {
        "state": state,
        "human_input_state": human_input_state,
        "synthetic_only": "true",
        "artifact_count": "6",
        "model_state": EXPECTED_MODEL_STATE,
        "runtime_ranking_wired": "false",
        "automatic_model_activation": "false",
        "release_authorized": "false",
    }
    for key, expected_value in expected.items():
        if string_item_value(item, key) != expected_value:
            raise ValueError(f"human review rejects pending invariant: {key}")


def _recorded_review_response(
    *,
    item: Mapping[str, object],
    detail: Mapping[str, object],
    run_id: str,
) -> dict[str, object]:
    _require_item_invariants(
        item,
        state=RECORDED_REVIEW_STATE,
        human_input_state=RECORDED_REVIEW_STATE,
    )
    if string_item_value(item, "decision_scope") != DECISION_SCOPE:
        raise ValueError("recorded human review decision scope is invalid")
    bindings = decode_stored_artifact_bindings(
        string_item_value(item, "artifact_bindings"),
        run_id=run_id,
    )
    receipt_json = string_item_value(item, "review_receipt_json")
    receipt_sha256 = string_item_value(item, "review_receipt_sha256")
    try:
        receipt = json.loads(receipt_json)
    except json.JSONDecodeError as exc:
        raise ValueError("recorded human review receipt is invalid") from exc
    if not isinstance(receipt, dict) or canonical_json(receipt) != receipt_json:
        raise ValueError("recorded human review receipt is not canonical")
    observed_sha256 = hashlib.sha256(receipt_json.encode("utf-8")).hexdigest()
    if observed_sha256 != receipt_sha256:
        raise ValueError("recorded human review receipt digest is invalid")
    expected_receipt, expected_sha256 = build_review_receipt(
        run_id=run_id,
        approver_ref=detail.get("approver_ref"),
        decision=detail.get("decision"),
        submitted_artifact_bindings=detail.get("artifact_bindings"),
        expected_artifact_bindings=bindings,
        recorded_at=str(receipt.get("recorded_at") or ""),
    )
    if receipt != expected_receipt or receipt_sha256 != expected_sha256:
        raise ValueError("human review retry conflicts with the recorded receipt")
    if (
        string_item_value(item, "decision") != receipt["decision"]
        or string_item_value(item, "reviewed_by_ref") != receipt["approver_ref"]
    ):
        raise ValueError("recorded human review state conflicts with its receipt")
    return {
        "run_id": run_id,
        "state": RECORDED_REVIEW_STATE,
        "human_input_state": RECORDED_REVIEW_STATE,
        "decision": receipt["decision"],
        "decision_scope": DECISION_SCOPE,
        "release_authorized": False,
        "review_receipt_sha256": receipt_sha256,
        "review_receipt": receipt,
        "runtime_ranking_wired": False,
        "automatic_model_activation": False,
    }


def _record_human_review(
    *,
    detail: Mapping[str, object],
    environment: Mapping[str, str],
    dynamodb_client: object,
) -> dict[str, object]:
    if not detail.get("run_id"):
        raise ValueError("human review requires an explicit run_id")
    run_id = validate_run_id(str(detail["run_id"]))
    run_table = _required(environment, "MLOPS_RUN_TABLE")
    current = _get_run_item(dynamodb_client, run_table, run_id)
    current_state = string_item_value(current, "state")
    if current_state == RECORDED_REVIEW_STATE:
        return _recorded_review_response(item=current, detail=detail, run_id=run_id)
    _require_item_invariants(
        current,
        state=PENDING_REVIEW_STATE,
        human_input_state=HUMAN_INPUT_NOT_RECORDED,
    )
    if "review_receipt_sha256" in current or "decision" in current:
        raise ValueError("pending human review contains an unexpected prior decision")
    stored_bindings_json = string_item_value(current, "artifact_bindings")
    stored_bindings = decode_stored_artifact_bindings(
        stored_bindings_json,
        run_id=run_id,
    )
    recorded_at = _now()
    receipt, receipt_sha256 = build_review_receipt(
        run_id=run_id,
        approver_ref=detail.get("approver_ref"),
        decision=detail.get("decision"),
        submitted_artifact_bindings=detail.get("artifact_bindings"),
        expected_artifact_bindings=stored_bindings,
        recorded_at=recorded_at,
    )
    receipt_json = canonical_json(receipt)
    decision = str(receipt["decision"])
    values = _string_item(
        {
            ":recorded_state": RECORDED_REVIEW_STATE,
            ":decision": decision,
            ":decision_scope": DECISION_SCOPE,
            ":updated_at": recorded_at,
            ":approver_ref": receipt["approver_ref"],
            ":receipt_json": receipt_json,
            ":receipt_sha256": receipt_sha256,
            ":pending_state": PENDING_REVIEW_STATE,
            ":not_recorded": HUMAN_INPUT_NOT_RECORDED,
            ":synthetic_true": "true",
            ":artifact_count": "6",
            ":model_state": EXPECTED_MODEL_STATE,
            ":false": "false",
            ":artifact_bindings": stored_bindings_json,
        }
    )
    try:
        response = dynamodb_client.update_item(
            TableName=run_table,
            Key={"run_id": {"S": run_id}},
            UpdateExpression=(
                "SET #state = :recorded_state, human_input_state = :recorded_state, "
                "decision = :decision, decision_scope = :decision_scope, "
                "release_authorized = :false, updated_at = :updated_at, "
                "reviewed_by_ref = :approver_ref, review_receipt_json = :receipt_json, "
                "review_receipt_sha256 = :receipt_sha256"
            ),
            ConditionExpression=(
                "#state = :pending_state AND human_input_state = :not_recorded "
                "AND synthetic_only = :synthetic_true AND artifact_count = :artifact_count "
                "AND model_state = :model_state AND runtime_ranking_wired = :false "
                "AND automatic_model_activation = :false AND release_authorized = :false "
                "AND artifact_bindings = :artifact_bindings "
                "AND attribute_not_exists(review_receipt_sha256) "
                "AND attribute_not_exists(decision)"
            ),
            ExpressionAttributeNames={"#state": "state"},
            ExpressionAttributeValues=values,
            ReturnValues="ALL_NEW",
        )
    except Exception:
        observed = _get_run_item(dynamodb_client, run_table, run_id)
        if string_item_value(observed, "state") == RECORDED_REVIEW_STATE:
            return _recorded_review_response(
                item=observed,
                detail=detail,
                run_id=run_id,
            )
        raise
    if not isinstance(response, dict) or not isinstance(response.get("Attributes"), dict):
        raise RuntimeError("human review state transition returned no attributes")
    return _recorded_review_response(
        item=response["Attributes"],
        detail=detail,
        run_id=run_id,
    )


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
    action = str(detail.get("action") or TRAIN_ACTION)
    if action == REVIEW_ACTION:
        return _record_human_review(
            detail=detail,
            environment=environment,
            dynamodb_client=dynamodb_client,
        )
    if action != TRAIN_ACTION:
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
        artifact_hashes = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in artifacts.values()
        }
        if set(artifact_hashes) != EXPECTED_ARTIFACT_FILES:
            raise RuntimeError("training did not produce the exact six review artifacts")
        artifact_bindings: dict[str, dict[str, str]] = {}
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
                "IfNoneMatch": "*",
            }
            response = s3_client.put_object(**put_arguments)
            if not isinstance(response, dict):
                raise RuntimeError("artifact store returned an invalid response")
            version_id = response.get("VersionId")
            if not isinstance(version_id, str) or not version_id or version_id == "null":
                raise RuntimeError("artifact store did not return a version identifier")
            artifact_bindings[path.name] = {
                "key": key,
                "sha256": artifact_hashes[path.name],
                "version_id": version_id,
            }

        prefix = f"mlops/runs/{run_id}/"
        _transition_run_to_pending(
            dynamodb_client,
            run_table,
            run_id=run_id,
            source_mode=source_mode,
            artifact_prefix=prefix,
            artifact_bindings_json=canonical_json(artifact_bindings),
        )
        return {
            "run_id": run_id,
            "state": "TRAINED_PENDING_HUMAN_REVIEW",
            "artifact_prefix": prefix,
            "artifact_count": len(artifacts),
            "artifact_bindings": artifact_bindings,
            "runtime_ranking_wired": False,
            "automatic_model_activation": False,
            "release_authorized": False,
            "human_input_state": HUMAN_INPUT_NOT_RECORDED,
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
