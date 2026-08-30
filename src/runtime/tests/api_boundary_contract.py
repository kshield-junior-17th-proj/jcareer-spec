from __future__ import annotations

import asyncio
import copy
import inspect
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


API_ROOT = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(API_ROOT))

import app.main as api_main  # noqa: E402
from app.main import (  # noqa: E402
    ConsentRequest,
    CompanyProfileRequest,
    JobRequest,
    LoginRequest,
    RecruiterSignupRequest,
    ResumeRequest,
    SignupRequest,
    _validate_explanation_response,
    _validate_matcher_response,
)
from app.database import OutcomeBase, database_target  # noqa: E402
from app.outcome_store import (  # noqa: E402
    DATASET_VERSION,
    FEATURE_SCHEMA_VERSION,
    GENERATION_METHOD,
    LABEL_SEMANTICS,
    RESULT_SOURCE,
    SOURCE_PROFILE,
    OutcomeDataset,
    SyntheticDocumentOutcome,
    outcome_observation_revision,
)
from app.seed import required_seed_ids  # noqa: E402


def expect_rejected(model, **values: object) -> None:
    try:
        model(**values)
    except ValidationError:
        return
    raise AssertionError(f"{model.__name__} unexpectedly accepted invalid input")


def valid_matcher_envelope() -> tuple[dict[str, object], dict[str, object]]:
    request_payload: dict[str, object] = {
        "candidate": {
            "id": "candidate-1",
            "desired_role": "백엔드 엔지니어",
            "skills": ["Python"],
            "years_experience": 3,
        },
        "jobs": [
            {
                "id": "job-1",
                "title": "백엔드 엔지니어",
                "required_skills": ["Python"],
                "min_experience": 2,
            }
        ],
        "limit": 20,
    }
    body: dict[str, object] = {
        "status": "AVAILABLE",
        "matcher_version": "deterministic-matcher-v1",
        "items": [
            {
                "subject_ref": "job-1",
                "matcher_version": "deterministic-matcher-v1",
                "score": 100.0,
                "score_breakdown": {
                    "schema_version": "score-breakdown-v1",
                    "formula_version": "deterministic-70-20-10-v1",
                    "policy_source": "platform_default",
                    "formula": "기술 70 + 경력 20 + 직무 연관 10",
                    "total_points": 100.0,
                    "max_points": 100.0,
                    "configured_priority_factor_id": "skills",
                    "largest_contribution_factor_ids": ["skills"],
                    "factors": [
                        {
                            "factor_id": "skills",
                            "label": "요구 기술 일치",
                            "raw_points": 70.0,
                            "display_points": 70.0,
                            "max_points": 70.0,
                            "calculation": "정규화 후 일치 1개 / 요구 1개",
                            "evidence": ["요구 기술 ‘Python’ 일치"],
                            "details": {},
                        },
                        {
                            "factor_id": "experience",
                            "label": "경력 조건",
                            "raw_points": 20.0,
                            "display_points": 20.0,
                            "max_points": 20.0,
                            "calculation": "min(3년 / 2년, 1)",
                            "evidence": ["후보 경력 3년 · 요구 2년"],
                            "details": {},
                        },
                        {
                            "factor_id": "role",
                            "label": "희망 직무 연관",
                            "raw_points": 10.0,
                            "display_points": 10.0,
                            "max_points": 10.0,
                            "calculation": "공고 직무 토큰과 희망 직무의 정규화 부분 일치",
                            "evidence": ["희망 직무와 공고 직무 연관"],
                            "details": {},
                        },
                    ],
                    "excluded_input_fields": [
                        "name",
                        "phone",
                        "email",
                        "birthdate",
                        "address",
                        "school",
                        "certificates",
                        "projects",
                        "self_intro",
                    ],
                },
                "matched_feature_ids": [
                    "skill.python",
                    "experience.minimum_met",
                    "role.title_overlap",
                ],
                "matched_feature_labels": [
                    "요구 기술 ‘Python’ 일치",
                    "관련 경력 3년 · 요구 2년",
                    "희망 직무와 공고 직무 연관",
                ],
            }
        ],
    }
    return body, request_payload


async def operations_snapshot(
    handler,
) -> api_main.AiServiceOperationsResponse:
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return await api_main.ai_service_operations_snapshot(client)


