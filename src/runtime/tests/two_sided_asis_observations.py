from __future__ import annotations

import json
import uuid
import subprocess
from collections.abc import Callable
from functools import wraps

from database_boundary import RUNTIME_ROOT, psql
from smoke import request, wait_ready


def require_synthetic_runtime() -> None:
    status, runtime = request("/api/v1/runtime")
    assert status == 200, runtime
    assert runtime["live_client_service"] is False
    assert runtime["dataset_profile"] == "demo_not_for_measurement"
    status, gateway = request("/llm/health")
    assert status == 200, gateway
    assert gateway["provider"] == "local-synthetic-stub", (
        "observation scenarios are stub-only and must not reach an external provider"
    )
    assert gateway["mode"] == "success", (
        "cache observations require the deterministic successful synthetic stub mode"
    )
    assert gateway["raw_prompt_log_enabled"] == "true", (
        "raw prompt retention observations require the synthetic prompt log to be enabled"
    )
    assert gateway["bedrock_live_enabled"] == "false", (
        "observation scenarios require Bedrock live to remain disabled"
    )


def observe_internal_service_and_prompt_boundary(cleanup: dict[str, object]) -> None:
    subject_ref = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    status, matched = request(
        "/agent/internal/match/jobs",
        method="POST",
        body={
            "candidate": {
                "id": str(uuid.uuid4()),
                "desired_role": "합성 플랫폼 개발자",
                "skills": ["Python"],
                "years_experience": 2,
            },
            "jobs": [
                {
                    "id": subject_ref,
                    "title": "합성 플랫폼 개발자",
                    "required_skills": ["Python"],
                    "min_experience": 1,
                }
            ],
            "limit": 1,
        },
    )
    assert status == 200 and matched["status"] == "AVAILABLE", matched
    match = matched["items"][0]
    status, explained = request(
        "/llm/internal/explanations",
        method="POST",
        body={
            "correlation_id": correlation_id,
            "items": [
                {
                    "subject_ref": subject_ref,
                    "score": match["score"],
                    "score_breakdown": match["score_breakdown"],
                    "matched_feature_ids": match["matched_feature_ids"],
                    "matched_feature_labels": match["matched_feature_labels"],
                    "candidate_context": {
                        "name": "합성 내부경로 관찰자",
                        "phone": "010-0000-0000",
                        "email": "internal-observation@example.invalid",
                        "birthdate": "1994-01-01",
                        "address": "합성 지역",
                        "school": "합성 학교",
                        "certificates": ["합성 자격"],
                        "self_intro": "합성 신뢰와 협업을 설명하는 자기소개",
                    },
                    "company_context": {
                        "company_name": "합성 내부경로 관찰기업",
                        "direction_statement": "합성 신뢰와 협업을 선언한 기업 방향",
                        "declared_values": ["합성 신뢰", "합성 협업"],
                        "profile_version": "company-profile-internal-observation-v1",
                        "job_title": "합성 플랫폼 개발자",
                        "job_summary": "내부 서비스 인증 경계와 준비 필드를 관찰하는 합성 공고",
                    },
                }
            ],
        },
    )
    assert status == 200 and explained["status"] == "AVAILABLE", explained
    explanation = explained["items"][0]
    prompt_fields = [
        "address",
        "birthdate",
        "certificates",
        "email",
        "name",
        "phone",
        "school",
        "self_intro",
    ]
    pii_fields = ["address", "birthdate", "email", "name", "phone", "school"]
    assert explanation["prompt_fields_prepared"] == prompt_fields
    assert explanation["pii_fields_prepared"] == pii_fields
    assert set(prompt_fields).issubset(
        set(match["score_breakdown"]["excluded_input_fields"])
    )
    cleanup["prompt_records"] = [(correlation_id, subject_ref)]


def signup_candidate(suffix: str) -> tuple[str, str, str]:
    email = f"asis-observation-{suffix}@example.invalid"
    status, signup = request(
        "/api/v1/auth/signup",
        method="POST",
        body={
            "email": email,
            "password": "Demo123!",
            "display_name": f"합성 관찰지원자 {suffix}",
        },
    )
    assert status == 201, signup
    return signup["access_token"], email, str(signup["user"]["id"])


def signup_recruiter(suffix: str) -> tuple[str, dict[str, object]]:
    status, signup = request(
        "/api/v1/auth/signup/recruiter",
        method="POST",
        body={
            "email": f"asis-observation-recruiter-{suffix}@example.invalid",
            "password": "Demo123!",
            "display_name": f"합성 관찰담당자 {suffix}",
            "company_name": f"합성 관찰기업 {suffix}",
            "company_address": "합성 주소",
        },
    )
    assert status == 201, signup
    return signup["access_token"], signup["user"]


def register_member_state_restore(
    cleanup: dict[str, object],
    *,
    user_id: object,
    field: str,
    original: object,
) -> dict[str, object]:
    canonical_user_id = validated_uuid(user_id)
    if field == "company_id":
        canonical_original: object = validated_uuid(original)
    elif field == "active" and isinstance(original, bool):
        canonical_original = original
    else:
        raise AssertionError("unsupported synthetic member state restore")
    restores = cleanup.setdefault("member_state_restores", [])
    if not isinstance(restores, list):
        raise AssertionError("synthetic member state restore registry is invalid")
    record = {
        "user_id": canonical_user_id,
        "field": field,
        "original": canonical_original,
        "expected_current": canonical_original,
    }
    restores.append(record)
    return record


def member_state_sql(field: str, value: object) -> tuple[str, str]:
    if field == "company_id":
        canonical = validated_uuid(value)
        return f"company_id='{canonical}'", canonical
    if field == "active" and isinstance(value, bool):
        return ("active is true" if value else "active is false"), ("t" if value else "f")
    raise AssertionError("unsupported synthetic member state value")


