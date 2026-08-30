from __future__ import annotations

import re
import math
import os
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field, field_validator


app = FastAPI(
    title="J-Career deterministic matcher",
    version="0.2.0",
    description="Synthetic AS-IS runtime matcher. It does not make hiring decisions.",
)

MATCHER_VERSION = os.getenv("MATCHER_VERSION", "deterministic-0.2.0")
FORMULA_VERSION = os.getenv("SCORING_FORMULA_VERSION", "deterministic-70-20-10-v1")
BREAKDOWN_SCHEMA_VERSION = os.getenv("SCORE_BREAKDOWN_SCHEMA_VERSION", "score-breakdown-v1")
SKILL_MAX_POINTS = float(os.getenv("SKILL_MAX_POINTS", "70"))
EXPERIENCE_MAX_POINTS = float(os.getenv("EXPERIENCE_MAX_POINTS", "20"))
ROLE_MAX_POINTS = float(os.getenv("ROLE_MAX_POINTS", "10"))
MAX_TOTAL_POINTS = SKILL_MAX_POINTS + EXPERIENCE_MAX_POINTS + ROLE_MAX_POINTS

if (
    not math.isclose(SKILL_MAX_POINTS, 70.0, abs_tol=1e-9)
    or not math.isclose(EXPERIENCE_MAX_POINTS, 20.0, abs_tol=1e-9)
    or not math.isclose(ROLE_MAX_POINTS, 10.0, abs_tol=1e-9)
):
    raise RuntimeError("deterministic-70-20-10-v1 requires exact 70/20/10 weights")


