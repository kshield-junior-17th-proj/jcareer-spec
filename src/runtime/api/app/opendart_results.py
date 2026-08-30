from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Callable


RESULT_SCHEMA_VERSION = "jcareer-opendart-refresh-result-v1"
RESULT_TTL_SECONDS = 3600
RESULT_MAX_BYTES = 220_000
ALLOWED_OUTCOMES = {"UPDATED", "NOT_UPDATED"}
ALLOWED_ERROR_CATEGORIES = {
    None,
    "NO_DATA",
    "UPSTREAM_REJECTED",
    "COMPANY_NAME_MISMATCH",
}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class OpenDartResultError(RuntimeError):
    """Safe durable-result error without SDK request, key, or identifier detail."""


class OpenDartResultExpired(OpenDartResultError):
    """The result passed its application-enforced expiry boundary."""


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _content_hash(payload: dict[str, object]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def build_refresh_result(
    *,
    request_id: str,
    company_id: str,
    corp_code: str,
    requested_at: datetime,
    outcome: str,
    snapshot: dict[str, object] | None,
    error_category: str | None,
    completed_at: datetime | None = None,
) -> dict[str, object]:
    if outcome not in ALLOWED_OUTCOMES:
        raise OpenDartResultError("OpenDART result outcome is invalid")
    if error_category not in ALLOWED_ERROR_CATEGORIES:
        raise OpenDartResultError("OpenDART result category is invalid")
    if outcome == "UPDATED" and (not isinstance(snapshot, dict) or error_category):
        raise OpenDartResultError("OpenDART updated result is incomplete")
    if outcome == "NOT_UPDATED" and (snapshot is not None or not error_category):
        raise OpenDartResultError("OpenDART non-updated result is incomplete")
    moment = (completed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    payload: dict[str, object] = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "request_id": str(uuid.UUID(request_id)),
        "company_id": str(uuid.UUID(company_id)),
        "corp_code": corp_code,
        "requested_at": requested_at.astimezone(timezone.utc).isoformat(),
        "completed_at": moment.isoformat(),
        "outcome": outcome,
        "error_category": error_category,
        "snapshot": snapshot,
    }
    payload["content_sha256"] = _content_hash(payload)
    if len(_canonical_json(payload).encode("utf-8")) > RESULT_MAX_BYTES:
        raise OpenDartResultError("OpenDART result exceeds the durable-result limit")
    return payload


def validate_refresh_result(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise OpenDartResultError("OpenDART result format is invalid")
    expected = {
        "schema_version",
        "request_id",
        "company_id",
        "corp_code",
        "requested_at",
        "completed_at",
        "outcome",
        "error_category",
        "snapshot",
        "content_sha256",
    }
    if set(payload) != expected or payload.get("schema_version") != RESULT_SCHEMA_VERSION:
        raise OpenDartResultError("OpenDART result schema is invalid")
    try:
        uuid.UUID(str(payload["request_id"]))
        uuid.UUID(str(payload["company_id"]))
        requested_at = datetime.fromisoformat(str(payload["requested_at"]))
        completed_at = datetime.fromisoformat(str(payload["completed_at"]))
    except (ValueError, TypeError, KeyError):
        raise OpenDartResultError("OpenDART result identity is invalid") from None
    if requested_at.tzinfo is None or completed_at.tzinfo is None:
        raise OpenDartResultError("OpenDART result time is invalid")
    corp_code = payload.get("corp_code")
    if not isinstance(corp_code, str) or not re.fullmatch(r"[0-9]{8}", corp_code):
        raise OpenDartResultError("OpenDART result corporation code is invalid")
    outcome = payload.get("outcome")
    error_category = payload.get("error_category")
    snapshot = payload.get("snapshot")
    if outcome not in ALLOWED_OUTCOMES or error_category not in ALLOWED_ERROR_CATEGORIES:
        raise OpenDartResultError("OpenDART result state is invalid")
    if outcome == "UPDATED":
        if not isinstance(snapshot, dict) or error_category is not None:
            raise OpenDartResultError("OpenDART updated result is incomplete")
    elif snapshot is not None or error_category is None:
        raise OpenDartResultError("OpenDART non-updated result is incomplete")
    supplied_hash = payload.get("content_sha256")
    unhashed = {key: value for key, value in payload.items() if key != "content_sha256"}
    if not isinstance(supplied_hash, str) or not SHA256_PATTERN.fullmatch(supplied_hash):
        raise OpenDartResultError("OpenDART result hash is invalid")
    if not hmac.compare_digest(supplied_hash, _content_hash(unhashed)):
        raise OpenDartResultError("OpenDART result hash does not match")
    if len(_canonical_json(payload).encode("utf-8")) > RESULT_MAX_BYTES:
        raise OpenDartResultError("OpenDART result exceeds the durable-result limit")
    return payload


def put_refresh_result(
    payload: dict[str, object],
    *,
    writer_factory: Callable[[], object] | None = None,
) -> str:
    table_name = os.getenv("OPENDART_RESULT_TABLE", "").strip()
    if not table_name:
        raise OpenDartResultError("OpenDART result store is not configured")
    result = validate_refresh_result(payload)
    try:
        ttl_seconds = int(os.getenv("OPENDART_RESULT_TTL_SECONDS", str(RESULT_TTL_SECONDS)))
    except ValueError:
        raise OpenDartResultError("OpenDART result TTL is invalid") from None
    if ttl_seconds < 900 or ttl_seconds > 86400:
        raise OpenDartResultError("OpenDART result TTL is invalid")
    ttl = int(datetime.now(timezone.utc).timestamp()) + ttl_seconds
    try:
        if writer_factory is None:
            import boto3

            writer = boto3.client(
                "dynamodb", region_name=os.getenv("AWS_REGION", "ap-northeast-2")
            )
        else:
            writer = writer_factory()
        writer.put_item(
            TableName=table_name,
            Item={
                "request_id": {"S": str(result["request_id"])},
                "company_id": {"S": str(result["company_id"])},
                "payload": {"S": _canonical_json(result)},
                "expires_at": {"N": str(ttl)},
            },
            ConditionExpression="attribute_not_exists(request_id)",
        )
    except Exception as error:
        response = getattr(error, "response", None)
        code = (
            response.get("Error", {}).get("Code")
            if isinstance(response, dict)
            else None
        )
        if code == "ConditionalCheckFailedException":
            return "ALREADY_RECORDED"
        raise OpenDartResultError("OpenDART result could not be recorded") from None
    return "RECORDED"


def get_refresh_result(
    request_id: str,
    *,
    reader_factory: Callable[[], object] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, object] | None:
    broker_socket = os.getenv("OPENDART_AWS_BROKER_SOCKET", "").strip()
    table_name = (
        "broker-configured-opendart-results"
        if broker_socket
        else os.getenv("OPENDART_RESULT_TABLE", "").strip()
    )
    if not table_name:
        raise OpenDartResultError("OpenDART result store is not configured")
    request_id = str(uuid.UUID(request_id))
    try:
        if reader_factory is None:
            if broker_socket:
                from .aws_broker_client import OpenDartBrokerDynamoClient

                reader = OpenDartBrokerDynamoClient()
            else:
                import boto3

                reader = boto3.client(
                    "dynamodb", region_name=os.getenv("AWS_REGION", "ap-northeast-2")
                )
        else:
            reader = reader_factory()
        response = reader.get_item(
            TableName=table_name,
            Key={"request_id": {"S": request_id}},
            ConsistentRead=True,
            ProjectionExpression="#request_id, #company_id, #payload, #expires_at",
            ExpressionAttributeNames={
                "#request_id": "request_id",
                "#company_id": "company_id",
                "#payload": "payload",
                "#expires_at": "expires_at",
            },
        )
    except Exception:
        raise OpenDartResultError("OpenDART result could not be read") from None
    item = response.get("Item") if isinstance(response, dict) else None
    if not isinstance(item, dict):
        return None
    try:
        payload_text = item["payload"]["S"]
        company_id = item["company_id"]["S"]
        expires_at_text = item["expires_at"]["N"]
        if not isinstance(payload_text, str) or len(payload_text.encode("utf-8")) > RESULT_MAX_BYTES:
            raise ValueError
        if not isinstance(expires_at_text, str) or not re.fullmatch(r"[0-9]{1,20}", expires_at_text):
            raise ValueError
        expires_at = int(expires_at_text)
        payload = validate_refresh_result(json.loads(payload_text))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OpenDartResultError):
        raise OpenDartResultError("OpenDART stored result is invalid") from None
    if payload["request_id"] != request_id or payload["company_id"] != company_id:
        raise OpenDartResultError("OpenDART stored result binding is invalid")
    observed_at = (clock or (lambda: datetime.now(timezone.utc)))()
    if observed_at.tzinfo is None:
        raise OpenDartResultError("OpenDART result clock is invalid")
    if expires_at <= int(observed_at.astimezone(timezone.utc).timestamp()):
        raise OpenDartResultExpired("OpenDART stored result has expired")
    return payload


def delete_refresh_result(
    request_id: str,
    company_id: str,
    *,
    deleter_factory: Callable[[], object] | None = None,
) -> None:
    broker_socket = os.getenv("OPENDART_AWS_BROKER_SOCKET", "").strip()
    table_name = (
        "broker-configured-opendart-results"
        if broker_socket
        else os.getenv("OPENDART_RESULT_TABLE", "").strip()
    )
    if not table_name:
        raise OpenDartResultError("OpenDART result store is not configured")
    request_id = str(uuid.UUID(request_id))
    company_id = str(uuid.UUID(company_id))
    try:
        if deleter_factory is None:
            if broker_socket:
                from .aws_broker_client import OpenDartBrokerDynamoClient

                deleter = OpenDartBrokerDynamoClient()
            else:
                import boto3

                deleter = boto3.client(
                    "dynamodb", region_name=os.getenv("AWS_REGION", "ap-northeast-2")
                )
        else:
            deleter = deleter_factory()
        deleter.delete_item(
            TableName=table_name,
            Key={"request_id": {"S": request_id}},
            ConditionExpression="company_id = :company_id",
            ExpressionAttributeValues={":company_id": {"S": company_id}},
        )
    except Exception as error:
        response = getattr(error, "response", None)
        code = (
            response.get("Error", {}).get("Code")
            if isinstance(response, dict)
            else None
        )
        if code == "ConditionalCheckFailedException":
            raise OpenDartResultError("OpenDART result ownership does not match") from None
        raise OpenDartResultError("OpenDART result could not be removed") from None
