#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src/runtime/api"))
sys.path.insert(0, str(ROOT / "src/runtime/opendart_worker"))

import handler as worker  # noqa: E402
from app.opendart import OpenDartClient, OpenDartError  # noqa: E402
from app.opendart_dispatch import build_refresh_message  # noqa: E402


FIXED_TIME = datetime(2026, 8, 28, 2, 3, 4, tzinfo=timezone.utc)
COMPANY_ID = "00000000-0000-0000-0000-aaaaaaaaaaaa"
REQUEST_ID = "00000000-0000-0000-0000-bbbbbbbbbbbb"


class FakeRepository:
    def __init__(
        self,
        *,
        name: str = "아크웨이브",
        pending_id: str = REQUEST_ID,
        pending_at: datetime = FIXED_TIME,
        complete_result: bool = True,
    ) -> None:
        self.company = {
            "name": name,
            "opendart_pending_request_id": pending_id,
            "opendart_pending_requested_at": pending_at,
        }
        self.complete_result = complete_result
        self.completed: list[dict[str, object]] = []
        self.failures: list[dict[str, object]] = []

    def load_company(self, _company_id: str) -> dict[str, object] | None:
        return self.company

    def complete(
        self,
        message: worker.RefreshMessage,
        *,
        expected_company_name: str,
        snapshot: dict[str, object],
    ) -> bool:
        self.completed.append(
            {
                "message": message,
                "expected_company_name": expected_company_name,
                "snapshot": snapshot,
            }
        )
        return self.complete_result

    def record_failure(
        self,
        message: worker.RefreshMessage,
        *,
        category: str,
        retryable: bool,
    ) -> None:
        self.failures.append(
            {
                "message": message,
                "category": category,
                "retryable": retryable,
            }
        )


class RaisingClient:
    def __init__(self, category: str) -> None:
        self.category = category
        self.calls = 0

    def refresh_company(self, _corp_code: str) -> dict[str, object]:
        self.calls += 1
        raise OpenDartError(self.category, "safe synthetic failure")


def expect_worker_error(callable_object, category: str, retryable: bool) -> None:
    try:
        callable_object()
    except worker.WorkerError as error:
        assert error.category == category
        assert error.retryable is retryable
    else:
        raise AssertionError(f"expected WorkerError {category}")


def valid_body() -> str:
    return json.dumps(
        build_refresh_message(
            company_id=COMPANY_ID,
            corp_code="90000001",
            requested_at=FIXED_TIME,
            request_id=REQUEST_ID,
        )
    )


