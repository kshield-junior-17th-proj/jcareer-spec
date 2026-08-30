#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src/runtime/api"))


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
        os.environ["AUTO_SEED"] = "true"
        os.environ["OPENDART_MODE"] = "fixture"
        os.environ.pop("OPENDART_API_KEY", None)

        from fastapi.testclient import TestClient

        from app import main as api_main

        with TestClient(api_main.app) as client:
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
            os.environ["OPENDART_DISPATCH_MODE"] = "fixture_inline"
            assert queued.status_code == 202, queued.text
            assert queued.json()["refresh"]["state"] == "QUEUED"
            assert queued.json()["company_profile"]["opendart"]["state"] == "REFRESH_QUEUED"
            assert len(queued_messages) == 1
            assert "api_key" not in json.dumps(queued_messages[0]).lower()
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

        api_main.member_engine.dispose()
        api_main.company_engine.dispose()

    print(f"OpenDART API boundary contract: PASS ({checks}/{checks})")


if __name__ == "__main__":
    main()
