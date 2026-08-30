#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src/runtime/api"))
sys.path.insert(0, str(ROOT / "src/runtime/opendart_worker"))

import handler as worker  # noqa: E402
from app.opendart import OpenDartClient, OpenDartError  # noqa: E402
from app.opendart_dispatch import build_refresh_message  # noqa: E402


FIXED_TIME = datetime(2026, 8, 28, 2, 3, 4, tzinfo=timezone.utc)
COMPANY_ID = "00000000-0000-0000-0000-000000""000001"
REQUEST_ID = "00000000-0000-0000-0000-000000""000002"


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
            expected_company_name="아크웨이브",
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
    assert message.expected_company_name == "아크웨이브"
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

    durable_results: list[dict[str, object]] = []

    def fake_result_writer(payload: dict[str, object]) -> str:
        durable_results.append(payload)
        return "RECORDED"

    durable_outcome = worker.process_refresh_to_durable_result(
        message,
        client=OpenDartClient(mode="fixture", clock=lambda: FIXED_TIME),
        result_writer=fake_result_writer,
    )
    assert durable_outcome == "UPDATED"
    assert durable_results[0]["company_id"] == COMPANY_ID
    assert durable_results[0]["snapshot"]["score_effect"] == "NONE"
    checks += 1

    mismatch_message = worker.RefreshMessage(
        request_id=message.request_id,
        company_id=message.company_id,
        expected_company_name="다른기업",
        corp_code=message.corp_code,
        requested_at=message.requested_at,
    )
    durable_results.clear()
    assert worker.process_refresh_to_durable_result(
        mismatch_message,
        client=OpenDartClient(mode="fixture", clock=lambda: FIXED_TIME),
        result_writer=fake_result_writer,
    ) == "NOT_UPDATED"
    assert durable_results[0]["error_category"] == "COMPANY_NAME_MISMATCH"
    assert durable_results[0]["snapshot"] is None
    checks += 1

    durable_results.clear()
    assert worker.process_refresh_to_durable_result(
        message,
        client=RaisingClient("NO_DATA"),
        result_writer=fake_result_writer,
    ) == "NOT_UPDATED"
    assert durable_results[0]["error_category"] == "NO_DATA"
    expect_worker_error(
        lambda: worker.process_refresh_to_durable_result(
            message,
            client=RaisingClient("RATE_LIMITED"),
            result_writer=fake_result_writer,
        ),
        "RATE_LIMITED",
        True,
    )
    checks += 2

    original_result_writer = worker.put_refresh_result
    original_key_reader = worker.read_opendart_api_key
    original_client = worker.OpenDartClient
    key_reads = 0

    def fake_key_reader() -> str:
        nonlocal key_reads
        key_reads += 1
        return "k" * 40

    try:
        worker.put_refresh_result = fake_result_writer
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
        worker.put_refresh_result = original_result_writer
        worker.read_opendart_api_key = original_key_reader
        worker.OpenDartClient = original_client
    checks += 1

    retryable_client = RaisingClient("RATE_LIMITED")
    try:
        worker.read_opendart_api_key = lambda: "k" * 40
        worker.OpenDartClient = lambda **_kwargs: retryable_client
        with contextlib.redirect_stdout(io.StringIO()):
            retry_result = worker.lambda_handler(
                {
                    "Records": [
                        {"messageId": "retry-first", "body": valid_body()},
                        {"messageId": "not-processed", "body": valid_body()},
                    ]
                },
                None,
            )
        assert retry_result == {
            "batchItemFailures": [
                {"itemIdentifier": "retry-first"},
                {"itemIdentifier": "not-processed"},
            ]
        }
        assert retryable_client.calls == 1
    finally:
        worker.read_opendart_api_key = original_key_reader
        worker.OpenDartClient = original_client
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
