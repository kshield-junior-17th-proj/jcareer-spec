#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src/runtime/api"))

from app.opendart import OpenDartClient  # noqa: E402
from app.opendart_results import (  # noqa: E402
    OpenDartResultExpired,
    OpenDartResultError,
    build_refresh_result,
    delete_refresh_result,
    get_refresh_result,
    put_refresh_result,
    validate_refresh_result,
)


FIXED_TIME = datetime(2026, 8, 29, 1, 2, 3, tzinfo=timezone.utc)
REQUEST_ID = "00000000-0000-0000-0000-000000""000002"
COMPANY_ID = "00000000-0000-0000-0000-000000""000001"


class ConditionalFailure(RuntimeError):
    response = {"Error": {"Code": "ConditionalCheckFailedException"}}


class FakeDynamo:
    def __init__(self) -> None:
        self.item: dict[str, object] | None = None
        self.deleted = False
        self.fail_duplicate = False

    def put_item(self, **kwargs: object) -> None:
        if self.fail_duplicate:
            raise ConditionalFailure
        self.item = kwargs["Item"]

    def get_item(self, **_kwargs: object) -> dict[str, object]:
        return {"Item": self.item} if self.item is not None else {}

    def delete_item(self, **_kwargs: object) -> None:
        self.deleted = True


def expect_result_error(callable_object) -> None:
    try:
        callable_object()
    except OpenDartResultError:
        return
    raise AssertionError("expected OpenDartResultError")


def main() -> None:
    checks = 0
    previous_table = os.environ.get("OPENDART_RESULT_TABLE")
    os.environ["OPENDART_RESULT_TABLE"] = "synthetic-opendart-results"

    snapshot = OpenDartClient(mode="fixture", clock=lambda: FIXED_TIME).refresh_company(
        "90000001"
    )
    result = build_refresh_result(
        request_id=REQUEST_ID,
        company_id=COMPANY_ID,
        corp_code="90000001",
        requested_at=FIXED_TIME,
        completed_at=FIXED_TIME,
        outcome="UPDATED",
        snapshot=snapshot,
        error_category=None,
    )
    assert validate_refresh_result(result) == result
    checks += 1

    tampered = {**result, "corp_code": "90000002"}
    expect_result_error(lambda: validate_refresh_result(tampered))
    checks += 1

    fake = FakeDynamo()
    assert put_refresh_result(result, writer_factory=lambda: fake) == "RECORDED"
    assert fake.item is not None
    stored_text = fake.item["payload"]["S"]
    assert "api_key" not in stored_text.lower()
    assert json.loads(stored_text)["snapshot"]["score_effect"] == "NONE"
    checks += 1

    loaded = get_refresh_result(REQUEST_ID, reader_factory=lambda: fake)
    assert loaded == result
    checks += 1

    expired = FakeDynamo()
    expired.item = {key: dict(value) for key, value in fake.item.items()}
    expired.item["expires_at"] = {"N": str(int(FIXED_TIME.timestamp()))}
    try:
        get_refresh_result(
            REQUEST_ID,
            reader_factory=lambda: expired,
            clock=lambda: FIXED_TIME + timedelta(seconds=1),
        )
    except OpenDartResultExpired:
        pass
    else:
        raise AssertionError("expected OpenDartResultExpired")
    checks += 1

    delete_refresh_result(REQUEST_ID, COMPANY_ID, deleter_factory=lambda: fake)
    assert fake.deleted is True
    checks += 1

    fake.fail_duplicate = True
    assert put_refresh_result(result, writer_factory=lambda: fake) == "ALREADY_RECORDED"
    checks += 1

    permanent = build_refresh_result(
        request_id=REQUEST_ID,
        company_id=COMPANY_ID,
        corp_code="90000001",
        requested_at=FIXED_TIME,
        completed_at=FIXED_TIME,
        outcome="NOT_UPDATED",
        snapshot=None,
        error_category="NO_DATA",
    )
    assert validate_refresh_result(permanent)["snapshot"] is None
    checks += 1

    os.environ.pop("OPENDART_RESULT_TABLE", None)
    expect_result_error(lambda: put_refresh_result(result, writer_factory=lambda: fake))
    checks += 1
    if previous_table is not None:
        os.environ["OPENDART_RESULT_TABLE"] = previous_table

    print(f"OpenDART durable result contract: PASS ({checks}/{checks})")


if __name__ == "__main__":
    main()
