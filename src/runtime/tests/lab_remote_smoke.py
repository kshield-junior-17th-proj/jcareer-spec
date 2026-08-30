from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request


PUBLIC_BASE = os.getenv("JCAREER_PUBLIC_BASE", "http://127.0.0.1:3000")
EXPECTED_PROVIDER = os.getenv(
    "JCAREER_EXPECTED_EXPLANATION_PROVIDER", "local-synthetic-stub"
)
EXPECTED_BEDROCK_LIVE = os.getenv(
    "JCAREER_EXPECTED_BEDROCK_LIVE", "false"
).lower()
CHECK_INTERNAL_SERVICES = os.getenv(
    "JCAREER_CHECK_INTERNAL_SERVICES", "false"
).lower()

if EXPECTED_PROVIDER not in {"local-synthetic-stub", "bedrock"}:
    raise RuntimeError("unsupported expected explanation provider")
if EXPECTED_BEDROCK_LIVE not in {"true", "false"}:
    raise RuntimeError("expected Bedrock live flag must be true or false")
if CHECK_INTERNAL_SERVICES not in {"true", "false"}:
    raise RuntimeError("internal service check flag must be true or false")
if (EXPECTED_PROVIDER == "bedrock") != (EXPECTED_BEDROCK_LIVE == "true"):
    raise RuntimeError("Bedrock provider and live expectation must change together")