def conditionally_replace_member_state(
    record: dict[str, object], replacement: object
) -> None:
    user_id = validated_uuid(record["user_id"])
    field = str(record["field"])
    expected_clause, _ = member_state_sql(field, record["expected_current"])
    replacement_clause, replacement_output = member_state_sql(field, replacement)
    replacement_literal = replacement_clause.split("=", 1)[1] if field == "company_id" else (
        "true" if replacement is True else "false"
    )
    changed = psql(
        "jcareer_member_app",
        "jcareer_member",
        "with changed as ("
        f"update users set {field}={replacement_literal} "
        f"where id='{user_id}' and {expected_clause} returning id"
        ") select count(*) from changed;",
    )
    assert changed.returncode == 0 and changed.stdout.strip() == "1", (
        "synthetic member state mutation did not affect exactly one expected row"
    )
    record["expected_current"] = replacement
    observed = psql(
        "jcareer_member_app",
        "jcareer_member",
        f"select {field} from users where id='{user_id}';",
    )
    assert observed.returncode == 0 and observed.stdout.strip() == replacement_output, (
        "synthetic member state mutation verification failed"
    )


def restore_member_state_record(
    cleanup: dict[str, object], record: dict[str, object]
) -> None:
    if record["expected_current"] != record["original"]:
        conditionally_replace_member_state(record, record["original"])
    restores = cleanup.get("member_state_restores")
    if isinstance(restores, list) and record in restores:
        restores.remove(record)


def restore_observation_member_states(cleanup: dict[str, object]) -> list[str]:
    restores = cleanup.get("member_state_restores") or []
    if not isinstance(restores, list):
        return ["synthetic member state restore registry is invalid"]
    failures: list[str] = []
    for record in list(restores):
        if not isinstance(record, dict):
            failures.append("synthetic member state restore record is invalid")
            continue
        try:
            restore_member_state_record(cleanup, record)
        except Exception:
            failures.append("synthetic member state conditional restore failed")
    return failures


def observe_api_token_reuse_and_account_active_gate(
    cleanup: dict[str, object], suffix: str
) -> None:
    token, _, user_id = signup_candidate(f"{suffix}-session")
    candidate_ids = cleanup.get("candidate_ids")
    if not isinstance(candidate_ids, list):
        raise AssertionError("synthetic candidate cleanup registry is invalid")
    candidate_ids.append(user_id)
    restore = register_member_state_restore(
        cleanup, user_id=user_id, field="active", original=True
    )
    scenario_failed = False
    try:
        status, before = request("/api/v1/auth/me", token=token)
        assert status == 200 and before["id"] == user_id, before
        status, _ = request(
            "/api/v1/auth/logout", method="POST", token=token
        )
        assert status == 404
        status, after_unknown_route = request("/api/v1/auth/me", token=token)
        assert status == 200 and after_unknown_route["id"] == user_id
        conditionally_replace_member_state(restore, False)
        status, _ = request("/api/v1/auth/me", token=token)
        assert status == 401
    except BaseException:
        scenario_failed = True
        raise
    finally:
        try:
            restore_member_state_record(cleanup, restore)
        except Exception as restore_error:
            if not scenario_failed:
                raise
            print(
                "WARNING: session observation restore did not mask scenario failure: "
                f"{restore_error}"
            )
    print(
        "api_token_account_gate_observed="
        "auth-me-before:200,post-auth-logout:404,"
        "auth-me-same-token-after-route-404:200,"
        "auth-me-after-test-only-active-false:401"
    )


def observe_recruiter_logical_link_resolution(
    cleanup: dict[str, object],
    *,
    recruiter_token: str,
    recruiter_user_id: object,
    original_company_id: object,
    alternate_company_id: object,
) -> None:
    original_company = validated_uuid(original_company_id)
    alternate_company = validated_uuid(alternate_company_id)
    assert original_company != alternate_company
    missing_company = str(uuid.uuid4())
    company_count = psql(
        "jcareer_company_app",
        "jcareer_company",
        "select count(*) from companies where "
        f"id in ('{original_company}','{alternate_company}');",
    )
    missing_count = psql(
        "jcareer_company_app",
        "jcareer_company",
        f"select count(*) from companies where id='{missing_company}';",
    )
    assert company_count.returncode == 0 and company_count.stdout.strip() == "2"
    assert missing_count.returncode == 0 and missing_count.stdout.strip() == "0"
    restore = register_member_state_restore(
        cleanup,
        user_id=recruiter_user_id,
        field="company_id",
        original=original_company,
    )
    scenario_failed = False
    try:
        conditionally_replace_member_state(restore, missing_company)
        status, _ = request("/api/v1/recruiter/overview", token=recruiter_token)
        assert status == 503
        conditionally_replace_member_state(restore, alternate_company)
        status, alternate_overview = request(
            "/api/v1/recruiter/overview", token=recruiter_token
        )
        assert status == 200, alternate_overview
        assert alternate_overview["company"]["company_id"] == alternate_company
    except BaseException:
        scenario_failed = True
        raise
    finally:
        try:
            restore_member_state_record(cleanup, restore)
        except Exception as restore_error:
            if not scenario_failed:
                raise
            print(
                "WARNING: logical-link observation restore did not mask scenario failure: "
                f"{restore_error}"
            )
    restored = psql(
        "jcareer_member_app",
        "jcareer_member",
        f"select company_id from users where id='{validated_uuid(recruiter_user_id)}';",
    )
    assert restored.returncode == 0 and restored.stdout.strip() == original_company
    print(
        "logical_link_resolution_observed="
        "missing-synthetic-company:overview-503,"
        "alternate-synthetic-company:overview-200-response-company-id-matched,"
        "original-company-id-restored"
    )