class JobInput(BaseModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    required_skills: list[str] = Field(min_length=1)
    min_experience: int = Field(default=0, ge=0, le=50)

    @field_validator("required_skills")
    @classmethod
    def require_normalisable_skill(cls, values: list[str]) -> list[str]:
        if not any(re.sub(r"[^0-9a-zA-Z가-힣+#.]", "", value) for value in values):
            raise ValueError("required_skills must contain a normalisable skill")
        return values


class CandidateInput(BaseModel):
    id: str = Field(min_length=1)
    desired_role: str = ""
    skills: list[str] = Field(default_factory=list)
    years_experience: int = Field(default=0, ge=0, le=60)


class ScoreFactor(BaseModel):
    factor_id: Literal["skills", "experience", "role"]
    label: str
    raw_points: float
    display_points: float
    max_points: float
    calculation: str
    evidence: list[str] = Field(default_factory=list)
    details: dict[str, object] = Field(default_factory=dict)


class ScoreBreakdown(BaseModel):
    schema_version: str = BREAKDOWN_SCHEMA_VERSION
    formula_version: str = FORMULA_VERSION
    policy_source: Literal["platform_default"] = "platform_default"
    formula: str
    total_points: float
    max_points: float = MAX_TOTAL_POINTS
    configured_priority_factor_id: Literal["skills", "experience", "role"]
    largest_contribution_factor_ids: list[Literal["skills", "experience", "role"]]
    factors: list[ScoreFactor]
    excluded_input_fields: list[str]


class MatchCandidatesRequest(BaseModel):
    job: JobInput
    candidates: list[CandidateInput]
    limit: int = Field(default=20, ge=1, le=100)


class MatchJobsRequest(BaseModel):
    candidate: CandidateInput
    jobs: list[JobInput]
    limit: int = Field(default=20, ge=1, le=100)


class MatchResult(BaseModel):
    subject_ref: str
    score: float
    score_breakdown: ScoreBreakdown
    matched_feature_ids: list[str]
    matched_feature_labels: list[str]
    matcher_version: str = MATCHER_VERSION


def _normalise(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣+#.]", "", value).lower()


def calculate_score(job: JobInput, candidate: CandidateInput) -> MatchResult:
    """Calculate a stable score from job-relevant structured fields only."""

    required = {_normalise(skill): skill for skill in job.required_skills if _normalise(skill)}
    candidate_skills = {
        _normalise(skill): skill for skill in candidate.skills if _normalise(skill)
    }
    overlaps = sorted(set(required).intersection(candidate_skills))

    skill_score = SKILL_MAX_POINTS * len(overlaps) / len(required)

    if job.min_experience <= 0:
        experience_score = EXPERIENCE_MAX_POINTS
        experience_ratio = 1.0
    else:
        experience_ratio = min(
            max(candidate.years_experience, 0) / job.min_experience, 1.0
        )
        experience_score = EXPERIENCE_MAX_POINTS * experience_ratio

    title_tokens = {
        normalised
        for token in re.split(r"[\s/·,_-]+", job.title)
        if len(normalised := _normalise(token)) >= 2
    }
    role = _normalise(candidate.desired_role)
    role_matched = bool(
        role
        and any(token in role or role in token for token in title_tokens)
    )
    role_score = ROLE_MAX_POINTS if role_matched else 0.0

    features: list[str] = []
    labels: list[str] = []
    for key in overlaps:
        features.append(f"skill.{key}")
        labels.append(f"요구 기술 ‘{required[key]}’ 일치")

    if candidate.years_experience >= job.min_experience:
        features.append("experience.minimum_met")
        labels.append(
            f"관련 경력 {candidate.years_experience}년 · 요구 {job.min_experience}년"
        )

    if role_score:
        features.append("role.title_overlap")
        labels.append(f"희망 직무 ‘{candidate.desired_role}’와 공고 직무 연관")

    factors = [
        ScoreFactor(
            factor_id="skills",
            label="요구 기술 일치",
            raw_points=round(skill_score, 6),
            display_points=round(skill_score, 1),
            max_points=SKILL_MAX_POINTS,
            calculation=f"정규화 후 일치 {len(overlaps)}개 / 요구 {len(required)}개",
            evidence=[f"요구 기술 ‘{required[key]}’ 일치" for key in overlaps],
            details={
                "matched_count": len(overlaps),
                "required_count": len(required),
                "normalisation": "case-and-punctuation-insensitive-unique",
            },
        ),
        ScoreFactor(
            factor_id="experience",
            label="경력 조건",
            raw_points=round(experience_score, 6),
            display_points=round(experience_score, 1),
            max_points=EXPERIENCE_MAX_POINTS,
            calculation=(
                "최소 경력 없음: 최대점"
                if job.min_experience == 0
                else f"min({candidate.years_experience}년 / {job.min_experience}년, 1)"
            ),
            evidence=[
                f"후보 경력 {candidate.years_experience}년 · 요구 {job.min_experience}년"
            ],
            details={
                "candidate_years": candidate.years_experience,
                "required_years": job.min_experience,
                "capped_ratio": round(experience_ratio, 6),
            },
        ),
        ScoreFactor(
            factor_id="role",
            label="희망 직무 연관",
            raw_points=round(role_score, 6),
            display_points=round(role_score, 1),
            max_points=ROLE_MAX_POINTS,
            calculation="공고 직무 토큰과 희망 직무의 정규화 부분 일치",
            evidence=(
                [f"희망 직무 ‘{candidate.desired_role}’와 공고 직무 연관"]
                if role_matched
                else []
            ),
            details={"matched": role_matched},
        ),
    ]
    raw_total = sum(factor.raw_points for factor in factors)
    configured_priority = max(factors, key=lambda factor: factor.max_points)
    largest_points = max(factor.raw_points for factor in factors)
    largest_contribution_ids = [
        factor.factor_id
        for factor in factors
        if math.isclose(factor.raw_points, largest_points, abs_tol=1e-9)
    ]
    total = round(min(raw_total, MAX_TOTAL_POINTS), 1)
    breakdown = ScoreBreakdown(
        formula=(
            f"기술 {SKILL_MAX_POINTS:g} + 경력 {EXPERIENCE_MAX_POINTS:g} "
            f"+ 직무 연관 {ROLE_MAX_POINTS:g}"
        ),
        total_points=total,
        configured_priority_factor_id=configured_priority.factor_id,
        largest_contribution_factor_ids=largest_contribution_ids,
        factors=factors,
        excluded_input_fields=[
            "name",
            "phone",
            "email",
            "birthdate",
            "address",
            "school",
            "certificates",
            "self_intro",
        ],
    )

    return MatchResult(
        subject_ref=candidate.id,
        score=total,
        score_breakdown=breakdown,
        matched_feature_ids=features,
        matched_feature_labels=labels,
    )


@app.get("/agent/health")
@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "agent",
        "matcher_version": MATCHER_VERSION,
        "formula_version": FORMULA_VERSION,
    }


@app.post("/agent/internal/match/candidates")
@app.post("/internal/match/candidates")
def match_candidates(request: MatchCandidatesRequest) -> dict[str, object]:
    results = [calculate_score(request.job, candidate) for candidate in request.candidates]
    results.sort(key=lambda item: (-item.score, item.subject_ref))
    return {
        "status": "AVAILABLE",
        "matcher_version": MATCHER_VERSION,
        "items": [item.model_dump() for item in results[: request.limit]],
    }


@app.post("/agent/internal/match/jobs")
@app.post("/internal/match/jobs")
def match_jobs(request: MatchJobsRequest) -> dict[str, object]:
    items: list[dict[str, object]] = []
    for job in request.jobs:
        match = calculate_score(job, request.candidate)
        payload = match.model_dump()
        payload["subject_ref"] = job.id
        items.append(payload)
    items.sort(key=lambda item: (-float(item["score"]), str(item["subject_ref"])))
    return {
        "status": "AVAILABLE",
        "matcher_version": MATCHER_VERSION,
        "items": items[: request.limit],
    }
