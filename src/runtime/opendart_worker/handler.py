from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol

from app.opendart import OpenDartClient, OpenDartError, company_names_match


MESSAGE_SCHEMA_VERSION = "jcareer-opendart-refresh-request-v1"
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
    corp_code: str
    requested_at: datetime


class CompanySnapshotRepository(Protocol):
    def load_company(self, company_id: str) -> dict[str, object] | None: ...

    def complete(
        self,
        message: RefreshMessage,
        *,
        expected_company_name: str,
        snapshot: dict[str, object],
    ) -> bool: ...

    def record_failure(
        self,
        message: RefreshMessage,
        *,
        category: str,
        retryable: bool,
    ) -> None: ...


def parse_message(raw_body: str) -> RefreshMessage:
    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, TypeError):
        raise WorkerError("INVALID_MESSAGE", retryable=False) from None
    expected = {
        "schema_version",
        "request_id",
        "company_id",
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
    return RefreshMessage(
        request_id=request_id,
        company_id=company_id,
        corp_code=corp_code,
        requested_at=requested_at.astimezone(timezone.utc),
    )


class PostgresCompanySnapshotRepository:
    def __init__(self, database_url: str):
        if not database_url:
            raise WorkerError("DATABASE_CONFIGURATION", retryable=True)
        self._database_url = database_url.replace(
            "postgresql+psycopg://", "postgresql://", 1
        )

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row

            return psycopg.connect(
                self._database_url,
                connect_timeout=5,
                row_factory=dict_row,
            )
        except Exception:
            raise WorkerError("DATABASE_UNAVAILABLE", retryable=True) from None

    def load_company(self, company_id: str) -> dict[str, object] | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT name, opendart_pending_request_id, opendart_pending_requested_at
                FROM companies
                WHERE id = %s
                """,
                (company_id,),
            )
            return cursor.fetchone()

    def complete(
        self,
        message: RefreshMessage,
        *,
        expected_company_name: str,
        snapshot: dict[str, object],
    ) -> bool:
        from psycopg.types.json import Jsonb

        synced_at = datetime.now(timezone.utc)
        snapshot_version = f"opendart-snapshot-{str(snapshot['content_sha256'])[:12]}"
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE companies
                SET opendart_corp_code = %s,
                    opendart_snapshot = %s,
                    opendart_sync_state = 'AVAILABLE_LIVE',
                    opendart_snapshot_version = %s,
                    opendart_synced_at = %s,
                    opendart_last_attempt_at = %s,
                    opendart_pending_request_id = NULL,
                    opendart_pending_requested_at = NULL
                WHERE id = %s
                  AND name = %s
                  AND opendart_pending_request_id = %s
                  AND opendart_pending_requested_at <= %s
                """,
                (
                    message.corp_code,
                    Jsonb(snapshot),
                    snapshot_version,
                    synced_at,
                    synced_at,
                    message.company_id,
                    expected_company_name,
                    message.request_id,
                    message.requested_at,
                ),
            )
            return cursor.rowcount == 1

    def record_failure(
        self,
        message: RefreshMessage,
        *,
        category: str,
        retryable: bool,
    ) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE companies
                SET opendart_sync_state = CASE
                      WHEN COALESCE(opendart_snapshot::text, '{}') = '{}' THEN 'UNAVAILABLE_NO_SNAPSHOT'
                      WHEN %s THEN 'REFRESH_RETRY_PENDING'
                      ELSE 'STALE_LAST_KNOWN_GOOD'
                    END,
                    opendart_last_attempt_at = %s,
                    opendart_pending_request_id = CASE WHEN %s THEN opendart_pending_request_id ELSE NULL END,
                    opendart_pending_requested_at = CASE WHEN %s THEN opendart_pending_requested_at ELSE NULL END
                WHERE id = %s
                  AND opendart_pending_request_id = %s
                """,
                (
                    retryable,
                    datetime.now(timezone.utc),
                    retryable,
                    retryable,
                    message.company_id,
                    message.request_id,
                ),
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


def process_refresh(
    message: RefreshMessage,
    *,
    repository: CompanySnapshotRepository,
    client: OpenDartClient | None = None,
    client_factory: Callable[[], OpenDartClient] | None = None,
) -> str:
    company = repository.load_company(message.company_id)
    if not company:
        raise WorkerError("COMPANY_NOT_FOUND", retryable=False)
    pending_id = company.get("opendart_pending_request_id")
    pending_at = company.get("opendart_pending_requested_at")
    if pending_id != message.request_id:
        return "STALE_REQUEST_IGNORED"
    if isinstance(pending_at, datetime):
        normalised_pending_at = (
            pending_at.replace(tzinfo=timezone.utc)
            if pending_at.tzinfo is None
            else pending_at.astimezone(timezone.utc)
        )
        if normalised_pending_at > message.requested_at:
            return "STALE_REQUEST_IGNORED"
    if client is None:
        if client_factory is None:
            raise WorkerError("CLIENT_CONFIGURATION", retryable=True)
        client = client_factory()
    try:
        snapshot = client.refresh_company(message.corp_code)
    except OpenDartError as error:
        retryable = error.category not in PERMANENT_PROVIDER_ERRORS
        repository.record_failure(
            message, category=error.category, retryable=retryable
        )
        if retryable:
            raise WorkerError(error.category, retryable=True) from None
        return "NOT_UPDATED"
    company_name = str(company.get("name", ""))
    dart_company = snapshot.get("company")
    dart_name = (
        str(dart_company.get("legal_name", ""))
        if isinstance(dart_company, dict)
        else ""
    )
    if not company_names_match(company_name, dart_name):
        repository.record_failure(
            message, category="COMPANY_NAME_MISMATCH", retryable=False
        )
        return "NOT_UPDATED"
    updated = repository.complete(
        message,
        expected_company_name=company_name,
        snapshot=snapshot,
    )
    return "UPDATED" if updated else "STALE_REQUEST_IGNORED"


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
    repository = PostgresCompanySnapshotRepository(
        os.getenv("COMPANY_DATABASE_URL", "")
    )
    live_client: OpenDartClient | None = None

    def get_live_client() -> OpenDartClient:
        nonlocal live_client
        if live_client is None:
            live_client = OpenDartClient(
                mode="live",
                api_key=read_opendart_api_key(),
            )
        return live_client

    for record in records:
        message_id = record.get("messageId", "unknown") if isinstance(record, dict) else "unknown"
        body = record.get("body") if isinstance(record, dict) else None
        try:
            message = parse_message(body)
            outcome = process_refresh(
                message,
                repository=repository,
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
                failures.append({"itemIdentifier": str(message_id)})
    return {"batchItemFailures": failures}