def close_observation_job(
    recruiter_token: str,
    job_id: str,
    job_body: dict[str, object],
    *,
    strict: bool,
) -> None:
    status, response = request(
        f"/api/v1/recruiter/jobs/{job_id}",
        method="PUT",
        token=recruiter_token,
        body={**job_body, "status": "closed"},
    )
    if status == 200:
        return
    message = f"synthetic observation job cleanup failed: {status}: {response}"
    if strict:
        raise AssertionError(message)
    print(f"WARNING: {message}")


def validated_uuid(value: object) -> str:
    parsed = str(uuid.UUID(str(value)))
    if parsed != str(value):
        raise AssertionError("synthetic cleanup identifier is not canonical UUID")
    return parsed


def redis_cli(
    *arguments: str, input_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "exec", "-T", "redis", "redis-cli", "--raw", *arguments],
        cwd=RUNTIME_ROOT,
        check=False,
        text=True,
        encoding="utf-8",
        errors="strict",
        input=input_text,
        capture_output=True,
    )


def recruiter_audit_count(recruiter_user_id: object, company_id: object) -> int:
    actor = validated_uuid(recruiter_user_id)
    company = validated_uuid(company_id)
    observed = psql(
        "jcareer_member_app",
        "jcareer_member",
        "select count(*) from audit_events "
        f"where actor_user_id='{actor}' and company_id='{company}';",
    )
    if observed.returncode != 0:
        raise AssertionError("synthetic recruiter audit count query failed")
    try:
        return int(observed.stdout.strip())
    except ValueError as exc:
        raise AssertionError("synthetic recruiter audit count was not an integer") from exc


def recruiter_cache_entry(
    job_id: object, correlation_id: object
) -> tuple[str, dict[str, object]]:
    job = validated_uuid(job_id)
    correlation = validated_uuid(correlation_id)
    scanned = redis_cli(
        "--scan", "--pattern", f"asis:*:recruiter-recommendations:{job}:*"
    )
    if scanned.returncode != 0:
        raise AssertionError("synthetic recruiter cache scan failed")
    matches: list[tuple[str, dict[str, object]]] = []
    for key in (line.strip() for line in scanned.stdout.splitlines() if line.strip()):
        if not key.startswith("asis:") or job not in key:
            raise AssertionError("synthetic cache lookup escaped the exact job identifier")
        raw = redis_cli("GET", key)
        if raw.returncode != 0:
            raise AssertionError("synthetic recruiter cache read failed")
        try:
            payload = json.loads(raw.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError("synthetic recruiter cache JSON was invalid") from exc
        if isinstance(payload, dict) and payload.get("correlation_id") == correlation:
            matches.append((key, payload))
    if len(matches) != 1:
        raise AssertionError("exact synthetic recruiter cache entry was not unique")
    return matches[0]


def prompt_log_record_count(
    correlation_id: object, subject_ref: object
) -> subprocess.CompletedProcess[str]:
    correlation = validated_uuid(correlation_id)
    subject = validated_uuid(subject_ref)
    probe = "\n".join(
        [
            "import json, pathlib, sys",
            "path = pathlib.Path('/data/prompt-log.jsonl')",
            "records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]",
            "count = sum(record.get('correlation_id') == sys.argv[1] and record.get('subject_ref') == sys.argv[2] for record in records)",
            "print(count)",
        ]
    )
    return subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "llm-gateway",
            "python",
            "-c",
            probe,
            correlation,
            subject,
        ],
        cwd=RUNTIME_ROOT,
        check=False,
        text=True,
        encoding="utf-8",
        errors="strict",
        capture_output=True,
    )


def verify_retained_prompt_records(cleanup: dict[str, object]) -> list[str]:
    failures: list[str] = []
    records = cleanup.get("prompt_records") or []
    if not isinstance(records, list) or not records:
        return ["raw prompt retention probe has no exact synthetic record"]
    pairs: list[tuple[str, str]] = []
    for record in records:
        if not isinstance(record, (list, tuple)) or len(record) != 2:
            return ["raw prompt retention probe has an invalid pair"]
        pairs.append((validated_uuid(record[0]), validated_uuid(record[1])))
    if len(pairs) != len(set(pairs)):
        return ["raw prompt retention probe has duplicate synthetic pairs"]
    for correlation_id, subject_ref in pairs:
        observed = prompt_log_record_count(correlation_id, subject_ref)
        if observed.returncode != 0 or observed.stdout.strip() != "1":
            failures.append("exact synthetic raw prompt record was not retained once")
    return failures


def delete_observation_cache_keys(cleanup: dict[str, object]) -> list[str]:
    identifiers = {
        validated_uuid(value)
        for value in [cleanup.get("job_id"), *(cleanup.get("candidate_ids") or [])]
        if value
    }
    patterns: list[str] = []
    if cleanup.get("job_id"):
        patterns.append(
            f"asis:*:recruiter-recommendations:{validated_uuid(cleanup['job_id'])}:*"
        )
    patterns.extend(
        f"asis:*:candidate-recommendations:{validated_uuid(candidate_id)}:*"
        for candidate_id in cleanup.get("candidate_ids") or []
    )
    failures: list[str] = []
    keys: set[str] = set()
    for pattern in patterns:
        scanned = redis_cli("--scan", "--pattern", pattern)
        if scanned.returncode != 0:
            failures.append("Redis synthetic cache scan failed")
            continue
        keys.update(line.strip() for line in scanned.stdout.splitlines() if line.strip())
    if any(
        not key.startswith("asis:") or not any(identifier in key for identifier in identifiers)
        for key in keys
    ):
        failures.append("Redis cleanup refused a key outside the exact synthetic run identifiers")
        return failures
    if keys:
        deleted = redis_cli("DEL", *sorted(keys))
        if deleted.returncode != 0:
            failures.append("Redis synthetic cache delete failed")
    for pattern in patterns:
        remaining = redis_cli("--scan", "--pattern", pattern)
        if remaining.returncode != 0 or remaining.stdout.strip():
            failures.append("Redis synthetic cache residue verification failed")
    return failures