def main() -> None:
    checks = 0

    message = worker.parse_message(valid_body())
    assert message.request_id == REQUEST_ID
    assert message.company_id == COMPANY_ID
    assert message.requested_at == FIXED_TIME
    checks += 1

    expect_worker_error(lambda: worker.parse_message("not-json"), "INVALID_MESSAGE", False)
    wrong_version = json.loads(valid_body())
    wrong_version["schema_version"] = "unknown"
    expect_worker_error(
        lambda: worker.parse_message(json.dumps(wrong_version)),
        "INVALID_MESSAGE_VERSION",
        False,
    )
    extra_field = json.loads(valid_body())
    extra_field["api_key"] = "must-not-be-accepted"
    expect_worker_error(
        lambda: worker.parse_message(json.dumps(extra_field)), "INVALID_MESSAGE", False
    )
    naive_time = json.loads(valid_body())
    naive_time["requested_at"] = "2026-08-28T02:03:04"
    expect_worker_error(
        lambda: worker.parse_message(json.dumps(naive_time)), "INVALID_MESSAGE", False
    )
    checks += 4

    repository = FakeRepository()
    outcome = worker.process_refresh(
        message,
        repository=repository,
        client=OpenDartClient(mode="fixture", clock=lambda: FIXED_TIME),
    )
    assert outcome == "UPDATED"
    assert len(repository.completed) == 1
    assert repository.completed[0]["snapshot"]["synthetic"] is True
    checks += 1

    factory_calls = 0

    def forbidden_factory() -> OpenDartClient:
        nonlocal factory_calls
        factory_calls += 1
        raise AssertionError("stale requests must not read a key or construct a client")

    stale_repository = FakeRepository(
        pending_id="00000000-0000-0000-0000-cccccccccccc"
    )
    assert (
        worker.process_refresh(
            message,
            repository=stale_repository,
            client_factory=forbidden_factory,
        )
        == "STALE_REQUEST_IGNORED"
    )
    newer_repository = FakeRepository(pending_at=FIXED_TIME + timedelta(seconds=1))
    assert (
        worker.process_refresh(
            message,
            repository=newer_repository,
            client_factory=forbidden_factory,
        )
        == "STALE_REQUEST_IGNORED"
    )
    assert factory_calls == 0
    checks += 2

    mismatch_repository = FakeRepository(name="다른기업")
    assert (
        worker.process_refresh(
            message,
            repository=mismatch_repository,
            client=OpenDartClient(mode="fixture", clock=lambda: FIXED_TIME),
        )
        == "NOT_UPDATED"
    )
    assert mismatch_repository.failures[0]["category"] == "COMPANY_NAME_MISMATCH"
    assert mismatch_repository.failures[0]["retryable"] is False
    checks += 1

    permanent_repository = FakeRepository()
    permanent_client = RaisingClient("NO_DATA")
    assert (
        worker.process_refresh(
            message,
            repository=permanent_repository,
            client=permanent_client,
        )
        == "NOT_UPDATED"
    )
    assert permanent_repository.failures[0]["retryable"] is False
    checks += 1

    retry_repository = FakeRepository()
    retry_client = RaisingClient("RATE_LIMITED")
    expect_worker_error(
        lambda: worker.process_refresh(
            message,
            repository=retry_repository,
            client=retry_client,
        ),
        "RATE_LIMITED",
        True,
    )
    assert retry_repository.failures[0]["retryable"] is True
    checks += 1

    raced_repository = FakeRepository(complete_result=False)
    assert (
        worker.process_refresh(
            message,
            repository=raced_repository,
            client=OpenDartClient(mode="fixture", clock=lambda: FIXED_TIME),
        )
        == "STALE_REQUEST_IGNORED"
    )
    checks += 1

    original_repository = worker.PostgresCompanySnapshotRepository
    original_key_reader = worker.read_opendart_api_key
    original_client = worker.OpenDartClient
    lambda_repository = FakeRepository()
    key_reads = 0

    def fake_key_reader() -> str:
        nonlocal key_reads
        key_reads += 1
        return "k" * 40

    try:
        worker.PostgresCompanySnapshotRepository = lambda _url: lambda_repository
        worker.read_opendart_api_key = fake_key_reader
        worker.OpenDartClient = (
            lambda **_kwargs: OpenDartClient(mode="fixture", clock=lambda: FIXED_TIME)
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = worker.lambda_handler(
                {
                    "Records": [
                        {"messageId": "synthetic-valid", "body": valid_body()},
                        {"messageId": "synthetic-invalid", "body": "not-json"},
                    ]
                },
                None,
            )
        assert result == {"batchItemFailures": []}
        assert key_reads == 1
        logs = [json.loads(line) for line in output.getvalue().splitlines()]
        assert [row["outcome"] for row in logs] == [
            "UPDATED",
            "DISCARDED_PERMANENTLY",
        ]
        assert all("company_id" not in row and "corp_code" not in row for row in logs)
    finally:
        worker.PostgresCompanySnapshotRepository = original_repository
        worker.read_opendart_api_key = original_key_reader
        worker.OpenDartClient = original_client
    checks += 1

    stale_lambda_repository = FakeRepository(
        pending_id="00000000-0000-0000-0000-cccccccccccc"
    )
    try:
        worker.PostgresCompanySnapshotRepository = lambda _url: stale_lambda_repository
        worker.read_opendart_api_key = (
            lambda: (_ for _ in ()).throw(
                AssertionError("stale Lambda message must not read SSM")
            )
        )
        with contextlib.redirect_stdout(io.StringIO()):
            stale_result = worker.lambda_handler(
                {"Records": [{"messageId": "synthetic-stale", "body": valid_body()}]},
                None,
            )
        assert stale_result == {"batchItemFailures": []}
    finally:
        worker.PostgresCompanySnapshotRepository = original_repository
        worker.read_opendart_api_key = original_key_reader
    checks += 1

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        invalid_event = worker.lambda_handler([], None)
    assert invalid_event == {
        "batchItemFailures": [{"itemIdentifier": "invalid-event"}]
    }
    assert json.loads(output.getvalue())["category"] == "INVALID_EVENT"
    checks += 1

    print(f"OpenDART serverless worker contract: PASS ({checks}/{checks})")


if __name__ == "__main__":
    main()