def main() -> None:
    os.environ["DATASET_PROFILE"] = "demo_not_for_measurement"
    os.environ["OPENDART_MODE"] = "fixture"
    os.environ["OPENDART_DISPATCH_MODE"] = "fixture_inline"
    api_main.LLM_PROVIDER = "local-synthetic-stub"

    async def cache_probe(path: str) -> api_main.Response:
        async def call_next(_request) -> api_main.Response:
            return api_main.Response(content="{}", media_type="application/json")

        request = SimpleNamespace(url=SimpleNamespace(path=path))
        return await api_main.prevent_api_response_storage(request, call_next)

    protected_api_response = asyncio.run(cache_probe("/api/v1/candidates/me/resume"))
    assert protected_api_response.headers["cache-control"] == "no-store, private"
    assert protected_api_response.headers["pragma"] == "no-cache"
    non_api_response = asyncio.run(cache_probe("/health"))
    assert "cache-control" not in non_api_response.headers
    assert "pragma" not in non_api_response.headers

    public_http_response = api_main.Response()
    runtime = api_main.runtime_info(public_http_response).model_dump(mode="json")
    assert public_http_response.headers["cache-control"] == "no-store"
    assert runtime["dataset_profile"] == "demo_not_for_measurement"
    assert runtime["explanation_provider"] == "local-synthetic-stub"
    assert "ai_service_operations" not in runtime

    def healthy_services(request: httpx.Request) -> httpx.Response:
        if request.url.port == 8100:
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "service": "agent",
                    "matcher_version": "deterministic-0.2.0",
                    "formula_version": "deterministic-70-20-10-v1",
                },
            )
        if request.url.port == 8200:
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "service": "llm-gateway",
                    "provider": "local-synthetic-stub",
                    "bedrock_live_enabled": "false",
                },
            )
        raise AssertionError("unexpected internal health target")

    operations_model = asyncio.run(operations_snapshot(healthy_services))
    operations = operations_model.model_dump(mode="json")
    assert operations["contract_version"] == "ai-service-operations-v2"
    assert operations["dataset_scope"] == "SYNTHETIC_DEMO_ONLY"
    assert operations["stale_after_seconds"] == 30
    assert operations["matcher"]["probe_state"] == "AVAILABLE"
    assert operations["matcher"]["matcher_version"] == "deterministic-0.2.0"
    assert operations["matcher"]["formula_version"] == "deterministic-70-20-10-v1"
    assert operations["matcher"]["external_model_used_for_score"] is False
    assert operations["llm_gateway"]["probe_state"] == "AVAILABLE"
    assert operations["llm_gateway"]["provider"] == "local-synthetic-stub"
    assert operations["llm_gateway"]["bedrock_live_enabled"] is False
    assert operations["llm_gateway"]["score_effect"] == "NONE"
    assert operations["llm_gateway"]["ranking_effect"] == "NONE"
    assert operations["opendart"]["evidence_state"] == "SOURCE_CONFIGURATION_NOT_PROBED"
    assert operations["opendart"]["probe_state"] == "NOT_PROBED"
    assert operations["opendart"]["mode"] == "fixture"
    assert operations["opendart"]["dispatch_mode"] == "fixture_inline"
    assert operations["outcome_observation"]["probe_state"] == "NOT_PROBED"
    assert operations["outcome_observation"]["response_wired"] is True
    assert {
        operations["outcome_observation"][key]
        for key in ("runtime_effect", "ranking_effect", "model_effect")
    } == {"NONE"}
    assert operations["mlops"]["probe_state"] == "NOT_PROBED"
    assert operations["mlops"]["runtime_wired"] is False
    assert operations["mlops"]["ranking_runtime_wired"] is False
    assert operations["mlops"]["automatic_model_activation"] is False
    assert operations["external_service_call_proven"] is False
    assert operations["aws_deployment_proven"] is False
    assert operations["human_review_required"] is True

    os.environ["OPENDART_MODE"] = "disabled"
    disabled_operations = asyncio.run(operations_snapshot(healthy_services)).model_dump(
        mode="json"
    )
    assert disabled_operations["opendart"]["mode"] == "disabled"

    strict_extra = copy.deepcopy(operations)
    strict_extra["unexpected"] = "rejected"
    expect_rejected(api_main.AiServiceOperationsResponse, **strict_extra)

    def assert_no_sensitive_status_keys(value: object) -> None:
        if isinstance(value, dict):
            forbidden = {
                "secret",
                "credential",
                "api_key",
                "account_id",
                "arn",
                "model_id",
                "base_url",
                "password",
                "token",
                "endpoint",
            }
            assert not forbidden.intersection(str(key).lower() for key in value)
            for nested in value.values():
                assert_no_sensitive_status_keys(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_no_sensitive_status_keys(nested)

    assert_no_sensitive_status_keys(operations)

    os.environ["OPENDART_MODE"] = "live"
    os.environ["OPENDART_DISPATCH_MODE"] = "serverless_queue"

    def bedrock_gateway(request: httpx.Request) -> httpx.Response:
        if request.url.port == 8100:
            return healthy_services(request)
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "service": "llm-gateway",
                "provider": "bedrock",
                "bedrock_live_enabled": "true",
            },
        )

    bedrock_operations = asyncio.run(operations_snapshot(bedrock_gateway)).model_dump(mode="json")
    assert bedrock_operations["llm_gateway"]["provider"] == "bedrock"
    assert bedrock_operations["llm_gateway"]["bedrock_live_enabled"] is True
    assert bedrock_operations["opendart"]["mode"] == "live"
    assert bedrock_operations["opendart"]["dispatch_mode"] == "serverless_queue"

    canary = "sensitive-status-canary"
    os.environ["DATASET_PROFILE"] = canary
    os.environ["OPENDART_MODE"] = canary
    os.environ["OPENDART_DISPATCH_MODE"] = canary
    api_main.LLM_PROVIDER = canary

    def invalid_health(request: httpx.Request) -> httpx.Response:
        if request.url.port == 8100:
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "service": "agent",
                    "matcher_version": canary,
                    "formula_version": canary,
                },
            )
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "service": "llm-gateway",
                "provider": [canary],
                "bedrock_live_enabled": {"value": canary},
            },
        )

    invalid_operations = asyncio.run(operations_snapshot(invalid_health)).model_dump(mode="json")
    assert invalid_operations["matcher"]["matcher_version"] == "UNRECOGNIZED_CONFIGURATION"
    assert invalid_operations["llm_gateway"]["probe_state"] == "UNAVAILABLE"
    assert invalid_operations["llm_gateway"]["provider"] == "UNRECOGNIZED_CONFIGURATION"
    assert invalid_operations["opendart"]["mode"] == "UNRECOGNIZED_CONFIGURATION"
    assert canary not in json.dumps(invalid_operations)
    invalid_runtime = api_main.runtime_info(api_main.Response()).model_dump(mode="json")
    assert invalid_runtime["dataset_profile"] == "UNRECOGNIZED_CONFIGURATION"
    assert invalid_runtime["explanation_provider"] == "UNRECOGNIZED_CONFIGURATION"
    assert canary not in json.dumps(invalid_runtime)

    def unavailable_health(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("internal service unavailable", request=request)

    unavailable_operations = asyncio.run(operations_snapshot(unavailable_health)).model_dump(mode="json")
    assert unavailable_operations["matcher"]["probe_state"] == "UNAVAILABLE"
    assert unavailable_operations["matcher"]["matcher_version"] == "NOT_OBSERVED"
    assert unavailable_operations["llm_gateway"]["probe_state"] == "UNAVAILABLE"
    assert unavailable_operations["llm_gateway"]["provider"] == "NOT_OBSERVED"

    def oversized_health(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"x" * (api_main.INTERNAL_HEALTH_RESPONSE_MAX_BYTES + 1),
        )

    oversized_operations = asyncio.run(operations_snapshot(oversized_health)).model_dump(
        mode="json"
    )
    assert oversized_operations["matcher"]["probe_state"] == "UNAVAILABLE"
    assert oversized_operations["llm_gateway"]["probe_state"] == "UNAVAILABLE"
    probe_source = inspect.getsource(api_main._probe_internal_health)
    assert 'client.stream("GET"' in probe_source
    assert "aiter_bytes(chunk_size=4096)" in probe_source
    assert "response.content" not in probe_source

    class FakeAuditDb:
        def __init__(self) -> None:
            self.added: list[object] = []
            self.committed = False

        def add(self, value: object) -> None:
            self.added.append(value)

        def commit(self) -> None:
            self.committed = True

    original_snapshot = api_main.ai_service_operations_snapshot

    async def fixed_snapshot() -> api_main.AiServiceOperationsResponse:
        return operations_model

    audit_db = FakeAuditDb()
    admin_http_response = api_main.Response()
    api_main.ai_service_operations_snapshot = fixed_snapshot
    try:
        admin_response = asyncio.run(
            api_main.admin_ai_operations(
                http_response=admin_http_response,
                db=audit_db,
                user=SimpleNamespace(id="admin-synthetic", role="admin", company_id=None),
            )
        )
    finally:
        api_main.ai_service_operations_snapshot = original_snapshot
    assert admin_response is operations_model
    assert admin_http_response.headers["cache-control"] == "no-store"
    assert audit_db.committed is True
    assert len(audit_db.added) == 1
    assert audit_db.added[0].event_type == "ai_operations_snapshot_viewed"

    os.environ["DATASET_PROFILE"] = "demo_not_for_measurement"
    os.environ["OPENDART_MODE"] = "fixture"
    os.environ["OPENDART_DISPATCH_MODE"] = "fixture_inline"
    api_main.LLM_PROVIDER = "local-synthetic-stub"

    provider_config = api_main.explanation_provider_config()
    assert provider_config == {
        "provider": "local-synthetic-stub",
        "contract_version": "score-explanation-v1",
        "client_region": "NOT_APPLICABLE",
        "model_ref_hash": "NOT_APPLICABLE",
        "provider_config_fingerprint": provider_config["provider_config_fingerprint"],
    }
    assert len(provider_config["provider_config_fingerprint"]) == 64
    current_attempt = api_main.explanation_attempt_metadata(
        "UNAVAILABLE_PROVIDER", item_count=1, scope="CURRENT_REQUEST"
    )
    assert current_attempt["gateway_receipt_state"] == "NOT_CONFIRMED"
    assert current_attempt["external_provider_receipt_state"] == "NOT_ASSERTED"
    assert current_attempt["score_effect"] == "NONE"
    assert current_attempt["prepared_field_set_state"] == "CURRENT_REQUEST_PREPARED_BY_API"
    assert current_attempt["candidate_fields_prepared"] == api_main.EXPECTED_PROMPT_FIELDS
    cached_attempt = api_main.explanation_attempt_metadata(
        "AVAILABLE", item_count=1, scope="CACHED_ORIGIN_REQUEST"
    )
    assert (
        cached_attempt["gateway_receipt_state"]
        == "CACHE_ENTRY_ACCEPTED_ORIGIN_NOT_VERIFIED"
    )
    assert cached_attempt["prepared_field_set_state"] == "CACHE_ORIGIN_FIELD_SET_NOT_VERIFIED"
    assert cached_attempt["candidate_fields_prepared"] == []
    assert cached_attempt["classified_pii_fields"] == []
    assert cached_attempt["company_fields_prepared"] == []
    empty_attempt = api_main.explanation_attempt_metadata(
        "AVAILABLE", item_count=0, scope="CURRENT_REQUEST"
    )
    assert empty_attempt["gateway_receipt_state"] == "NOT_NEEDED_EMPTY_SET"
    assert empty_attempt["prepared_field_set_state"] == "NOT_PREPARED_EMPTY_SUBJECT_SET"
    assert empty_attempt["candidate_fields_prepared"] == []
    assert empty_attempt["classified_pii_fields"] == []
    assert empty_attempt["company_fields_prepared"] == []

    assert database_target(
        "postgresql+psycopg://member_role@db.example:5432/shared?sslmode=require"
    ) == database_target(
        "postgresql+psycopg://company_role@DB.EXAMPLE/shared?application_name=company"
    )
    assert database_target("postgresql+psycopg://role@db.example/member") != database_target(
        "postgresql+psycopg://role@db.example/company"
    )
    assert database_target("sqlite:///./same.db?mode=rw") == database_target(
        "sqlite:///./same.db?timeout=5"
    )

    cache_job = SimpleNamespace(
        id="job-cache-1",
        company_id="company-cache-1",
        company=SimpleNamespace(profile_version="company-profile-cache-v1"),
        title="합성 백엔드 엔지니어",
        summary="합성 추천 캐시 계약을 확인하기 위한 공고 설명입니다.",
        location="합성 서울",
        employment_type="정규직",
        required_skills=["Python"],
        min_experience=2,
        status="open",
        updated_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
    )
    initial_job_contract = api_main.candidate_job_cache_contract([cache_job])
    changed_job = copy.deepcopy(cache_job)
    changed_job.required_skills = ["Python", "FastAPI"]
    assert api_main.candidate_job_cache_contract([changed_job]) != initial_job_contract
    changed_profile = copy.deepcopy(cache_job)
    changed_profile.company.profile_version = "company-profile-cache-v2"
    assert api_main.candidate_job_cache_contract([changed_profile]) != initial_job_contract

    review_company = SimpleNamespace(
        direction_statement="신뢰를 바탕으로 Python 서비스를 운영합니다.",
        declared_values=["신뢰"],
        profile_version="company-profile-review-v1",
    )
    review_job = SimpleNamespace(
        summary="Python 기반 채용 서비스를 개발합니다.",
        required_skills=["Python"],
        updated_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
        company=review_company,
    )
    review_resume = SimpleNamespace(
        self_intro="Python으로 합성 채용 기능을 개발했습니다.",
        projects=[
            {
                "title": "합성 Python 프로젝트",
                "role": "개발",
                "technologies": ["Python"],
                "summary": "신뢰 가능한 합성 데이터 처리를 구현했습니다.",
                "outcome": "합성 결과만 기록했습니다.",
            }
        ],
        updated_at=datetime(2026, 8, 29, tzinfo=timezone.utc),
    )
    recruiter_review = api_main.build_recruiter_review_support(
        review_resume, review_job
    )
    assert recruiter_review["contract_version"] == "recruiter-evidence-review-v1"
    assert recruiter_review["review_boundary"] == {
        "owner": "recruiter",
        "purpose": "candidate_source_material_review",
        "is_candidate_quality_decision": False,
        "is_hiring_probability": False,
        "is_company_fit_decision": False,
        "automatic_hiring_decision": False,
    }
    assert recruiter_review["score_effect"] == "NONE"
    assert recruiter_review["ranking_effect"] == "NONE"
    assert recruiter_review["human_review_required"] is True
    review_evidence = recruiter_review["qualitative_evidence"]
    assert review_evidence["score_effect"] == "NONE"
    assert review_evidence["ranking_effect"] == "NONE"
    assert review_evidence["method"] == "literal-source-span-v1"
    assert review_evidence["claims"]
    assert all(
        claim["support_state"] == "DIRECT_TEXT_EVIDENCE"
        and claim["score_effect"] == "NONE"
        and claim["human_review_required"] is True
        for claim in review_evidence["claims"]
    )
    assert recruiter_review["provenance"] == {
        "candidate_resume_version": review_resume.updated_at.isoformat(),
        "job_version": review_job.updated_at.isoformat(),
        "company_public_profile_version": review_company.profile_version,
        "evidence_contract_version": review_evidence["contract_version"],
    }

    unavailable_observation = api_main.unavailable_historical_observation(
        "company-synthetic-1", "job-synthetic-1"
    )
    assert unavailable_observation["state"] == "UNAVAILABLE_OBSERVATION_STORE"
    assert unavailable_observation["scope"] == {
        "company_id": "company-synthetic-1",
        "job_id": "job-synthetic-1",
    }
    assert unavailable_observation["shared_evidence_tags"] == []
    assert {
        unavailable_observation["runtime_effect"],
        unavailable_observation["ranking_effect"],
        unavailable_observation["model_effect"],
    } == {"NONE"}
    assert not unavailable_observation["is_hiring_probability"]

    outcome_test_engine = create_engine("sqlite:///:memory:")
    OutcomeBase.metadata.create_all(bind=outcome_test_engine)
    with Session(outcome_test_engine) as outcome_test_db:
        empty_revision = outcome_observation_revision(outcome_test_db)
        assert len(empty_revision) == 64
        outcome_test_db.add(
            OutcomeDataset(
                dataset_version=DATASET_VERSION,
                synthetic=True,
                label_semantics=LABEL_SEMANTICS,
                generation_method=GENERATION_METHOD,
                source_profile=SOURCE_PROFILE,
                runtime_effect="NONE",
                ranking_effect="NONE",
                approved_for_model_training=False,
                created_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
            )
        )
        outcome_row = SyntheticDocumentOutcome(
            id="00000000-0000-5000-8000-000000""000001",
            dataset_version=DATASET_VERSION,
            application_ref="syn-application-" + "a" * 24,
            candidate_ref="syn-candidate-" + "b" * 24,
            job_id="job-synthetic-1",
            company_id="company-synthetic-1",
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            feature_snapshot={
                "skill_overlap": 1.0,
                "experience_fit": 0.5,
                "role_overlap": 0.5,
                "self_intro_job_overlap": 0.25,
                "company_direction_overlap": 0.25,
            },
            evidence_tags=["Python"],
            document_result="passed",
            result_source=RESULT_SOURCE,
            observed_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
            created_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
        )
        outcome_test_db.add(outcome_row)
        outcome_test_db.flush()
        populated_revision = outcome_observation_revision(outcome_test_db)
        assert populated_revision != empty_revision
        outcome_row.evidence_tags = ["Python", "FastAPI"]
        changed_revision = outcome_observation_revision(outcome_test_db)
        assert changed_revision != populated_revision
    outcome_test_engine.dispose()

    seed_ids = required_seed_ids()
    assert {label: len(values) for label, values in seed_ids.items()} == {
        "companies": 3,
        "users": 40,
        "resumes": 37,
        "consents": 37,
        "jobs": 12,
        "applications": 75,
        "audit": 1,
    }
    expect_rejected(
        SignupRequest,
        email=f"{'a' * 250}@jcareer.test",
        password="Demo123!",
        display_name="합성 지원자",
    )
    expect_rejected(
        LoginRequest,
        email=f"{'a' * 250}@jcareer.test",
        password="Demo123!",
    )
    expect_rejected(
        RecruiterSignupRequest,
        email="recruiter-boundary@example.invalid",
        password="Demo123!",
        display_name="합성 담당자",
        company_name="  ",
        company_address="합성 주소",
    )
    expect_rejected(
        ConsentRequest,
        action="grant",
        consent_type="privacy_core",
        policy_version="x" * 41,
    )
    assert ConsentRequest(policy_version=" client-version ").policy_version == "client-version"

    resume = ResumeRequest(
        phone="010-0000-0001",
        birth_date=None,
        address_region=" 합성 지역 ",
        education=" 합성 교육기관 ",
        desired_role=" 백엔드 엔지니어 ",
        years_experience=3,
        skills=[" Python ", "PYTHON", "python!", "FastAPI"],
        certificates=[" 합성 자격 ", "합성 자격"],
        self_intro=" 합성 자기소개 ",
    )
    assert resume.skills == ["Python", "FastAPI"]
    assert resume.certificates == ["합성 자격"]
    assert resume.address_region == "합성 지역"
    assert resume.self_intro == "합성 자기소개"
    resume_values = resume.model_dump()
    expect_rejected(ResumeRequest, **{**resume_values, "skills": ["---"]})
    expect_rejected(ResumeRequest, **{**resume_values, "skills": ["x" * 81]})
    expect_rejected(ResumeRequest, **{**resume_values, "certificates": ["x" * 181]})
    expect_rejected(ResumeRequest, **{**resume_values, "desired_role": "  "})

    job_values = {
        "title": " 합성 공고 ",
        "summary": " 합성 입력 경계를 확인하기 위한 충분히 긴 공고 설명입니다. ",
        "location": " 합성시 ",
        "employment_type": " 정규직 ",
        "required_skills": [" Python ", "Python", "FastAPI"],
        "min_experience": 2,
        "status": "open",
    }
    job = JobRequest(**job_values)
    assert job.title == "합성 공고"
    assert job.required_skills == ["Python", "FastAPI"]
    semantic_duplicate_job = JobRequest(
        **{**job_values, "required_skills": ["Python", "PYTHON", "python!", "FastAPI"]}
    )
    assert semantic_duplicate_job.required_skills == ["Python", "FastAPI"]
    expect_rejected(JobRequest, **{**job_values, "required_skills": ["---"]})
    expect_rejected(JobRequest, **{**job_values, "required_skills": ["x" * 81]})
    expect_rejected(JobRequest, **{**job_values, "summary": "          "})
    expect_rejected(
        CompanyProfileRequest,
        direction_statement=" " * 20,
        declared_values=["신뢰"],
    )

    body, request_payload = valid_matcher_envelope()
    _validate_matcher_response(body, "/internal/match/jobs", request_payload)

    invalid_mutations = []
    for feature_ids, feature_labels in (
        ("skill.python", ["Python"]),
        (["skill.python"], []),
        (["unknown.source"], ["unknown"]),
        (["skill.python", "skill.python"], ["Python", "Python"]),
        (["skill.python"], ["x" * 201]),
    ):
        mutated = copy.deepcopy(body)
        item = mutated["items"][0]
        item["matched_feature_ids"] = feature_ids
        item["matched_feature_labels"] = feature_labels
        invalid_mutations.append(mutated)

    for mutated in invalid_mutations:
        try:
            _validate_matcher_response(mutated, "/internal/match/jobs", request_payload)
        except ValueError:
            continue
        raise AssertionError("malformed matcher feature metadata was accepted")

    invalid_breakdowns = []
    bad_calculation = copy.deepcopy(body)
    bad_calculation["items"][0]["score_breakdown"]["factors"][0]["calculation"] = {}
    invalid_breakdowns.append(bad_calculation)
    wrong_factor_order = copy.deepcopy(body)
    wrong_factor_order["items"][0]["score_breakdown"]["factors"].reverse()
    invalid_breakdowns.append(wrong_factor_order)
    wrong_excluded = copy.deepcopy(body)
    wrong_excluded["items"][0]["score_breakdown"]["excluded_input_fields"] = ["name"]
    invalid_breakdowns.append(wrong_excluded)
    for mutated in invalid_breakdowns:
        try:
            _validate_matcher_response(mutated, "/internal/match/jobs", request_payload)
        except ValueError:
            continue
        raise AssertionError("malformed matcher display metadata was accepted")

    ordered = copy.deepcopy(body)
    ordered_request = copy.deepcopy(request_payload)
    ordered_request["jobs"].append(
        {
            "id": "job-2",
            "title": "백엔드 엔지니어",
            "required_skills": ["Python"],
            "min_experience": 2,
        }
    )
    second_item = copy.deepcopy(ordered["items"][0])
    second_item["subject_ref"] = "job-2"
    ordered["items"].append(second_item)
    _validate_matcher_response(ordered, "/internal/match/jobs", ordered_request)
    reversed_items = copy.deepcopy(ordered)
    reversed_items["items"].reverse()
    try:
        _validate_matcher_response(
            reversed_items, "/internal/match/jobs", ordered_request
        )
    except ValueError:
        pass
    else:
        raise AssertionError("matcher ranking order drift was accepted")

    expected_explanations = [
        {
            "subject_ref": "job-1",
            "candidate_context": {
                "self_intro": "합성 자기소개",
                "projects": [
                    {
                        "title": "합성 프로젝트",
                        "role": "백엔드 개발",
                        "technologies": ["Python"],
                        "summary": "합성 데이터 처리 자동화를 구현했습니다.",
                        "outcome": "합성 처리 시간을 단축했습니다.",
                    }
                ],
            },
            "company_context": {
                "profile_version": "company-profile-test-v1",
                "direction_statement": "합성 기업 방향",
                "declared_values": ["신뢰"],
            },
        }
    ]
    explanation = {
        "status": "AVAILABLE",
        "correlation_id": "correlation-1",
        "items": [
            {
                "subject_ref": "job-1",
                "status": "AVAILABLE",
                "text": "합성 설명",
                "provider": "local-synthetic-stub",
                "generation_mode": "deterministic-local-stub",
                "contract_version": "score-explanation-v1",
                "client_region": provider_config["client_region"],
                "model_ref_hash": provider_config["model_ref_hash"],
                "provider_config_fingerprint": provider_config[
                    "provider_config_fingerprint"
                ],
                "output_validation_state": "NOT_IMPLEMENTED_ASIS",
                "prompt_hash": "a" * 64,
                "prompt_fields_prepared": [
                    "address",
                    "birthdate",
                    "certificates",
                    "email",
                    "name",
                    "phone",
                    "projects",
                    "school",
                    "self_intro",
                ],
                "pii_fields_prepared": [
                    "address",
                    "birthdate",
                    "email",
                    "name",
                    "phone",
                    "school",
                ],
                "company_fields_prepared": [
                    "company_name",
                    "declared_values",
                    "direction_statement",
                    "job_summary",
                    "job_title",
                    "profile_version",
                ],
                "company_alignment": {
                    "state": "NO_DIRECT_DECLARED_VALUE_EVIDENCE",
                    "profile_version": "company-profile-test-v1",
                    "direction_statement": "합성 기업 방향",
                    "declared_values": ["신뢰"],
                    "matched_declared_values": [],
                    "basis": "company-declared-profile-and-candidate-materials",
                    "score_effect": "NONE",
                    "human_review_required": True,
                },
            }
        ],
    }
    assert _validate_explanation_response(
        explanation, expected_explanations, "correlation-1"
    )["job-1"]["text"] == "합성 설명"
    assert asyncio.run(api_main.run_explanations([], "empty-correlation")) == (
        "AVAILABLE",
        {},
    )
    invalid_explanations = [
        {**explanation, "items": [None]},
        {**explanation, "items": []},
        {**explanation, "correlation_id": "wrong"},
    ]
    wrong_validation = copy.deepcopy(explanation)
    wrong_validation["items"][0]["output_validation_state"] = "VERIFIED"
    invalid_explanations.append(wrong_validation)
    missing_prompt_field = copy.deepcopy(explanation)
    missing_prompt_field["items"][0]["prompt_fields_prepared"] = ["name"]
    invalid_explanations.append(missing_prompt_field)
    invalid_hash = copy.deepcopy(explanation)
    invalid_hash["items"][0]["prompt_hash"] = "not-a-hash"
    invalid_explanations.append(invalid_hash)
    wrong_provider_config = copy.deepcopy(explanation)
    wrong_provider_config["items"][0]["provider_config_fingerprint"] = "0" * 64
    invalid_explanations.append(wrong_provider_config)
    score_changing_alignment = copy.deepcopy(explanation)
    score_changing_alignment["items"][0]["company_alignment"]["score_effect"] = "CHANGED"
    invalid_explanations.append(score_changing_alignment)
    crossed_alignment = copy.deepcopy(explanation)
    crossed_alignment["items"][0]["company_alignment"]["profile_version"] = "other-profile"
    invalid_explanations.append(crossed_alignment)
    false_positive_alignment = copy.deepcopy(explanation)
    false_positive_alignment["items"][0]["company_alignment"].update(
        {
            "state": "DIRECT_DECLARED_VALUE_EVIDENCE_FOUND",
            "matched_declared_values": ["신뢰"],
        }
    )
    invalid_explanations.append(false_positive_alignment)
    for mutation in invalid_explanations:
        try:
            _validate_explanation_response(
                mutation, expected_explanations, "correlation-1"
            )
        except ValueError:
            continue
        raise AssertionError("malformed explanation envelope was accepted")
    false_negative_expected = copy.deepcopy(expected_explanations)
    false_negative_expected[0]["candidate_context"]["self_intro"] = "신뢰를 중시합니다"
    try:
        _validate_explanation_response(
            explanation, false_negative_expected, "correlation-1"
        )
    except ValueError:
        pass
    else:
        raise AssertionError("false-negative company alignment was accepted")

    class FakeRedis:
        def __init__(self, value: str):
            self.value = value

        async def get(self, _: str) -> str:
            return self.value

        async def aclose(self) -> None:
            return None

    original_redis_client = api_main.redis_client
    try:
        for invalid_cache in ("[]", "null", '{"items": []}'):
            api_main.redis_client = lambda value=invalid_cache: FakeRedis(value)
            assert asyncio.run(api_main.get_cached("synthetic-key")) is None
        valid_cache = {
            "recommendation_status": "AVAILABLE",
            "explanation_status": "AVAILABLE",
            "matcher_version": "deterministic-matcher-v1",
            "correlation_id": "correlation-1",
            "items": [],
            "cache": "miss",
            "explanation_freshness": "CURRENT_REQUEST_GATEWAY_RESULT",
            "explanation_attempt": api_main.explanation_attempt_metadata(
                "AVAILABLE", item_count=0, scope="CURRENT_REQUEST"
            ),
            "provider_config_fingerprint": provider_config[
                "provider_config_fingerprint"
            ],
        }
        api_main.redis_client = lambda: FakeRedis(json.dumps(valid_cache))
        assert asyncio.run(api_main.get_cached("synthetic-key")) == valid_cache
        wrong_partition = copy.deepcopy(valid_cache)
        wrong_partition["provider_config_fingerprint"] = "0" * 64
        api_main.redis_client = lambda: FakeRedis(json.dumps(wrong_partition))
        assert asyncio.run(api_main.get_cached("synthetic-key")) is None
    finally:
        api_main.redis_client = original_redis_client

    print("J-Career API boundary contract: PASS")


if __name__ == "__main__":
    main()