def delete_observation_database_records(cleanup: dict[str, object]) -> list[str]:
    recruiter_values = cleanup.get("recruiter_user_ids") or [
        cleanup.get("recruiter_user_id")
    ]
    user_ids = sorted({
        validated_uuid(value)
        for value in [*recruiter_values, *(cleanup.get("candidate_ids") or [])]
        if value
    })
    company_values = cleanup.get("company_ids") or [cleanup.get("company_id")]
    company_ids = sorted({validated_uuid(value) for value in company_values if value})
    job_id = validated_uuid(cleanup["job_id"]) if cleanup.get("job_id") else None
    failures: list[str] = []

    for company_id in company_ids:
        restored = psql(
            "jcareer_company_app",
            "jcareer_company",
            f"update companies set status='approved' where id='{company_id}';",
        )
        if restored.returncode != 0:
            failures.append("synthetic company status restore failed")

    if user_ids:
        quoted_users = ",".join(f"'{value}'" for value in user_ids)
        application_filter = f"candidate_id in ({quoted_users})"
        if job_id:
            application_filter += f" or job_id='{job_id}'"
        quoted_companies = ",".join(f"'{value}'" for value in company_ids)
        company_filter = (
            f" or company_id in ({quoted_companies})" if company_ids else ""
        )
        member_cleanup = psql(
            "jcareer_member_app",
            "jcareer_member",
            "begin;"
            f"delete from applications where {application_filter};"
            f"delete from consent_events where user_id in ({quoted_users});"
            f"delete from resumes where user_id in ({quoted_users});"
            f"delete from audit_events where actor_user_id in ({quoted_users}){company_filter};"
            f"delete from users where id in ({quoted_users});"
            "commit;",
        )
        if member_cleanup.returncode != 0:
            failures.append("synthetic member database cleanup failed")
        member_residue = psql(
            "jcareer_member_app",
            "jcareer_member",
            "select "
            f"(select count(*) from applications where {application_filter}) + "
            f"(select count(*) from consent_events where user_id in ({quoted_users})) + "
            f"(select count(*) from resumes where user_id in ({quoted_users})) + "
            f"(select count(*) from audit_events where actor_user_id in ({quoted_users}){company_filter}) + "
            f"(select count(*) from users where id in ({quoted_users}));",
        )
        if member_residue.returncode != 0 or member_residue.stdout.strip() != "0":
            failures.append("synthetic member database residue verification failed")

    if company_ids:
        quoted_companies = ",".join(f"'{value}'" for value in company_ids)
        company_cleanup = psql(
            "jcareer_company_app",
            "jcareer_company",
            "begin;"
            f"delete from jobs where company_id in ({quoted_companies});"
            f"delete from companies where id in ({quoted_companies});"
            "commit;",
        )
        if company_cleanup.returncode != 0:
            failures.append("synthetic company database cleanup failed")
        company_residue = psql(
            "jcareer_company_app",
            "jcareer_company",
            "select "
            f"(select count(*) from jobs where company_id in ({quoted_companies})) + "
            f"(select count(*) from companies where id in ({quoted_companies}));",
        )
        if company_residue.returncode != 0 or company_residue.stdout.strip() != "0":
            failures.append("synthetic company database residue verification failed")
    return failures


def cleanup_observation_data(
    cleanup: dict[str, object], *, strict: bool
) -> None:
    close_warning: str | None = None
    if {"recruiter_token", "job_id", "job_body"}.issubset(cleanup):
        try:
            close_observation_job(
                str(cleanup["recruiter_token"]),
                str(cleanup["job_id"]),
                dict(cleanup["job_body"]),
                strict=False,
            )
        except Exception:
            close_warning = "synthetic job close request failed; direct cleanup continued"
    failures: list[str] = []
    for label, cleanup_step in (
        ("synthetic member state restore raised", restore_observation_member_states),
        ("Redis synthetic cache cleanup raised", delete_observation_cache_keys),
        ("synthetic database cleanup raised", delete_observation_database_records),
        ("raw prompt retention probe raised", verify_retained_prompt_records),
    ):
        try:
            failures.extend(cleanup_step(cleanup))
        except Exception:
            failures.append(label)
    if failures:
        message = "; ".join(failures)
        if strict:
            raise AssertionError(message)
        print(f"WARNING: cleanup did not mask scenario failure: {message}")
        return
    if close_warning:
        print(f"WARNING: {close_warning}")
    print("observation_cleanup=database-records,run-cache-keys; raw-prompt-log=observed-retained")


def with_job_cleanup(function: Callable[[dict[str, object]], None]):
    @wraps(function)
    def wrapped() -> None:
        cleanup: dict[str, object] = {}
        scenario_failed = False
        try:
            function(cleanup)
        except BaseException:
            scenario_failed = True
            raise
        finally:
            try:
                cleanup_observation_data(cleanup, strict=not scenario_failed)
            except Exception as cleanup_error:
                if not scenario_failed:
                    raise
                print(f"WARNING: cleanup did not mask scenario failure: {cleanup_error}")

    return wrapped


