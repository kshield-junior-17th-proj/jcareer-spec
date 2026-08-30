from __future__ import annotations

import uuid

from smoke import request, wait_ready


MODES = ("timeout", "rate_limit", "provider_error", "malformed")


def signature(payload: dict[str, object]) -> list[tuple[object, ...]]:
    return [
        (
            item["job"]["id"],
            item["score"],
            item["score_breakdown"],
            item["matched_feature_ids"],
            item["matched_feature_labels"],
            item["matcher_version"],
        )
        for item in payload["items"]
    ]


def main() -> None:
    wait_ready()
    suffix = uuid.uuid4().hex[:10]
    phone_suffix = f"{uuid.uuid4().int % 10_000:04d}"
    status, signup = request(
        "/api/v1/auth/signup",
        method="POST",
        body={
            "email": f"resilience-{suffix}@example.invalid",
            "password": "Demo123!",
            "display_name": f"합성 복원력 검증자 {suffix}",
        },
    )
    assert status == 201, signup
    token = signup["access_token"]
    status, consent = request(
        "/api/v1/candidates/me/consents",
        method="POST",
        token=token,
        body={"consent_type": "privacy_core", "action": "grant", "policy_version": "2026-05"},
    )
    assert status == 201, consent
    status, resume = request(
        "/api/v1/candidates/me/resume",
        method="POST",
        token=token,
        body={
            "phone": f"010-0000-{phone_suffix}",
            "birth_date": "1995-01-01",
            "address_region": "합성시",
            "education": "합성대학교",
            "desired_role": "백엔드 엔지니어",
            "years_experience": 4,
            "skills": ["Python", "Docker", "AWS"],
            "certificates": [],
            "self_intro": "LLM 장애 시 추천 점수 보존을 확인하는 합성 이력서입니다.",
        },
    )
    assert status == 200, resume
    status, baseline = request(
        "/api/v1/candidates/me/recommendations", token=token
    )
    assert status == 200, baseline
    assert baseline["recommendation_status"] == "AVAILABLE"
    baseline_signature = signature(baseline)

    for mode in MODES:
        status, degraded = request(
            f"/api/v1/candidates/me/recommendations?explanation_mode={mode}",
            token=token,
        )
        assert status == 200, (mode, degraded)
        assert degraded["recommendation_status"] == "AVAILABLE"
        assert degraded["explanation_status"] == "UNAVAILABLE_PROVIDER"
        assert degraded["cache"] == "miss"
        assert signature(degraded) == baseline_signature

    print("J-Career LLM degradation smoke: PASS")


if __name__ == "__main__":
    main()
