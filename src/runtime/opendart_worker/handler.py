from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from app.opendart import OpenDartClient, OpenDartError, company_names_match
from app.opendart_results import (
    OpenDartResultError,
    build_refresh_result,
    put_refresh_result,
)


MESSAGE_SCHEMA_VERSION = "jcareer-opendart-refresh-request-v2"
CORP_CODE_PATTERN = re.compile(r"^[0-9]{8}$")
PERMANENT_PROVIDER_ERRORS = {
    "INVALID_CORP_CODE",
    "NO_DATA",
    "UPSTREAM_REJECTED",
}


class WorkerError(RuntimeError):
    def __init__(self, category: str, *, retryable: bool):
        super().__init__("OpenDART serverless worker request failed")
        self.category = category
        self.retryable = retryable


@dataclass(frozen=True)
class RefreshMessage:
    request_id: str
    company_id: str
    expected_company_name: str
    corp_code: str
    requested_at: datetime


def parse_message(raw_body: str) -> RefreshMessage:
    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, TypeError):
        raise WorkerError("INVALID_MESSAGE", retryable=False) from None
    expected = {
        "schema_version",
        "request_id",
        "company_id",
        "expected_company_name",
        "corp_code",
        "requested_at",
    }
    if not isinstance(payload, dict) or set(payload) != expected:
        raise WorkerError("INVALID_MESSAGE", retryable=False)
    if payload.get("schema_version") != MESSAGE_SCHEMA_VERSION:
        raise WorkerError("INVALID_MESSAGE_VERSION", retryable=False)
    try:
        request_id = str(uuid.UUID(payload["request_id"]))
        company_id = str(uuid.UUID(payload["company_id"]))
        requested_at = datetime.fromisoformat(payload["requested_at"])
    except (ValueError, TypeError, KeyError):
        raise WorkerError("INVALID_MESSAGE", retryable=False) from None
    if requested_at.tzinfo is None:
        raise WorkerError("INVALID_MESSAGE", retryable=False)
    corp_code = payload.get("corp_code")
    if not isinstance(corp_code, str) or not CORP_CODE_PATTERN.fullmatch(corp_code):
        raise WorkerError("INVALID_MESSAGE", retryable=False)
    expected_company_name = payload.get("expected_company_name")
    if not isinstance(expected_company_name, str):
        raise WorkerError("INVALID_MESSAGE", retryable=False)
    expected_company_name = " ".join(expected_company_name.split())
    if not expected_company_name or len(expected_company_name) > 120:
        raise WorkerError("INVALID_MESSAGE", retryable=False)
    return RefreshMessage(
        request_id=request_id,
        company_id=company_id,
        expected_company_name=expected_company_name,
        corp_code=corp_code,
        requested_at=requested_at.astimezone(timezone.utc),
    )


def read_opendart_api_key() -> str:
    parameter_name = os.getenv("OPENDART_API_KEY_PARAMETER_NAME", "").strip()
    if not parameter_name:
        raise WorkerError("KEY_CONFIGURATION", retryable=True)
    try:
        import boto3

        result = boto3.client(
            "ssm", region_name=os.getenv("AWS_REGION", "ap-northeast-2")
        ).get_parameter(Name=parameter_name, WithDecryption=True)
        key = result["Parameter"]["Value"]
    except Exception:
        raise WorkerError("KEY_UNAVAILABLE", retryable=True) from None
    if not isinstance(key, str) or len(key) != 40:
        raise WorkerError("KEY_CONFIGURATION", retryable=True)
    return key