def run_observations(cleanup: dict[str, object]) -> None:
    wait_ready()
    require_synthetic_runtime()
    observe_internal_service_and_prompt_boundary(cleanup)
    suffix = uuid.uuid4().hex[:10]

    recruiter_token, recruiter = signup_recruiter(suffix)
    cleanup.update(
        recruiter_token=recruiter_token,
        recruiter_user_id=str(recruiter["id"]),
        company_id=str(recruiter["company_id"]),
        recruiter_user_ids=[str(recruiter["id"])],
        company_ids=[str(recruiter["company_id"])],
    )
    candidate_token, candidate_email, candidate_id = signup_candidate(suffix)
    candidate_ids = [candidate_id]
    cleanup["candidate_ids"] = candidate_ids

    status, signup_overview = request(
        "/api/v1/recruiter/overview", token=recruiter_token
    )
    assert status == 200, signup_overview
    assert (
        signup_overview["customer_boundary"]["identity_model"]
        == "recruiter-company-logical-link-no-cardinality-constraint"
    )
    assert (
        signup_overview["customer_boundary"]["signup_recruiter_creation"]
        == "one-recruiter-with-new-company"
    )
    assert (
        signup_overview["customer_boundary"][
            "company_recruiter_cardinality_constraint"
        ]
        is False
    )
    assert signup_overview["customer_boundary"]["company_status_record"] == "approved"
    signup_initial_status_source = signup_overview["customer_boundary"][
        "company_signup_initial_status_source"
    ]
    assert signup_initial_status_source == "approved-model-default-without-review-transition"

    status, profile = request(
        "/api/v1/recruiter/company-profile", token=recruiter_token
    )
    assert status == 200 and profile["source"] == "unset", profile

    status, consent = request(
        "/api/v1/candidates/me/consents",
        method="POST",
        token=candidate_token,
        body={
            "action": "grant",
            "consent_type": "privacy_core",
            "policy_version": "asis-observation-client-value",
        },
    )
    assert status == 201, consent
    status, consents = request(
        "/api/v1/candidates/me/consents", token=candidate_token
    )
    assert status == 200 and consents, consents
    latest_consent = consents[0]
    assert latest_consent["policy_version"] == "asis-observation-client-value"
    assert {"skills", "desired_role", "self_intro"}.isdisjoint(
        latest_consent["collected_items"]
    )

    before_resume = {
        "phone": f"010-0000-{uuid.uuid4().int % 10000:04d}",
        "birth_date": "1994-01-01",
        "address_region": "합성 지역 A",
        "education": "합성 대학교",
        "desired_role": "디자인 전문가",
        "years_experience": 0,
        "skills": ["Figma"],
        "certificates": ["합성 자격"],
        "self_intro": "지원 당시 합성 자기소개 BEFORE",
    }
    status, _ = request(
        "/api/v1/candidates/me/resume",
        method="POST",
        token=candidate_token,
        body=before_resume,
    )
    assert status == 200

    job_before = {
        "title": "합성 플랫폼 개발자 공고 BEFORE",
        "summary": "지원 시점 snapshot 부재를 관찰하기 위한 합성 공고입니다.",
        "location": "합성 지역 A",
        "employment_type": "정규직",
        "required_skills": ["Python", "FastAPI"],
        "min_experience": 2,
        "status": "open",
    }
    status, job = request(
        "/api/v1/recruiter/jobs",
        method="POST",
        token=recruiter_token,
        body=job_before,
    )
    assert status == 201, job
    cleanup.update(
        recruiter_token=recruiter_token,
        job_id=str(job["id"]),
        job_body=job_before,
    )

    status, application = request(
        f"/api/v1/jobs/{job['id']}/applications",
        method="POST",
        token=candidate_token,
    )
    assert status == 201, application
    application_id = validated_uuid(application["id"])
    submitted_audit = psql(
        "jcareer_member_app",
        "jcareer_member",
        "select count(*) from audit_events "
        f"where actor_user_id='{validated_uuid(candidate_id)}' "
        "and event_type='application_submitted' and target_type='job' "
        f"and target_ref='{validated_uuid(job['id'])}' and detail::jsonb='{{}}'::jsonb;",
    )
    assert submitted_audit.returncode == 0 and submitted_audit.stdout.strip() == "1"
    status, application_after_status = request(
        f"/api/v1/recruiter/applications/{application_id}",
        method="PATCH",
        token=recruiter_token,
        body={"status": "reviewing"},
    )
    assert status == 200 and application_after_status["status"] == "reviewing"
    status_audit = psql(
        "jcareer_member_app",
        "jcareer_member",
        "select count(*) from audit_events "
        f"where actor_user_id='{validated_uuid(recruiter['id'])}' "
        "and event_type='application_status_changed' and target_type='application' "
        f"and target_ref='{application_id}' and action='reviewing' "
        "and detail::jsonb='{}'::jsonb;",
    )
    assert status_audit.returncode == 0 and status_audit.stdout.strip() == "1"

    attacker_token, attacker = signup_recruiter(f"{suffix}-attacker")
    attacker_user_id = validated_uuid(attacker["id"])
    attacker_company_id = validated_uuid(attacker["company_id"])
    target_company_id = validated_uuid(recruiter["company_id"])
    assert attacker_company_id != target_company_id
    cleanup["recruiter_user_ids"].append(attacker_user_id)
    cleanup["company_ids"].append(attacker_company_id)
    target_job_id = validated_uuid(job["id"])
    denied_requests = [
        (
            f"/api/v1/recruiter/jobs/{job['id']}/pipeline",
            "GET",
            None,
            "job",
            target_job_id,
            "view_pipeline",
        ),
        (
            f"/api/v1/recruiter/jobs/{job['id']}/recommendations",
            "GET",
            None,
            "job",
            target_job_id,
            "view_recommendations",
        ),
        (
            f"/api/v1/recruiter/jobs/{job['id']}",
            "PUT",
            job_before,
            "job",
            target_job_id,
            "update",
        ),
        (
            f"/api/v1/recruiter/applications/{application_id}",
            "PATCH",
            {"status": "interview"},
            "application",
            application_id,
            "update_status",
        ),
    ]
    for path, method, body, _, _, _ in denied_requests:
        status, denied = request(path, method=method, token=attacker_token, body=body)
        assert status == 403, denied
    for _, _, _, target_type, target_ref, action in denied_requests:
        exact_denial = psql(
            "jcareer_member_app",
            "jcareer_member",
            "select count(*) from audit_events "
            f"where actor_user_id='{attacker_user_id}' "
            f"and company_id='{attacker_company_id}' "
            "and actor_role='recruiter' and event_type='authorization_denied' "
            "and result='denied' and purpose='recruiting' and detail::jsonb='{}'::jsonb "
            "and not (detail::jsonb ? 'target_company_id') "
            f"and target_type='{target_type}' and target_ref='{target_ref}' "
            f"and action='{action}';",
        )
        assert exact_denial.returncode == 0, (
            "exact authorization-denial audit query failed: "
            f"{exact_denial.stderr.strip() or 'psql exited without stderr'}"
        )
        assert exact_denial.stdout.strip() == "1"
    denial_shape = psql(
        "jcareer_member_app",
        "jcareer_member",
        "select count(*) from audit_events "
        f"where actor_user_id='{attacker_user_id}' "
        f"and company_id='{attacker_company_id}' "
        "and actor_role='recruiter' and event_type='authorization_denied' "
        "and result='denied' and purpose='recruiting' and detail::jsonb='{}'::jsonb "
        "and not (detail::jsonb ? 'target_company_id') and ("
        f"(target_type='job' and target_ref='{target_job_id}' "
        "and action in ('view_pipeline','view_recommendations','update')) or "
        f"(target_type='application' and target_ref='{application_id}' "
        "and action='update_status'));",
    )
    assert denial_shape.returncode == 0, (
        "authorization-denial aggregate query failed: "
        f"{denial_shape.stderr.strip() or 'psql exited without stderr'}"
    )
    assert denial_shape.stdout.strip() == "4"
    target_company_filter = psql(
        "jcareer_member_app",
        "jcareer_member",
        "select count(*) from audit_events "
        f"where actor_user_id='{attacker_user_id}' "
        f"and company_id='{target_company_id}' "
        "and event_type='authorization_denied';",
    )
    assert target_company_filter.returncode == 0
    assert target_company_filter.stdout.strip() == "0"

    status, initial_recommendations = request(
        f"/api/v1/recruiter/jobs/{job['id']}/recommendations",
        token=recruiter_token,
    )
    assert status == 200, initial_recommendations
    assert initial_recommendations["cache"] == "miss"
    prompt_records = cleanup.get("prompt_records")
    assert isinstance(prompt_records, list)
    prompt_records.append((str(initial_recommendations["correlation_id"]), candidate_id))
    initial_candidate = next(
        item
        for item in initial_recommendations["items"]
        if item["candidate"]["email"] == candidate_email
    )
    assert initial_candidate["score"] == 0.0
    assert initial_candidate["candidate"]["desired_role"] == before_resume["desired_role"]
    assert initial_candidate["candidate"]["skills"] == before_resume["skills"]

    after_resume = dict(before_resume)
    after_resume.update(
        {
            "desired_role": "합성 플랫폼 개발자 AFTER",
            "skills": ["Python", "FastAPI", "PostgreSQL"],
            "years_experience": 3,
            "self_intro": "지원 뒤 수정한 합성 자기소개 AFTER",
        }
    )
    status, _ = request(
        "/api/v1/candidates/me/resume",
        method="POST",
        token=candidate_token,
        body=after_resume,
    )
    assert status == 200

    candidate_b_token, candidate_b_email, candidate_b_id = signup_candidate(f"{suffix}-b")
    candidate_ids.append(candidate_b_id)
    status, _ = request(
        "/api/v1/candidates/me/consents",
        method="POST",
        token=candidate_b_token,
        body={
            "action": "grant",
            "consent_type": "privacy_core",
            "policy_version": "asis-observation-client-value",
        },
    )
    assert status == 201
    candidate_b_resume = {
        **after_resume,
        "phone": f"010-0000-{uuid.uuid4().int % 10000:04d}",
        "self_intro": "캐시 생성 뒤 지원한 두 번째 합성 지원자",
    }
    status, _ = request(
        "/api/v1/candidates/me/resume",
        method="POST",
        token=candidate_b_token,
        body=candidate_b_resume,
    )
    assert status == 200
    status, _ = request(
        f"/api/v1/jobs/{job['id']}/applications",
        method="POST",
        token=candidate_b_token,
    )
    assert status == 201

    candidate_c_token, _, candidate_c_id = signup_candidate(f"{suffix}-c")
    candidate_ids.append(candidate_c_id)
    status, _ = request(
        "/api/v1/candidates/me/consents",
        method="POST",
        token=candidate_c_token,
        body={
            "action": "grant",
            "consent_type": "privacy_core",
            "policy_version": "asis-observation-client-value",
        },
    )
    assert status == 201
    candidate_c_resume = {
        **after_resume,
        "phone": f"010-0000-{uuid.uuid4().int % 10000:04d}",
        "self_intro": "기업 상태 게이트 관찰용 세 번째 합성 지원자",
    }
    status, _ = request(
        "/api/v1/candidates/me/resume",
        method="POST",
        token=candidate_c_token,
        body=candidate_c_resume,
    )
    assert status == 200

    status, current_pipeline = request(
        f"/api/v1/recruiter/jobs/{job['id']}/pipeline",
        token=recruiter_token,
    )
    assert status == 200, current_pipeline
    current_by_email = {
        item["candidate"]["email"]: item for item in current_pipeline["items"]
    }
    assert current_by_email[candidate_email]["candidate"]["skills"] == after_resume["skills"]
    assert candidate_b_email in current_by_email

    status, stale_recommendations = request(
        f"/api/v1/recruiter/jobs/{job['id']}/recommendations",
        token=recruiter_token,
    )
    assert status == 200, stale_recommendations
    assert stale_recommendations["cache"] == "hit"
    stale_by_email = {
        item["candidate"]["email"]: item for item in stale_recommendations["items"]
    }
    assert candidate_b_email not in stale_by_email
    assert stale_by_email[candidate_email]["score"] == 0.0
    assert (
        stale_by_email[candidate_email]["candidate"]["desired_role"]
        == before_resume["desired_role"]
    )
    assert stale_by_email[candidate_email]["candidate"]["skills"] == before_resume["skills"]

    job_after = dict(job_before)
    job_after["title"] = "합성 플랫폼 개발자 공고 AFTER"
    status, _ = request(
        f"/api/v1/recruiter/jobs/{job['id']}",
        method="PUT",
        token=recruiter_token,
        body=job_after,
    )
    assert status == 200
    cleanup["job_body"] = job_after

    status, updated_profile = request(
        "/api/v1/recruiter/company-profile",
        method="PUT",
        token=recruiter_token,
        body={
            "direction_statement": "지원 뒤 변경한 합성 기업 방향을 현재 조회가 사용하는지 관찰합니다.",
            "declared_values": ["합성 신뢰", "합성 협업"],
        },
    )
    assert status == 200 and updated_profile["source"] == "recruiter_declared"

    status, _ = request(
        "/api/v1/candidates/me/consents/privacy_core",
        method="DELETE",
        token=candidate_token,
    )
    assert status == 201
    status, _ = request(
        "/api/v1/candidates/me/recommendations", token=candidate_token
    )
    assert status == 409, "candidate recommendation should observe the latest revocation"

    company_id = str(recruiter["company_id"])
    assert str(uuid.UUID(company_id)) == company_id
    suspended = psql(
        "jcareer_company_app",
        "jcareer_company",
        f"update companies set status='suspended' where id='{company_id}';",
    )
    assert suspended.returncode == 0, suspended.stderr

    status, suspended_public_jobs = request("/api/v1/jobs")
    assert status == 200 and isinstance(suspended_public_jobs, list)
    assert sum(item["id"] == job["id"] for item in suspended_public_jobs) == 1
    status, suspended_public_detail = request(f"/api/v1/jobs/{job['id']}")
    assert status == 200 and suspended_public_detail["id"] == job["id"]

    status, suspended_candidate_recommendations = request(
        "/api/v1/candidates/me/recommendations", token=candidate_b_token
    )
    assert status == 200, suspended_candidate_recommendations
    suspended_candidate_job = next(
        item
        for item in suspended_candidate_recommendations["items"]
        if item["job"]["id"] == job["id"]
    )
    assert suspended_candidate_job["job"]["id"] == job["id"]
    prompt_records = cleanup.get("prompt_records")
    assert isinstance(prompt_records, list)
    prompt_records.extend(
        (
            str(suspended_candidate_recommendations["correlation_id"]),
            str(item["job"]["id"]),
        )
        for item in suspended_candidate_recommendations["items"]
    )

    status, suspended_application = request(
        f"/api/v1/jobs/{job['id']}/applications",
        method="POST",
        token=candidate_c_token,
    )
    assert status == 201 and suspended_application["status"] == "applied"
    status, suspended_candidate_applications = request(
        "/api/v1/candidates/me/applications", token=candidate_c_token
    )
    assert status == 200 and sum(
        item["job"]["id"] == job["id"] for item in suspended_candidate_applications
    ) == 1

    status, overview = request(
        "/api/v1/recruiter/overview", token=recruiter_token
    )
    assert status == 200, overview
    assert overview["customer_boundary"]["company_status_record"] == "suspended"
    assert overview["customer_boundary"]["company_status_gate_enforced"] is False
    lifecycle_absence_keys = (
        "organization_membership_implemented",
        "invite_and_role_lifecycle_implemented",
        "company_account_withdrawal_implemented",
        "company_ownership_transfer_implemented",
        "company_consent_lifecycle_implemented",
        "company_status_transition_implemented",
        "company_status_actor_modeled",
    )
    assert all(
        overview["customer_boundary"][key] is False
        for key in lifecycle_absence_keys
    )
    assert (
        overview["data_boundary"]["application_job_reference"]
        == "logical_id_without_cross_database_foreign_key"
    )
    assert overview["data_boundary"]["cross_database_atomic_commit"] is False
    recovery_absence_keys = (
        "company_signup_operation_id_implemented",
        "company_signup_idempotency_key_implemented",
        "cross_database_compensation_implemented",
        "cross_database_reconciliation_implemented",
        "cross_database_outbox_implemented",
    )
    assert (
        all(overview["data_boundary"][key] is False for key in recovery_absence_keys)
    )

    status, pipeline = request(
        f"/api/v1/recruiter/jobs/{job['id']}/pipeline",
        token=recruiter_token,
    )
    assert status == 200, pipeline
    observed = next(
        item for item in pipeline["items"] if item["candidate"]["email"] == candidate_email
    )
    assert observed["candidate"]["desired_role"] == after_resume["desired_role"]
    assert observed["candidate"]["skills"] == after_resume["skills"]
    assert observed["candidate"]["self_intro"] == after_resume["self_intro"]
    assert pipeline["job"]["title"] == job_after["title"]
    assert (
        pipeline["job"]["company_profile"]["profile_version"]
        == updated_profile["profile_version"]
    )

    audit_before_miss = recruiter_audit_count(recruiter["id"], company_id)
    status, recommendations = request(
        f"/api/v1/recruiter/jobs/{job['id']}/recommendations",
        token=recruiter_token,
    )
    assert status == 200, recommendations
    audit_after_miss = recruiter_audit_count(recruiter["id"], company_id)
    assert audit_after_miss == audit_before_miss
    assert any(
        item["candidate"]["email"] == candidate_email
        for item in recommendations["items"]
    ), "revoked candidate remains readable through the current enterprise path"
    refreshed_by_email = {
        item["candidate"]["email"]: item for item in recommendations["items"]
    }
    assert recommendations["cache"] == "miss"
    assert refreshed_by_email[candidate_email]["score"] == 100.0
    assert refreshed_by_email[candidate_email]["candidate"]["skills"] == after_resume["skills"]
    assert candidate_b_email in refreshed_by_email

    prompt_records = cleanup.get("prompt_records")
    assert isinstance(prompt_records, list)
    prompt_records.extend(
        (str(recommendations["correlation_id"]), str(item["candidate"]["user_id"]))
        for item in recommendations["items"]
    )

    status, cached_recommendations = request(
        f"/api/v1/recruiter/jobs/{job['id']}/recommendations",
        token=recruiter_token,
    )
    assert status == 200 and cached_recommendations["cache"] == "hit"
    audit_after_hit = recruiter_audit_count(recruiter["id"], company_id)
    assert audit_after_hit == audit_after_miss

    cache_key, cache_payload = recruiter_cache_entry(
        job["id"], recommendations["correlation_id"]
    )
    cached_items = cache_payload.get("items")
    assert isinstance(cached_items, list) and cached_items
    assert isinstance(cached_items[0], dict)
    assert cached_items[0].pop("score_breakdown", None) is not None
    written = redis_cli(
        "-x",
        "SETEX",
        cache_key,
        "86400",
        input_text=json.dumps(cache_payload, ensure_ascii=False, default=str),
    )
    assert written.returncode == 0, "synthetic nested cache mutation failed"
    status, weakly_validated_cache = request(
        f"/api/v1/recruiter/jobs/{job['id']}/recommendations",
        token=recruiter_token,
    )
    assert status == 200 and weakly_validated_cache["cache"] == "hit"
    assert any(
        "score_breakdown" not in item
        for item in weakly_validated_cache["items"]
    )

    restored_for_public_observation = psql(
        "jcareer_company_app",
        "jcareer_company",
        f"update companies set status='approved' where id='{company_id}';",
    )
    assert restored_for_public_observation.returncode == 0
    status, public_jobs_before_close = request("/api/v1/jobs")
    assert status == 200 and isinstance(public_jobs_before_close, list)
    assert sum(item["id"] == job["id"] for item in public_jobs_before_close) == 1
    close_observation_job(
        recruiter_token,
        str(job["id"]),
        job_after,
        strict=True,
    )
    status, public_jobs = request("/api/v1/jobs")
    assert status == 200 and isinstance(public_jobs, list)
    assert sum(item["id"] == job["id"] for item in public_jobs) == 0
    status, public_closed_detail = request(f"/api/v1/jobs/{job['id']}")
    assert status == 200, public_closed_detail
    assert public_closed_detail["id"] == job["id"]
    assert public_closed_detail["status"] == "closed"
    assert public_closed_detail["company_id"] == target_company_id
    assert public_closed_detail["company_profile"] == updated_profile

    observe_api_token_reuse_and_account_active_gate(cleanup, suffix)
    observe_recruiter_logical_link_resolution(
        cleanup,
        recruiter_token=attacker_token,
        recruiter_user_id=attacker_user_id,
        original_company_id=attacker_company_id,
        alternate_company_id=target_company_id,
    )

    print("J-Career two-sided AS-IS observation scenarios: OBSERVED")
    print("company_status_gate_observed=public-list,public-detail,candidate-application,candidate-application-tracker,candidate-recommendations,overview,pipeline,recruiter-recommendations")
    print("company_lifecycle_declaration_observed=signup-one-recruiter-no-cardinality,signup-default-approved,seven-lifecycle-absences,logical-job-ref,no-atomic-commit,no-operation-id,no-idempotency,no-compensation,no-reconciliation,no-outbox")
    print("pipeline_material_source=current-resume,current-job,current-company-profile")
    print("candidate_recommendation_after_revoke=409; enterprise_read_after_revoke=200")
    print("recruiter_cache_dependency_observed=resume-and-applicant-set-omitted")
    print("recommendation_audit_delta=miss:0,hit:0")
    print("cache_item_schema_observed=missing-score-breakdown-returned")
    print("application_audit_shape=submitted:job-only,status-change:application-and-new-status-only")
    print("internal_service_auth_observed=agent-and-llm-operations-without-caller-token")
    print("prompt_field_boundary_observed=8-prepared,6-classified-pii,score-effect-none")
    print("authorization_denial_tenant_shape_observed=actor-company,target-object,no-target-company-snapshot")
    print("public_closed_job_detail_observed=baseline-open:1,list-after-close:0,detail-present")


def main() -> None:
    with_job_cleanup(run_observations)()


if __name__ == "__main__":
    main()
