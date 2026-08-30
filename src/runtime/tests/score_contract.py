from __future__ import annotations

import json
import math
import urllib.error
import urllib.request


AGENT = "http://127.0.0.1:8100"
GATEWAY = "http://127.0.0.1:8200"


def post(base: str, path: str, body: dict[str, object]) -> tuple[int, object]:
    request = urllib.request.Request(
        base + path,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def assert_breakdown(item: dict[str, object], expected_score: float) -> None:
    breakdown = item["score_breakdown"]
    assert item["score"] == expected_score
    assert breakdown["total_points"] == expected_score
    assert breakdown["max_points"] == 100.0
    assert breakdown["formula_version"] == "deterministic-70-20-10-v1"
    assert breakdown["schema_version"] == "score-breakdown-v1"
    factors = breakdown["factors"]
    assert [factor["factor_id"] for factor in factors] == ["skills", "experience", "role"]
    assert math.isclose(sum(factor["max_points"] for factor in factors), 100.0)
    assert round(sum(factor["raw_points"] for factor in factors), 1) == expected_score
    assert "school" in breakdown["excluded_input_fields"]
    assert "address" in breakdown["excluded_input_fields"]


def main() -> None:
    status, body = post(
        AGENT,
        "/internal/match/candidates",
        {
            "job": {
                "id": "job-perfect",
                "title": "백엔드 플랫폼 엔지니어",
                "required_skills": ["Python", "Docker"],
                "min_experience": 2,
            },
            "candidates": [
                {
                    "id": "candidate-perfect",
                    "desired_role": "플랫폼 엔지니어",
                    "skills": ["python", "Docker", "PYTHON"],
                    "years_experience": 4,
                },
                {
                    "id": "candidate-empty-role",
                    "desired_role": "",
                    "skills": ["Python", "Docker"],
                    "years_experience": 4,
                },
            ],
            "limit": 10,
        },
    )
    assert status == 200, body
    items = {item["subject_ref"]: item for item in body["items"]}
    assert_breakdown(items["candidate-perfect"], 100.0)
    assert_breakdown(items["candidate-empty-role"], 90.0)
    assert items["candidate-perfect"]["score_breakdown"]["factors"][2]["details"]["matched"] is True
    assert items["candidate-empty-role"]["score_breakdown"]["factors"][2]["details"]["matched"] is False

    status, partial = post(
        AGENT,
        "/internal/match/candidates",
        {
            "job": {
                "id": "job-rounding",
                "title": "데이터 분석가",
                "required_skills": ["A", "B", "C", "D", "E", "F"],
                "min_experience": 3,
            },
            "candidates": [
                {
                    "id": "candidate-rounding",
                    "desired_role": "보안 엔지니어",
                    "skills": ["A"],
                    "years_experience": 1,
                }
            ],
        },
    )
    assert status == 200, partial
    assert_breakdown(partial["items"][0], 18.3)
    displayed_sum = sum(
        factor["display_points"]
        for factor in partial["items"][0]["score_breakdown"]["factors"]
    )
    assert math.isclose(displayed_sum, 18.4), "the UI must disclose component-versus-total rounding"

    status, invalid = post(
        AGENT,
        "/internal/match/candidates",
        {
            "job": {
                "id": "job-invalid",
                "title": "합성 공고",
                "required_skills": ["---"],
                "min_experience": 0,
            },
            "candidates": [],
        },
    )
    assert status == 422, invalid

    sample = items["candidate-perfect"]
    status, explanation = post(
        GATEWAY,
        "/internal/explanations",
        {
            "items": [
                {
                    "subject_ref": sample["subject_ref"],
                    "score": sample["score"],
                    "score_breakdown": sample["score_breakdown"],
                    "matched_feature_ids": sample["matched_feature_ids"],
                    "matched_feature_labels": sample["matched_feature_labels"],
                    "candidate_context": {
                        "name": "합성지원자",
                        "phone": "010-0000-0000",
                        "email": "candidate@example.invalid",
                        "birthdate": "1995-01-01",
                        "address": "합성시",
                        "school": "합성대학교",
                        "certificates": ["SYNTH-CERT"],
                        "self_intro": "신뢰와 협업을 바탕으로 자동화한 합성 데이터",
                    },
                    "company_context": {
                        "company_name": "합성기업",
                        "direction_statement": "신뢰할 수 있는 서비스를 협업으로 자동화합니다.",
                        "declared_values": ["신뢰", "협업", "자동화", "포용"],
                        "profile_version": "company-profile-test-v1",
                        "job_title": "백엔드 플랫폼 엔지니어",
                        "job_summary": "합성 공고",
                    },
                }
            ],
            "mode": "overclaim",
            "correlation_id": "00000000-0000-0000-0000-a00000000000",
        },
    )
    assert status == 200, explanation
    rendered = explanation["items"][0]
    assert rendered["output_validation_state"] == "NOT_IMPLEMENTED_ASIS"
    assert rendered["generation_mode"] == "synthetic-overclaim-injection"
    assert len(rendered["prompt_fields_prepared"]) == 9
    assert len(rendered["pii_fields_prepared"]) == 6
    assert rendered["company_alignment"]["matched_declared_values"] == ["신뢰", "협업", "자동화"]
    assert rendered["company_alignment"]["score_effect"] == "NONE"
    assert "우선 채용" in rendered["text"]
    assert "score" not in rendered, "the explanation provider cannot overwrite the matcher score"

    print("J-Career score/explanation contract: PASS")
    print("Observed AS-IS scenario: 9 fields prepared, 6 classified as PII, overclaim not blocked.")
    print("Company alignment is evidence-only and does not change the 100-point score.")


if __name__ == "__main__":
    main()
