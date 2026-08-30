from __future__ import annotations

import asyncio
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from pydantic import ValidationError


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
from app.database import database_target  # noqa: E402
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


def main() -> None:
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
            "candidate_context": {"self_intro": "합성 자기소개"},
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
                    "basis": "company-declared-profile-and-self-introduction",
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
