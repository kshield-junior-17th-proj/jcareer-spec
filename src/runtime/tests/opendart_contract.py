#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src/runtime/api"))

from app.opendart import (  # noqa: E402
    MAX_RESPONSE_BYTES,
    OpenDartClient,
    OpenDartError,
    company_names_match,
    public_snapshot,
)
from app.opendart_dispatch import (  # noqa: E402
    OpenDartDispatchError,
    build_refresh_message,
    enqueue_refresh,
)


FIXED_TIME = datetime(2026, 8, 28, 1, 2, 3, tzinfo=timezone.utc)
SYNTHETIC_KEY = "k" * 40
SENSITIVE_KEYS = {
    "ceo_nm",
    "jurir_no",
    "bizr_no",
    "adres",
    "phn_no",
    "fax_no",
    "hm_url",
    "ir_url",
    "crtfc_key",
}


def expect_error(callable_object, category: str) -> OpenDartError:
    try:
        callable_object()
    except OpenDartError as error:
        assert error.category == category, (error.category, category)
        assert SYNTHETIC_KEY not in str(error)
        return error
    raise AssertionError(f"expected OpenDartError {category}")


def recursive_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for child in value.values():
            keys.update(recursive_keys(child))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for child in value:
            keys.update(recursive_keys(child))
        return keys
    return set()


def response(payload: object, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"content-type": "application/json"},
    )


