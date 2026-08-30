#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src/runtime/api"))
FIXED_TIME = datetime(2026, 8, 29, 1, 2, 3, tzinfo=timezone.utc)


def recursive_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        result = set(value)
        for child in value.values():
            result.update(recursive_keys(child))
        return result
    if isinstance(value, list):
        result: set[str] = set()
        for child in value:
            result.update(recursive_keys(child))
        return result
    return set()


def main() -> None:
    checks = 0
    with tempfile.TemporaryDirectory(prefix="jcareer-opendart-") as temporary:
        root = Path(temporary)
        os.environ["MEMBER_DATABASE_URL"] = f"sqlite:///{root / 'member.db'}"
        os.environ["COMPANY_DATABASE_URL"] = f"sqlite:///{root / 'company.db'}"
        os.environ["OUTCOME_DATABASE_URL"] = f"sqlite:///{root / 'outcome.db'}"
        os.environ["AUTO_SEED"] = "true"
        os.environ["OPENDART_MODE"] = "fixture"
        os.environ.pop("OPENDART_API_KEY", None)

        from fastapi.testclient import TestClient

        from app import main as api_main
        from app.opendart import _canonical_hash
        from app.opendart_results import OpenDartResultExpired, build_refresh_result

        @contextmanager
        def managed_client():
            try:
                with TestClient(api_main.app) as active_client:
                    yield active_client
            finally:
                api_main.member_engine.dispose()
                api_main.company_engine.dispose()
                api_main.outcome_engine.dispose()

        with managed_client() as client:
            def login(email: str) -> str:
                result = client.post(
                    "/api/v1/auth/login",
                    json={"email": email, "password": "Demo123!"},
                )
                assert result.status_code == 200, result.text
                return result.json()["access_token"]

            recruiter_token = login("recruiter@jcareer.test")
            other_recruiter_token = login("recruiter-beta@jcareer.test")
            candidate_token = login("candidate@jcareer.test")
            recruiter_headers = {"Authorization": f"Bearer {recruiter_token}"}
            other_headers = {"Authorization": f"Bearer {other_recruiter_token}"}
            candidate_headers = {"Authorization": f"Bearer {candidate_token}"}

            jobs = client.get("/api/v1/jobs")
            assert jobs.status_code == 200
            public_profile = jobs.json()[0]["company_profile"]
            public_dart = public_profile["opendart"]
            assert "corp_code" not in public_dart
            assert "last_attempt_at" not in public_dart
            assert public_dart["snapshot"]["synthetic"] is True
            assert public_dart["score_effect"] == "NONE"
            assert not (
                recursive_keys(public_dart)
                & {"ceo_nm", "jurir_no", "bizr_no", "phn_no", "fax_no"}
            )
            checks += 1

            recruiter_profile = client.get(
                "/api/v1/recruiter/company-profile", headers=recruiter_headers
            )
            assert recruiter_profile.status_code == 200
            assert recruiter_profile.json()["opendart"]["corp_code"] == "90000001"
            assert "last_attempt_at" in recruiter_profile.json()["opendart"]
            checks += 1

            refreshed = client.post(
                "/api/v1/recruiter/company-profile/opendart/refresh",
                headers=recruiter_headers,
                json={"corp_code": "90000001"},
            )
            assert refreshed.status_code == 202, refreshed.text
            assert refreshed.json()["refresh"]["state"] == "UPDATED_SYNTHETIC_FIXTURE"
            refreshed_profile = refreshed.json()["company_profile"]
            assert refreshed_profile["opendart"]["state"] == "AVAILABLE_SYNTHETIC_FIXTURE"
            assert refreshed_profile["opendart"]["snapshot"]["company"]["legal_name"] == "아크웨이브"
            assert "api_key" not in json.dumps(refreshed.json(), ensure_ascii=False).lower()
            checks += 1

            original_enqueue = api_main.enqueue_refresh
            queued_messages: list[dict[str, str]] = []

            def fake_enqueue(message: dict[str, str]) -> dict[str, str]:
                with api_main.company_engine.connect() as connection:
                    persisted = connection.exec_driver_sql(
                        "SELECT opendart_sync_state, opendart_pending_request_id "
                        "FROM companies WHERE id = ?",
                        (message["company_id"],),
                    ).mappings().one()
                assert persisted["opendart_sync_state"] == "REFRESH_DISPATCH_PENDING"
                assert persisted["opendart_pending_request_id"] == message["request_id"]
                queued_messages.append(message)
                return {
                    "request_id": message["request_id"],
                    "queue_message_id": "synthetic-message",
                    "deduplication_id": "d" * 64,
                }

            api_main.enqueue_refresh = fake_enqueue
            os.environ["OPENDART_DISPATCH_MODE"] = "serverless_queue"
            queued = client.post(
                "/api/v1/recruiter/company-profile/opendart/refresh",
                headers=recruiter_headers,
                json={"corp_code": "90000001"},
            )
            api_main.enqueue_refresh = original_enqueue
            assert queued.status_code == 202, queued.text
            assert queued.json()["refresh"]["state"] == "QUEUED"
            assert queued.json()["company_profile"]["opendart"]["state"] == "REFRESH_QUEUED"
            assert len(queued_messages) == 1
            assert "api_key" not in json.dumps(queued_messages[0]).lower()
            checks += 1

            duplicate = client.post(
                "/api/v1/recruiter/company-profile/opendart/refresh",
                headers=recruiter_headers,
                json={"corp_code": "90000001"},
            )
            assert duplicate.status_code == 202, duplicate.text
            assert duplicate.json()["refresh"]["state"] == "ALREADY_PENDING"
            assert duplicate.json()["refresh"]["request_id"] == queued_messages[0]["request_id"]
            assert len(queued_messages) == 1
            checks += 1

            original_get_result = api_main.get_refresh_result
            original_delete_result = api_main.delete_refresh_result
            api_main.get_refresh_result = lambda _request_id: None
            pending = client.post(
                "/api/v1/recruiter/company-profile/opendart/collect",
                headers=recruiter_headers,
            )
            assert pending.status_code == 202, pending.text
            assert pending.json()["refresh"]["state"] == "PENDING"
            checks += 1

            with api_main.company_engine.begin() as connection:
                connection.exec_driver_sql(
                    "UPDATE companies SET opendart_pending_requested_at = ? WHERE id = ?",
                    (datetime(2000, 1, 1, tzinfo=timezone.utc), queued_messages[0]["company_id"]),
                )
            timed_out = client.post(
                "/api/v1/recruiter/company-profile/opendart/collect",
                headers=recruiter_headers,
            )
            assert timed_out.status_code == 200, timed_out.text
            assert timed_out.json()["refresh"]["state"] == "RESULT_TIMEOUT"
            assert timed_out.json()["company_profile"]["opendart"]["pending_request_id"] is None
            checks += 1

            api_main.enqueue_refresh = fake_enqueue
            requeued_after_timeout = client.post(
                "/api/v1/recruiter/company-profile/opendart/refresh",
                headers=recruiter_headers,
                json={"corp_code": "90000001"},
            )
            api_main.enqueue_refresh = original_enqueue
            assert requeued_after_timeout.status_code == 202, requeued_after_timeout.text
            assert requeued_after_timeout.json()["refresh"]["state"] == "QUEUED"
            assert len(queued_messages) == 2
            checks += 1

            expired_deleted: list[tuple[str, str]] = []

            def fake_expired_result(_request_id: str) -> None:
                raise OpenDartResultExpired("synthetic expired result")

            api_main.get_refresh_result = fake_expired_result
            api_main.delete_refresh_result = (
                lambda request_id, company_id: expired_deleted.append(
                    (request_id, company_id)
                )
            )
            expired = client.post(
                "/api/v1/recruiter/company-profile/opendart/collect",
                headers=recruiter_headers,
            )
            assert expired.status_code == 200, expired.text
            assert expired.json()["refresh"]["state"] == "RESULT_EXPIRED"
            assert expired.json()["company_profile"]["opendart"]["pending_request_id"] is None
            assert expired_deleted == [
                (queued_messages[-1]["request_id"], queued_messages[-1]["company_id"])
            ]
            checks += 1

            api_main.get_refresh_result = original_get_result
            api_main.delete_refresh_result = original_delete_result
            api_main.enqueue_refresh = fake_enqueue
            requeued = client.post(
                "/api/v1/recruiter/company-profile/opendart/refresh",
                headers=recruiter_headers,
                json={"corp_code": "90000001"},
            )
            api_main.enqueue_refresh = original_enqueue
            assert requeued.status_code == 202, requeued.text
            assert requeued.json()["refresh"]["state"] == "QUEUED"
            assert len(queued_messages) == 3
            checks += 1

            external_snapshot = dict(refreshed_profile["opendart"]["snapshot"])
            external_snapshot["source_kind"] = "live_open_api"
            external_snapshot["synthetic"] = False
            external_snapshot["content_sha256"] = _canonical_hash(
                {
                    key: value
                    for key, value in external_snapshot.items()
                    if key != "content_sha256"
                }
            )
            result_payload = build_refresh_result(
                request_id=queued_messages[-1]["request_id"],
                company_id=queued_messages[-1]["company_id"],
                corp_code=queued_messages[-1]["corp_code"],
                requested_at=FIXED_TIME,
                completed_at=FIXED_TIME,
                outcome="UPDATED",
                snapshot=external_snapshot,
                error_category=None,
            )
            deleted: list[tuple[str, str]] = []
            api_main.get_refresh_result = lambda _request_id: result_payload
            api_main.delete_refresh_result = (
                lambda request_id, company_id: deleted.append((request_id, company_id))
            )
            collected = client.post(
                "/api/v1/recruiter/company-profile/opendart/collect",
                headers=recruiter_headers,
            )
            api_main.get_refresh_result = original_get_result
            api_main.delete_refresh_result = original_delete_result
            os.environ["OPENDART_DISPATCH_MODE"] = "fixture_inline"
            assert collected.status_code == 200, collected.text
            assert collected.json()["refresh"]["state"] == "UPDATED_EXTERNAL_SNAPSHOT"
            assert collected.json()["company_profile"]["opendart"]["state"] == "AVAILABLE_LIVE"
            assert deleted == [
                (queued_messages[-1]["request_id"], queued_messages[-1]["company_id"])
            ]
            checks += 1

            forbidden = client.post(
                "/api/v1/recruiter/company-profile/opendart/refresh",
                headers=candidate_headers,
                json={"corp_code": "90000001"},
            )
            assert forbidden.status_code == 403
            checks += 1

            before_mismatch = client.get(
                "/api/v1/recruiter/company-profile", headers=other_headers
            ).json()["opendart"]
            mismatch = client.post(
                "/api/v1/recruiter/company-profile/opendart/refresh",
                headers=other_headers,
                json={"corp_code": "90000001"},
            )
            assert mismatch.status_code == 409
            after_mismatch = client.get(
                "/api/v1/recruiter/company-profile", headers=other_headers
            ).json()["opendart"]
            assert after_mismatch["state"] == "STALE_LAST_KNOWN_GOOD"
            assert after_mismatch["corp_code"] == before_mismatch["corp_code"]
            assert (
                after_mismatch["snapshot"]["content_sha256"]
                == before_mismatch["snapshot"]["content_sha256"]
            )
            checks += 1

            invalid = client.post(
                "/api/v1/recruiter/company-profile/opendart/refresh",
                headers=recruiter_headers,
                json={"corp_code": "9000000x"},
            )
            assert invalid.status_code == 422
            checks += 1

            not_found = client.post(
                "/api/v1/recruiter/company-profile/opendart/refresh",
                headers=recruiter_headers,
                json={"corp_code": "99999999"},
            )
            assert not_found.status_code == 404
            retained = client.get(
                "/api/v1/recruiter/company-profile", headers=recruiter_headers
            ).json()["opendart"]
            assert retained["state"] == "STALE_LAST_KNOWN_GOOD"
            assert retained["corp_code"] == "90000001"
            assert retained["snapshot"]["company"]["legal_name"] == "아크웨이브"
            checks += 1

            public_after_failure = client.get("/api/v1/jobs").json()[0][
                "company_profile"
            ]["opendart"]
            assert public_after_failure["state"] == "STALE_LAST_KNOWN_GOOD"
            assert public_after_failure["snapshot"]["company"]["legal_name"]
            checks += 1

    print(f"OpenDART API boundary contract: PASS ({checks}/{checks})")


if __name__ == "__main__":
    main()