def process_refresh_to_durable_result(
    message: RefreshMessage,
    *,
    client: OpenDartClient | None = None,
    client_factory: Callable[[], OpenDartClient] | None = None,
    result_writer: Callable[[dict[str, object]], str] | None = None,
) -> str:
    """Fetch public facts and record a bounded result without database access.

    The application tier remains the only writer to the company database. This
    keeps the Lambda outside the VPC, so it can reach OpenDART without a NAT
    Gateway or exposing PostgreSQL to a serverless security group.
    """

    if client is None:
        if client_factory is None:
            raise WorkerError("CLIENT_CONFIGURATION", retryable=True)
        client = client_factory()
    try:
        snapshot = client.refresh_company(message.corp_code)
    except OpenDartError as error:
        if error.category not in PERMANENT_PROVIDER_ERRORS:
            raise WorkerError(error.category, retryable=True) from None
        payload = build_refresh_result(
            request_id=message.request_id,
            company_id=message.company_id,
            corp_code=message.corp_code,
            requested_at=message.requested_at,
            outcome="NOT_UPDATED",
            snapshot=None,
            error_category=error.category,
        )
    else:
        dart_company = snapshot.get("company")
        dart_name = (
            str(dart_company.get("legal_name", ""))
            if isinstance(dart_company, dict)
            else ""
        )
        if not company_names_match(message.expected_company_name, dart_name):
            payload = build_refresh_result(
                request_id=message.request_id,
                company_id=message.company_id,
                corp_code=message.corp_code,
                requested_at=message.requested_at,
                outcome="NOT_UPDATED",
                snapshot=None,
                error_category="COMPANY_NAME_MISMATCH",
            )
        else:
            payload = build_refresh_result(
                request_id=message.request_id,
                company_id=message.company_id,
                corp_code=message.corp_code,
                requested_at=message.requested_at,
                outcome="UPDATED",
                snapshot=snapshot,
                error_category=None,
            )
    try:
        recorded = (result_writer or put_refresh_result)(payload)
    except OpenDartResultError:
        raise WorkerError("RESULT_STORE_UNAVAILABLE", retryable=True) from None
    if recorded == "ALREADY_RECORDED":
        return "ALREADY_RECORDED"
    return str(payload["outcome"])


def log_worker_outcome(
    *,
    message_id: object,
    outcome: str,
    category: str | None = None,
    retryable: bool | None = None,
) -> None:
    payload: dict[str, object] = {
        "schema_version": "jcareer-opendart-worker-log-v1",
        "event": "opendart_refresh_worker",
        "message_id": str(message_id),
        "outcome": outcome,
    }
    if category is not None:
        payload["category"] = category
    if retryable is not None:
        payload["retryable"] = retryable
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def lambda_handler(event: object, _context: object) -> dict[str, list[dict[str, str]]]:
    records = event.get("Records") if isinstance(event, dict) else None
    if not isinstance(records, list):
        log_worker_outcome(
            message_id="invalid-event",
            outcome="RETRY_REQUESTED",
            category="INVALID_EVENT",
            retryable=True,
        )
        return {"batchItemFailures": [{"itemIdentifier": "invalid-event"}]}
    failures: list[dict[str, str]] = []
    live_client: OpenDartClient | None = None

    def get_live_client() -> OpenDartClient:
        nonlocal live_client
        if live_client is None:
            live_client = OpenDartClient(
                mode="live",
                api_key=read_opendart_api_key(),
            )
        return live_client

    for index, record in enumerate(records):
        message_id = record.get("messageId", "unknown") if isinstance(record, dict) else "unknown"
        body = record.get("body") if isinstance(record, dict) else None
        try:
            message = parse_message(body)
            outcome = process_refresh_to_durable_result(
                message,
                client_factory=get_live_client,
            )
            log_worker_outcome(message_id=message_id, outcome=outcome)
        except WorkerError as error:
            log_worker_outcome(
                message_id=message_id,
                outcome=(
                    "RETRY_REQUESTED" if error.retryable else "DISCARDED_PERMANENTLY"
                ),
                category=error.category,
                retryable=error.retryable,
            )
            if error.retryable:
                # FIFO ordering: after the first retryable failure, report that
                # record and every unprocessed record in this batch.
                for remaining in records[index:]:
                    remaining_id = (
                        remaining.get("messageId", "unknown")
                        if isinstance(remaining, dict)
                        else "unknown"
                    )
                    failures.append({"itemIdentifier": str(remaining_id)})
                break
    return {"batchItemFailures": failures}
