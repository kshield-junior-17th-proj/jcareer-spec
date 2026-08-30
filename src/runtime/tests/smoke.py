from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


BASE = "http://127.0.0.1:3000"


def request(path: str, *, method: str = "GET", body=None, token: str | None = None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            payload = response.read()
            return response.status, json.loads(payload) if payload else None
    except urllib.error.HTTPError as error:
        payload = error.read()
        if not payload:
            return error.code, None
        try:
            return error.code, json.loads(payload)
        except json.JSONDecodeError:
            return error.code, {"raw_response": payload.decode(errors="replace")}


def wait_ready():
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            status, body = request("/api/v1/runtime")
            if status == 200 and body.get("service") == "J-Career synthetic AS-IS runtime":
                return
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            pass
        time.sleep(2)
    raise AssertionError("runtime did not become ready")


def login(email: str) -> tuple[str, dict[str, object]]:
    status, body = request(
        "/api/v1/auth/login",
        method="POST",
        body={"email": email, "password": "Demo123!"},
    )
    assert status == 200, body
    return body["access_token"], body["user"]


def main():
    wait_ready()

    status, runtime = request("/api/v1/runtime")
    assert status == 200
    assert runtime["dataset_profile"] == "demo_not_for_measurement"
    assert runtime["trace_enabled"] is False
    assert runtime["database_boundaries"] == {
        "member": ["identity", "consent", "resume", "application", "audit"],
        "company": ["company", "company_profile", "job"],
        "cross_database_foreign_keys": False,
        "cross_database_atomic_commit": False,
    }

    status, jobs = request("/api/v1/jobs")
    assert status == 200 and len(jobs) >= 3
    status, skill_jobs = request("/api/v1/jobs?q=Playwright")
    assert status == 200 and skill_jobs
    assert all("Playwright" in job["required_skills"] for job in skill_jobs)

    candidate_token, candidate = login("candidate@jcareer.test")
    assert candidate["role"] == "candidate"
    status, recommendations = request(
        "/api/v1/candidates/me/recommendations", token=candidate_token
    )
    assert status == 200, recommendations
    assert recommendations["recommendation_status"] == "AVAILABLE"
    assert recommendations["items"] and recommendations["items"][0]["score"] >= 0
    baseline_items = recommendations["items"]
    first = baseline_items[0]
    assert first["score_breakdown"]["total_points"] == first["score"]
    assert first["score_breakdown"]["formula_version"] == "deterministic-70-20-10-v1"
    assert len(first["score_breakdown"]["factors"]) == 3
    assert "school" in first["score_breakdown"]["excluded_input_fields"]
    assert len(first["explanation"]["prompt_fields_prepared"]) == 9
    assert len(first["explanation"]["pii_fields_prepared"]) == 6
    assert first["explanation"]["company_alignment"]["score_effect"] == "NONE"
    assert first["job"]["company_profile"]["source"] in {
        "synthetic_recruiter_declared",
        "recruiter_declared",
    }

    status, degraded = request(
        "/api/v1/candidates/me/recommendations?explanation_mode=rate_limit",
        token=candidate_token,
    )
    assert status == 200, degraded
    assert degraded["recommendation_status"] == "AVAILABLE"
    assert degraded["explanation_status"] == "UNAVAILABLE_PROVIDER"
    assert degraded["items"] and degraded["items"][0]["score"] >= 0
    baseline_signature = [
        (
            item["job"]["id"],
            item["score"],
            item["score_breakdown"],
            item["matched_feature_ids"],
            item["matched_feature_labels"],
        )
        for item in baseline_items
    ]
    degraded_signature = [
        (
            item["job"]["id"],
            item["score"],
            item["score_breakdown"],
            item["matched_feature_ids"],
            item["matched_feature_labels"],
        )
        for item in degraded["items"]
    ]
    assert degraded_signature == baseline_signature

    status, overclaim = request(
        "/api/v1/candidates/me/recommendations?explanation_mode=overclaim",
        token=candidate_token,
    )
    assert status == 200, overclaim
    assert "우선 채용" in overclaim["items"][0]["explanation"]["text"]
    assert [
        (item["job"]["id"], item["score"], item["score_breakdown"])
        for item in overclaim["items"]
    ] == [
        (item["job"]["id"], item["score"], item["score_breakdown"])
        for item in baseline_items
    ]

    recruiter_token, recruiter = login("recruiter@jcareer.test")
    assert recruiter["role"] == "recruiter"
    status, overview = request("/api/v1/recruiter/overview", token=recruiter_token)
    assert status == 200, overview
    assert overview["company"]["company_id"] == recruiter["company_id"]
    assert overview["metrics"]["open_jobs"] >= 1
    assert overview["data_boundary"] == {
        "member_database": [
            "계정·인증",
            "동의 이벤트",
            "지원자 이력서",
            "지원 내역",
            "감사 이벤트",
        ],
        "company_database": ["기업", "기업 방향 프로필", "채용공고"],
        "join_owner": "api",
        "application_job_reference": "logical_id_without_cross_database_foreign_key",
        "cross_database_atomic_commit": False,
        "company_signup_operation_id_implemented": False,
        "company_signup_idempotency_key_implemented": False,
        "cross_database_compensation_implemented": False,
        "cross_database_reconciliation_implemented": False,
        "cross_database_outbox_implemented": False,
    }
    assert overview["customer_boundary"] == {
        "identity_model": "recruiter-company-logical-link-no-cardinality-constraint",
        "signup_recruiter_creation": "one-recruiter-with-new-company",
        "company_recruiter_cardinality_constraint": False,
        "organization_membership_implemented": False,
        "invite_and_role_lifecycle_implemented": False,
        "company_account_withdrawal_implemented": False,
        "company_ownership_transfer_implemented": False,
        "company_consent_lifecycle_implemented": False,
        "company_status_transition_implemented": False,
        "company_status_actor_modeled": False,
        "company_signup_initial_status_source": "approved-model-default-without-review-transition",
        "company_status_record": "approved",
        "company_status_gate_enforced": False,
    }
    assert all(
        item["company_id"] == recruiter["company_id"]
        for item in overview["recent_jobs"]
    )
    status, recruiter_jobs = request("/api/v1/recruiter/jobs", token=recruiter_token)
    assert status == 200 and recruiter_jobs
    status, company_profile = request(
        "/api/v1/recruiter/company-profile", token=recruiter_token
    )
    assert status == 200, company_profile
    assert company_profile["direction_statement"]
    assert company_profile["declared_values"]
    own_job = recruiter_jobs[0]
    status, pipeline = request(
        f"/api/v1/recruiter/jobs/{own_job['id']}/pipeline", token=recruiter_token
    )
    assert status == 200, pipeline
    status, ranked = request(
        f"/api/v1/recruiter/jobs/{own_job['id']}/recommendations",
        token=recruiter_token,
    )
    assert status == 200 and ranked["recommendation_status"] == "AVAILABLE", ranked
    assert ranked["items"][0]["score_breakdown"]["total_points"] == ranked["items"][0]["score"]

    other_job = next(job for job in jobs if job["company_id"] != recruiter["company_id"])
    status, _ = request(
        f"/api/v1/recruiter/jobs/{other_job['id']}/pipeline", token=recruiter_token
    )
    assert status == 403, "cross-tenant pipeline access must be denied"

    admin_token, admin = login("admin@jcareer.test")
    assert admin["role"] == "admin"
    status, operations = request("/api/v1/admin/ai-operations", token=admin_token)
    assert status == 200, operations
    assert operations["matcher"]["probe_state"] == "AVAILABLE"
    assert operations["llm_gateway"]["probe_state"] == "AVAILABLE"
    assert operations["opendart"]["probe_state"] == "NOT_PROBED"
    status, events = request("/api/v1/admin/audit", token=admin_token)
    assert status == 200 and events

    status, direct_agent = request("/agent/health")
    assert status == 200 and direct_agent["service"] == "agent"
    status, direct_gateway = request("/llm/health")
    assert status == 200 and direct_gateway["service"] == "llm-gateway"

    print("J-Career runtime smoke test: PASS")


if __name__ == "__main__":
    main()
