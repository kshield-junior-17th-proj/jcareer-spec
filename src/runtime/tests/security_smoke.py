from __future__ import annotations

import json
import uuid

from smoke import login, request, wait_ready


def expect(actual: int, expected: int, body: object, label: str) -> None:
    assert actual == expected, f"{label}: expected {expected}, got {actual}: {body}"


def stage_counts(overview: dict[str, object]) -> dict[str, int]:
    return {
        str(item["status"]): int(item["count"])
        for item in overview["application_stages"]
    }


def main() -> None:
    wait_ready()
    suffix = uuid.uuid4().hex[:10]
    phone_suffix = f"{uuid.uuid4().int % 10_000:04d}"
    canary = f"SYNTH-CANARY-{suffix}"

    status, body = request(
        "/api/v1/auth/signup",
        method="POST",
        body={
            "email": "synthetic-candidate@gmail.com",
            "password": "Demo123!",
            "display_name": canary,
        },
    )
    expect(status, 422, body, "non-reserved email must be rejected")
    status, body = request(
        "/api/v1/auth/signup",
        method="POST",
        body={
            "email": f"{'a' * 250}@jcareer.test",
            "password": "Demo123!",
            "display_name": canary,
        },
    )
    expect(status, 422, body, "email longer than the database contract")

    candidate_token, _ = login("candidate@jcareer.test")
    recruiter_token, recruiter = login("recruiter@jcareer.test")

    status, body = request(
        "/api/v1/candidates/me/consents",
        method="POST",
        token=candidate_token,
        body={
            "consent_type": "privacy_core",
            "action": "grant",
            "policy_version": "x" * 41,
        },
    )
    expect(status, 422, body, "policy version longer than the database contract")

    tampered_token = candidate_token[:-1] + ("A" if candidate_token[-1] != "A" else "B")
    status, body = request("/api/v1/auth/me", token=tampered_token)
    expect(status, 401, body, "tampered token")

    status, body = request("/api/v1/recruiter/jobs", token=candidate_token)
    expect(status, 403, body, "candidate crossing into recruiter API")
    status, body = request("/api/v1/recruiter/overview", token=candidate_token)
    expect(status, 403, body, "candidate crossing into recruiter overview")
    status, body = request("/api/v1/candidates/me/recommendations", token=recruiter_token)
    expect(status, 403, body, "recruiter crossing into candidate API")
    status, body = request("/api/v1/admin/audit", token=recruiter_token)
    expect(status, 403, body, "recruiter crossing into admin API")

    status, jobs = request("/api/v1/jobs")
    expect(status, 200, jobs, "public jobs")
    status, overview = request("/api/v1/recruiter/overview", token=recruiter_token)
    expect(status, 200, overview, "company-scoped recruiter overview")
    assert overview["company"]["company_id"] == recruiter["company_id"]
    assert all(
        item["company_id"] == recruiter["company_id"]
        for item in overview["recent_jobs"]
    ), "overview must not include another tenant's jobs"
    other_job = next(job for job in jobs if job["company_id"] != recruiter["company_id"])
    for path in (
        f"/api/v1/recruiter/jobs/{other_job['id']}/pipeline",
        f"/api/v1/recruiter/jobs/{other_job['id']}/recommendations",
    ):
        status, body = request(path, token=recruiter_token)
        expect(status, 403, body, f"cross-tenant read {path}")
    status, body = request(
        f"/api/v1/recruiter/jobs/{other_job['id']}",
        method="PUT",
        token=recruiter_token,
        body={
            "title": other_job["title"],
            "summary": other_job["summary"],
            "location": other_job["location"],
            "employment_type": other_job["employment_type"],
            "required_skills": other_job["required_skills"],
            "min_experience": other_job["min_experience"],
            "status": other_job["status"],
        },
    )
    expect(status, 403, body, "cross-tenant job update")

    beta_recruiter_token, beta_recruiter = login("recruiter-beta@jcareer.test")
    status, beta_overview_before = request(
        "/api/v1/recruiter/overview", token=beta_recruiter_token
    )
    expect(status, 200, beta_overview_before, "beta overview before current-run job")
    status, body = request(
        "/api/v1/recruiter/jobs",
        method="POST",
        token=beta_recruiter_token,
        body={
            "title": "합성 경계검증 공고",
            "summary": "비교 가능한 요구 기술이 없는 공고는 API 경계에서 거부해야 합니다.",
            "location": "합성시",
            "employment_type": "정규직",
            "required_skills": ["---"],
            "min_experience": 0,
            "status": "open",
        },
    )
    expect(status, 422, body, "non-normalisable required skills")
    status, test_job = request(
        "/api/v1/recruiter/jobs",
        method="POST",
        token=beta_recruiter_token,
        body={
            "title": f"합성 보안검증 공고 {suffix}",
            "summary": "테넌트 경계와 삭제 이후 캐시 상태를 검증하는 일회성 합성 공고입니다.",
            "location": "합성시",
            "employment_type": "정규직",
            "required_skills": ["Python", "Docker"],
            "min_experience": 2,
            "status": "open",
        },
    )
    expect(status, 201, test_job, "isolated synthetic job creation")
    status, job_overview = request(
        "/api/v1/recruiter/overview", token=beta_recruiter_token
    )
    expect(status, 200, job_overview, "beta overview after current-run job")
    assert (
        job_overview["metrics"]["open_jobs"]
        == beta_overview_before["metrics"]["open_jobs"] + 1
    )
    assert (
        job_overview["metrics"]["closed_jobs"]
        == beta_overview_before["metrics"]["closed_jobs"]
    )
    assert any(job["id"] == test_job["id"] for job in job_overview["recent_jobs"])
    for path in (
        f"/api/v1/recruiter/jobs/{test_job['id']}/pipeline",
        f"/api/v1/recruiter/jobs/{test_job['id']}/recommendations",
    ):
        status, body = request(path, token=recruiter_token)
        expect(status, 403, body, f"current-run cross-tenant read {path}")
    status, body = request(
        f"/api/v1/recruiter/jobs/{test_job['id']}",
        method="PUT",
        token=recruiter_token,
        body={
            "title": test_job["title"],
            "summary": test_job["summary"],
            "location": test_job["location"],
            "employment_type": test_job["employment_type"],
            "required_skills": test_job["required_skills"],
            "min_experience": test_job["min_experience"],
            "status": test_job["status"],
        },
    )
    expect(status, 403, body, "current-run cross-tenant job update")

    synthetic_email = f"candidate-{suffix}@example.invalid"
    status, candidate_signup = request(
        "/api/v1/auth/signup",
        method="POST",
        body={
            "email": synthetic_email,
            "password": "Demo123!",
            "display_name": canary,
        },
    )
    expect(status, 201, candidate_signup, "synthetic candidate signup")
    canary_token = candidate_signup["access_token"]

    resume = {
        "phone": f"010-0000-{phone_suffix}",
        "birth_date": "1995-01-01",
        "address_region": f"합성시 {canary}",
        "education": "합성대학교",
        "desired_role": "플랫폼 엔지니어",
        "years_experience": 4,
        "skills": ["Python", "Docker", "AWS"],
        "certificates": ["SYNTH-CERT"],
        "self_intro": f"{canary} 전용 합성 이력서",
    }
    status, body = request(
        "/api/v1/candidates/me/resume", method="POST", token=canary_token, body=resume
    )
    expect(status, 409, body, "resume before core consent")

    status, consent = request(
        "/api/v1/candidates/me/consents",
        method="POST",
        token=canary_token,
        body={"consent_type": "privacy_core", "action": "grant", "policy_version": "2026-05"},
    )
    expect(status, 201, consent, "core consent")

    resume["phone"] = "010-1234-5678"
    status, body = request(
        "/api/v1/candidates/me/resume", method="POST", token=canary_token, body=resume
    )
    expect(status, 422, body, "ordinary phone number must be rejected")
    resume["phone"] = f"010-0000-{phone_suffix}"
    status, saved_resume = request(
        "/api/v1/candidates/me/resume", method="POST", token=canary_token, body=resume
    )
    expect(status, 200, saved_resume, "synthetic resume save")

    status, application = request(
        f"/api/v1/jobs/{test_job['id']}/applications",
        method="POST",
        token=canary_token,
    )
    expect(status, 201, application, "synthetic application")
    status, applied_overview = request(
        "/api/v1/recruiter/overview", token=beta_recruiter_token
    )
    expect(status, 200, applied_overview, "beta overview after current-run application")
    assert (
        applied_overview["metrics"]["total_applications"]
        == job_overview["metrics"]["total_applications"] + 1
    )
    assert stage_counts(applied_overview)["applied"] == stage_counts(job_overview)["applied"] + 1

    status, recommendation = request(
        f"/api/v1/recruiter/jobs/{test_job['id']}/recommendations",
        token=beta_recruiter_token,
    )
    expect(status, 200, recommendation, "recruiter recommendation")
    assert any(
        item["candidate"]["display_name"] == canary
        for item in recommendation["items"]
    )

    status, body = request(
        f"/api/v1/recruiter/applications/{application['id']}",
        method="PATCH",
        token=recruiter_token,
        body={"status": "interview"},
    )
    expect(status, 403, body, "cross-tenant application status update")
    status, own_tenant_update = request(
        f"/api/v1/recruiter/applications/{application['id']}",
        method="PATCH",
        token=beta_recruiter_token,
        body={"status": "interview"},
    )
    expect(status, 200, own_tenant_update, "own-tenant application status update")
    assert own_tenant_update == {"id": application["id"], "status": "interview"}
    status, interview_overview = request(
        "/api/v1/recruiter/overview", token=beta_recruiter_token
    )
    expect(status, 200, interview_overview, "beta overview after status transition")
    assert (
        interview_overview["metrics"]["total_applications"]
        == applied_overview["metrics"]["total_applications"]
    )
    assert stage_counts(interview_overview)["applied"] == stage_counts(applied_overview)["applied"] - 1
    assert stage_counts(interview_overview)["interview"] == stage_counts(applied_overview)["interview"] + 1

    admin_token, _ = login("admin@jcareer.test")
    status, events = request("/api/v1/admin/audit", token=admin_token)
    expect(status, 200, events, "admin audit read")
    rendered_events = json.dumps(events, ensure_ascii=False)
    assert synthetic_email not in rendered_events
    assert "010-0000-" not in rendered_events
    status, audit_views = request(
        "/api/v1/admin/audit?event_type=audit_log_viewed&limit=500",
        token=admin_token,
    )
    expect(status, 200, audit_views, "audit-read self logging")
    assert audit_views, "admin audit reads must themselves be recorded"
    status, next_audit_views = request(
        "/api/v1/admin/audit?event_type=audit_log_viewed&limit=500",
        token=admin_token,
    )
    expect(status, 200, next_audit_views, "current audit-read self logging")
    prior_audit_view_ids = {event["id"] for event in audit_views}
    current_audit_view_ids = {event["id"] for event in next_audit_views}
    assert current_audit_view_ids - prior_audit_view_ids, (
        "the immediately preceding audit read must append a new audit_log_viewed event"
    )
    status, denials = request(
        "/api/v1/admin/audit?event_type=authorization_denied&limit=500",
        token=admin_token,
    )
    expect(status, 200, denials, "authorization denial audit")
    denial_facts = {
        (
            event["target_type"],
            event["target_ref"],
            event["action"],
            event["result"],
            event["company_id"],
        )
        for event in denials
    }
    required_denial_facts = {
        ("job", test_job["id"], "view_pipeline", "denied", recruiter["company_id"]),
        (
            "job",
            test_job["id"],
            "view_recommendations",
            "denied",
            recruiter["company_id"],
        ),
        ("job", test_job["id"], "update", "denied", recruiter["company_id"]),
        (
            "application",
            application["id"],
            "update_status",
            "denied",
            recruiter["company_id"],
        ),
    }
    assert required_denial_facts <= denial_facts
    status, status_events = request(
        "/api/v1/admin/audit?event_type=application_status_changed&limit=500",
        token=admin_token,
    )
    expect(status, 200, status_events, "application status change audit")
    assert any(
        event["target_type"] == "application"
        and event["target_ref"] == application["id"]
        and event["action"] == "interview"
        and event["result"] == "success"
        and event["company_id"] == beta_recruiter["company_id"]
        for event in status_events
    )
    status, job_events = request(
        "/api/v1/admin/audit?event_type=job_created&limit=500", token=admin_token
    )
    expect(status, 200, job_events, "job creation audit")
    assert any(event["target_ref"] == test_job["id"] for event in job_events)

    status, revoked = request(
        "/api/v1/candidates/me/consents/privacy_core",
        method="DELETE",
        token=canary_token,
    )
    expect(status, 201, revoked, "core consent revoke")
    status, body = request("/api/v1/candidates/me/recommendations", token=canary_token)
    expect(status, 409, body, "recommendation after core consent revoke")

    status, withdrawal = request(
        "/api/v1/candidates/me", method="DELETE", token=canary_token
    )
    expect(status, 202, withdrawal, "candidate withdrawal")
    status, body = request("/api/v1/auth/me", token=canary_token)
    expect(status, 401, body, "withdrawn account token")
    status, body = request(
        "/api/v1/auth/login",
        method="POST",
        body={"email": synthetic_email, "password": "Demo123!"},
    )
    expect(status, 401, body, "withdrawn account login")
    status, pipeline = request(
        f"/api/v1/recruiter/jobs/{test_job['id']}/pipeline",
        token=beta_recruiter_token,
    )
    expect(status, 200, pipeline, "post-withdrawal primary database pipeline")
    assert all(
        item["candidate"]["display_name"] != canary for item in pipeline["items"]
    ), "withdrawn candidate must be removed from the primary application relation"

    status, stale_cache = request(
        f"/api/v1/recruiter/jobs/{test_job['id']}/recommendations",
        token=beta_recruiter_token,
    )
    expect(status, 200, stale_cache, "post-withdrawal recommendation cache observation")
    assert stale_cache["cache"] == "hit"
    assert canary in json.dumps(stale_cache, ensure_ascii=False)

    status, closed_job = request(
        f"/api/v1/recruiter/jobs/{test_job['id']}",
        method="PUT",
        token=beta_recruiter_token,
        body={
            "title": test_job["title"],
            "summary": test_job["summary"],
            "location": test_job["location"],
            "employment_type": test_job["employment_type"],
            "required_skills": test_job["required_skills"],
            "min_experience": test_job["min_experience"],
            "status": "closed",
        },
    )
    expect(status, 200, closed_job, "synthetic test job cleanup")

    status, agent_root = request("/agent")
    expect(status, 200, agent_root, "agent root redirect")
    status, llm_root = request("/llm")
    expect(status, 200, llm_root, "llm root redirect")

    print(f"J-Career security smoke: PASS (synthetic canary {canary})")
    print("Observed AS-IS lifecycle state: primary rows removed; cached recommendation remains.")


if __name__ == "__main__":
    main()