def main() -> None:
    checks = 0

    fixture_client = OpenDartClient(mode="fixture", clock=lambda: FIXED_TIME)
    fixture = fixture_client.refresh_company("90000001")
    assert fixture["synthetic"] is True
    assert fixture["score_effect"] == "NONE"
    assert fixture["retrieved_at"] == FIXED_TIME.isoformat()
    assert not (recursive_keys(fixture) & SENSITIVE_KEYS)
    assert public_snapshot(fixture)["company"]["legal_name"] == "아크웨이브"
    checks += 1

    expect_error(lambda: fixture_client.refresh_company("9000000"), "INVALID_CORP_CODE")
    expect_error(lambda: fixture_client.refresh_company("not-code"), "INVALID_CORP_CODE")
    expect_error(lambda: fixture_client.refresh_company("99999999"), "NO_DATA")
    expect_error(
        lambda: OpenDartClient(mode="disabled").refresh_company("90000001"),
        "DISABLED",
    )
    checks += 4

    called = False

    def should_not_call(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return response({"status": "000"})

    no_key_client = OpenDartClient(
        mode="live",
        api_key="short",
        transport=httpx.MockTransport(should_not_call),
        clock=lambda: FIXED_TIME,
    )
    expect_error(lambda: no_key_client.refresh_company("00123456"), "CONFIGURATION")
    assert called is False
    checks += 1

    requests: list[httpx.Request] = []

    def success_transport(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.host == "opendart.fss.or.kr"
        assert request.url.params.get("crtfc_key") == SYNTHETIC_KEY
        if request.url.path == "/api/company.json":
            return response(
                {
                    "status": "000",
                    "message": "정상",
                    "corp_name": "아크웨이브",
                    "corp_name_eng": "ARCWAVE",
                    "stock_name": "",
                    "stock_code": "",
                    "ceo_nm": "SHOULD_NOT_LEAVE_ADAPTER",
                    "corp_cls": "E",
                    "jurir_no": "SHOULD_NOT_LEAVE_ADAPTER",
                    "bizr_no": "SHOULD_NOT_LEAVE_ADAPTER",
                    "adres": "SHOULD_NOT_LEAVE_ADAPTER",
                    "hm_url": "https://untrusted.invalid",
                    "phn_no": "SHOULD_NOT_LEAVE_ADAPTER",
                    "fax_no": "SHOULD_NOT_LEAVE_ADAPTER",
                    "induty_code": "62010",
                    "est_dt": "20180412",
                    "acc_mt": "12",
                }
            )
        assert request.url.path == "/api/list.json"
        return response(
            {
                "status": "000",
                "message": "정상",
                "list": [
                    {
                        "corp_cls": "E",
                        "corp_name": "아크웨이브",
                        "corp_code": "00123456",
                        "report_nm": "사업보고서",
                        "rcept_no": "20260331000001",
                        "flr_nm": "SHOULD_NOT_LEAVE_ADAPTER",
                        "rcept_dt": "20260331",
                        "rm": "",
                    }
                ],
            }
        )

    live_client = OpenDartClient(
        mode="live",
        api_key=SYNTHETIC_KEY,
        transport=httpx.MockTransport(success_transport),
        clock=lambda: FIXED_TIME,
    )
    live = live_client.refresh_company("00123456")
    assert len(requests) == 2
    assert live["synthetic"] is False
    assert live["company"]["legal_name"] == "아크웨이브"
    assert live["disclosures"]["items"][0]["report_name"] == "사업보고서"
    assert not (recursive_keys(live) & SENSITIVE_KEYS)
    assert SYNTHETIC_KEY not in json.dumps(live, ensure_ascii=False)
    checks += 1

    def no_data_transport(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/company.json":
            return success_transport(request)
        return response({"status": "013", "message": "조회된 데이타가 없습니다."})

    no_data = OpenDartClient(
        mode="live",
        api_key=SYNTHETIC_KEY,
        transport=httpx.MockTransport(no_data_transport),
        clock=lambda: FIXED_TIME,
    ).refresh_company("00123456")
    assert no_data["disclosures"] == {
        "state": "NO_DATA",
        "items": [],
        "error_category": None,
    }
    checks += 1

    def rate_limit_transport(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/company.json":
            return success_transport(request)
        return response(
            {
                "status": "020",
                "message": f"raw upstream secret {SYNTHETIC_KEY}",
            }
        )

    partial = OpenDartClient(
        mode="live",
        api_key=SYNTHETIC_KEY,
        transport=httpx.MockTransport(rate_limit_transport),
        clock=lambda: FIXED_TIME,
    ).refresh_company("00123456")
    assert partial["disclosures"]["state"] == "UNAVAILABLE"
    assert partial["disclosures"]["error_category"] == "RATE_LIMITED"
    assert SYNTHETIC_KEY not in json.dumps(partial, ensure_ascii=False)
    checks += 1

    for status, category in (
        ("010", "CONFIGURATION"),
        ("011", "CONFIGURATION"),
        ("012", "CONFIGURATION"),
        ("013", "NO_DATA"),
        ("014", "UPSTREAM_UNAVAILABLE"),
        ("020", "RATE_LIMITED"),
        ("021", "UPSTREAM_REJECTED"),
        ("100", "UPSTREAM_REJECTED"),
        ("101", "UPSTREAM_REJECTED"),
        ("800", "UPSTREAM_UNAVAILABLE"),
        ("900", "UPSTREAM_UNAVAILABLE"),
        ("901", "CONFIGURATION"),
        ("777", "UPSTREAM_UNAVAILABLE"),
    ):
        def status_transport(_: httpx.Request, status_value: str = status) -> httpx.Response:
            return response(
                {
                    "status": status_value,
                    "message": f"must not escape {SYNTHETIC_KEY}",
                }
            )

        client = OpenDartClient(
            mode="live",
            api_key=SYNTHETIC_KEY,
            transport=httpx.MockTransport(status_transport),
            clock=lambda: FIXED_TIME,
        )
        expect_error(lambda: client.refresh_company("00123456"), category)
    checks += 13

    malformed = OpenDartClient(
        mode="live",
        api_key=SYNTHETIC_KEY,
        transport=httpx.MockTransport(lambda _: response(["not", "an", "object"])),
        clock=lambda: FIXED_TIME,
    )
    expect_error(lambda: malformed.refresh_company("00123456"), "INVALID_RESPONSE")
    checks += 1

    oversized = OpenDartClient(
        mode="live",
        api_key=SYNTHETIC_KEY,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 1))
        ),
        clock=lambda: FIXED_TIME,
    )
    expect_error(lambda: oversized.refresh_company("00123456"), "INVALID_RESPONSE")
    checks += 1

    assert company_names_match("(주) 아크웨이브", "주식회사 아크웨이브")
    assert not company_names_match("아크웨이브", "모자이크웍스")
    checks += 1

    tampered = dict(fixture)
    tampered["ceo_nm"] = "must-not-leak"
    tampered["company"] = {**fixture["company"], "bizr_no": "must-not-leak"}
    projected = public_snapshot(tampered)
    assert projected is not None
    assert not (recursive_keys(projected) & SENSITIVE_KEYS)
    assert "must-not-leak" not in json.dumps(projected, ensure_ascii=False)
    assert "corp_code" not in projected
    checks += 1

    wrong_schema = {**fixture, "schema_version": "unknown"}
    assert public_snapshot(wrong_schema) is None
    missing_name = {
        **fixture,
        "company": {**fixture["company"], "legal_name": ""},
    }
    assert public_snapshot(missing_name) is None
    checks += 2

    message = build_refresh_message(
        company_id="00000000-0000-0000-0000-aaaaaaaaaaaa",
        corp_code="90000001",
        requested_at=FIXED_TIME,
        request_id="00000000-0000-0000-0000-bbbbbbbbbbbb",
    )
    assert set(message) == {
        "schema_version",
        "request_id",
        "company_id",
        "corp_code",
        "requested_at",
    }
    assert "api_key" not in json.dumps(message).lower()
    checks += 1

    class FakeQueue:
        def __init__(self) -> None:
            self.call: dict[str, str] | None = None

        def send_message(self, **kwargs: str) -> dict[str, str]:
            self.call = kwargs
            return {"MessageId": "synthetic-queue-message"}

    previous_queue = os.environ.get("OPENDART_REFRESH_QUEUE_URL")
    os.environ["OPENDART_REFRESH_QUEUE_URL"] = (
        "https://sqs.ap-northeast-2.amazonaws.com/ACCOUNT_ID/synthetic.fifo"
    )
    fake_queue = FakeQueue()
    queued = enqueue_refresh(message, sender_factory=lambda: fake_queue)
    assert queued["request_id"] == message["request_id"]
    assert fake_queue.call is not None
    assert json.loads(fake_queue.call["MessageBody"]) == message
    assert len(fake_queue.call["MessageGroupId"]) == 64
    assert len(fake_queue.call["MessageDeduplicationId"]) == 64
    checks += 1

    retried = enqueue_refresh(message, sender_factory=lambda: fake_queue)
    assert retried["deduplication_id"] == queued["deduplication_id"]
    checks += 1

    distinct_message = build_refresh_message(
        company_id=message["company_id"],
        corp_code=message["corp_code"],
        requested_at=FIXED_TIME,
        request_id="00000000-0000-0000-0000-cccccccccccc",
    )
    distinct = enqueue_refresh(distinct_message, sender_factory=lambda: fake_queue)
    assert distinct["deduplication_id"] != queued["deduplication_id"]
    checks += 1

    os.environ.pop("OPENDART_REFRESH_QUEUE_URL", None)
    try:
        enqueue_refresh(message, sender_factory=lambda: fake_queue)
    except OpenDartDispatchError as error:
        assert "queue" in str(error).lower() or "큐" in str(error)
    else:
        raise AssertionError("missing queue URL must fail closed")
    checks += 1
    if previous_queue is not None:
        os.environ["OPENDART_REFRESH_QUEUE_URL"] = previous_queue

    print(f"OpenDART adapter contract: PASS ({checks}/{checks})")


if __name__ == "__main__":
    main()