def request(base: str, path: str, *, method: str = "GET", body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            payload = response.read()
            return response.status, json.loads(payload) if payload else None
    except urllib.error.HTTPError as error:
        payload = error.read()
        try:
            return error.code, json.loads(payload) if payload else None
        except json.JSONDecodeError:
            return error.code, payload.decode(errors="replace")


def wait_ready() -> None:
    deadline = time.time() + 180
    while time.time() < deadline:
        try:
            status, body = request(PUBLIC_BASE, "/api/v1/runtime")
            if status == 200 and body.get("service") == "J-Career synthetic AS-IS runtime":
                return
        except (OSError, TimeoutError, json.JSONDecodeError):
            pass
        time.sleep(3)
    raise AssertionError("lab runtime did not become ready")


def login(email: str) -> tuple[str, dict[str, object]]:
    status, body = request(
        PUBLIC_BASE,
        "/api/v1/auth/login",
        method="POST",
        body={"email": email, "password": "Demo123!"},
    )
    assert status == 200, body
    return body["access_token"], body["user"]


def main() -> None:
    wait_ready()

    status, runtime = request(PUBLIC_BASE, "/api/v1/runtime")
    assert status == 200, runtime
    assert runtime["live_client_service"] is False
    assert runtime["dataset_profile"] == "demo_not_for_measurement"
    assert runtime["explanation_provider"] == EXPECTED_PROVIDER
    assert runtime["trace_enabled"] is False
    assert runtime["database_boundaries"]["cross_database_foreign_keys"] is False
    assert runtime["database_boundaries"]["cross_database_atomic_commit"] is False

    if CHECK_INTERNAL_SERVICES == "true":
        status, gateway = request("http://127.0.0.1:8200", "/health")
        assert status == 200, gateway
        assert gateway["provider"] == EXPECTED_PROVIDER
        assert gateway["bedrock_live_enabled"] == EXPECTED_BEDROCK_LIVE

        status, agent = request("http://127.0.0.1:8100", "/health")
        assert status == 200 and agent["service"] == "agent", agent

    status, jobs = request(PUBLIC_BASE, "/api/v1/jobs")
    assert status == 200 and len(jobs) >= 3, jobs

    candidate_token, candidate = login("candidate@jcareer.test")
    assert candidate["role"] == "candidate", candidate

    status, recommendations = request(
        PUBLIC_BASE,
        "/api/v1/candidates/me/recommendations",
        token=candidate_token,
    )
    assert status == 200, recommendations
    assert recommendations["recommendation_status"] == "AVAILABLE"
    assert recommendations["explanation_status"] == "AVAILABLE"
    assert recommendations["items"], recommendations
    first = recommendations["items"][0]
    assert first["score_breakdown"]["total_points"] == first["score"]
    assert first["score_breakdown"]["formula_version"] == "deterministic-70-20-10-v1"
    assert first["explanation"]["provider"] == EXPECTED_PROVIDER
    expected_generation_mode = (
        "bedrock-converse" if EXPECTED_PROVIDER == "bedrock" else "deterministic-local-stub"
    )
    assert first["explanation"]["generation_mode"] == expected_generation_mode
    assert first["explanation"]["company_alignment"]["score_effect"] == "NONE"

    status, _ = request(
        PUBLIC_BASE, "/api/v1/recruiter/overview", token=candidate_token
    )
    assert status == 403, "candidate must not enter the recruiter workspace"

    recruiter_token, recruiter = login("recruiter@jcareer.test")
    assert recruiter["role"] == "recruiter", recruiter
    status, overview = request(
        PUBLIC_BASE, "/api/v1/recruiter/overview", token=recruiter_token
    )
    assert status == 200, overview
    assert overview["company"]["company_id"] == recruiter["company_id"]
    assert overview["customer_boundary"]["organization_membership_implemented"] is False
    assert overview["customer_boundary"]["company_recruiter_cardinality_constraint"] is False
    assert overview["customer_boundary"]["company_account_withdrawal_implemented"] is False
    assert overview["customer_boundary"]["company_ownership_transfer_implemented"] is False
    assert overview["customer_boundary"]["company_consent_lifecycle_implemented"] is False
    assert (
        overview["customer_boundary"]["company_signup_initial_status_source"]
        == "approved-model-default-without-review-transition"
    )
    assert overview["data_boundary"]["cross_database_atomic_commit"] is False
    assert overview["data_boundary"]["company_signup_operation_id_implemented"] is False
    assert overview["data_boundary"]["company_signup_idempotency_key_implemented"] is False
    assert overview["data_boundary"]["cross_database_compensation_implemented"] is False
    assert overview["data_boundary"]["cross_database_reconciliation_implemented"] is False
    assert overview["data_boundary"]["cross_database_outbox_implemented"] is False

    status, recruiter_jobs = request(
        PUBLIC_BASE, "/api/v1/recruiter/jobs", token=recruiter_token
    )
    assert status == 200 and recruiter_jobs, recruiter_jobs
    own_job = recruiter_jobs[0]
    status, pipeline = request(
        PUBLIC_BASE,
        f"/api/v1/recruiter/jobs/{own_job['id']}/pipeline",
        token=recruiter_token,
    )
    assert status == 200, pipeline

    other_job = next(
        job for job in jobs if job["company_id"] != recruiter["company_id"]
    )
    status, _ = request(
        PUBLIC_BASE,
        f"/api/v1/recruiter/jobs/{other_job['id']}/pipeline",
        token=recruiter_token,
    )
    assert status == 403, "cross-company pipeline access must be denied"

    status, _ = request(
        PUBLIC_BASE,
        "/api/v1/candidates/me/recommendations",
        token=recruiter_token,
    )
    assert status == 403, "recruiter must not enter the candidate workspace"

    admin_token, admin = login("admin@jcareer.test")
    assert admin["role"] == "admin", admin
    status, operations = request(
        PUBLIC_BASE, "/api/v1/admin/ai-operations", token=admin_token
    )
    assert status == 200, operations
    assert operations["matcher"]["probe_state"] == "AVAILABLE", operations
    assert operations["llm_gateway"]["probe_state"] == "AVAILABLE", operations
    assert operations["llm_gateway"]["provider"] == EXPECTED_PROVIDER, operations
    assert operations["llm_gateway"]["bedrock_live_enabled"] is EXPECTED_BEDROCK_LIVE
    assert operations["opendart"]["probe_state"] == "NOT_PROBED", operations
    status, audit = request(PUBLIC_BASE, "/api/v1/admin/audit", token=admin_token)
    assert status == 200 and audit, audit

    status, _ = request(PUBLIC_BASE, "/agent/health")
    assert status == 404, "matcher must not be exposed through the lab web entrypoint"
    status, _ = request(PUBLIC_BASE, "/llm/health")
    assert status == 404, "LLM gateway must not be exposed through the lab web entrypoint"

    print("J-Career lab remote smoke: PASS")
    print(
        "provider="
        f"{EXPECTED_PROVIDER}, bedrock_live={EXPECTED_BEDROCK_LIVE}, "
        f"internal_checks={CHECK_INTERNAL_SERVICES}"
    )


if __name__ == "__main__":
    main()
