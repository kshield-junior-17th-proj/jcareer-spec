from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Literal

import httpx
import redis
import redis.asyncio as async_redis
from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import String, cast, delete, func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from .database import (
    CompanyBase,
    MemberBase,
    SessionLocal,
    company_engine,
    ensure_runtime_schema,
    get_db,
    member_engine,
)
from .models import Application, AuditEvent, Company, ConsentEvent, Job, Resume, User
from .opendart import (
    OpenDartClient,
    OpenDartError,
    company_names_match,
    public_snapshot,
)
from .opendart_dispatch import (
    OpenDartDispatchError,
    build_refresh_message,
    enqueue_refresh,
)
from .security import current_user, hash_password, issue_token, require_role, verify_password
from .seed import seed_demo


AGENT_BASE_URL = os.getenv("AGENT_BASE_URL", "http://localhost:8100")
LLM_GATEWAY_BASE_URL = os.getenv("LLM_GATEWAY_BASE_URL", "http://localhost:8200")
LLM_GATEWAY_TIMEOUT_SECONDS = float(os.getenv("LLM_GATEWAY_TIMEOUT_SECONDS", "15"))
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "local-synthetic-stub")
BEDROCK_REGION = os.getenv("BEDROCK_REGION", os.getenv("AWS_REGION", "ap-northeast-2"))
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "apac.amazon.nova-lite-v1:0")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
FAILURE_INJECTION_ENABLED = os.getenv("ENABLE_FAILURE_INJECTION", "false").lower() == "true"
SCORE_RESPONSE_CONTRACT_VERSION = "score-contract-v2"
EXPLANATION_CONTRACT_VERSION = "score-explanation-v1"
EXPECTED_PROMPT_FIELDS = [
    "address",
    "birthdate",
    "certificates",
    "email",
    "name",
    "phone",
    "school",
    "self_intro",
]
EXPECTED_PII_FIELDS = ["address", "birthdate", "email", "name", "phone", "school"]
EXPECTED_COMPANY_FIELDS = [
    "company_name",
    "declared_values",
    "direction_statement",
    "job_summary",
    "job_title",
    "profile_version",
]
EXPECTED_ALIGNMENT_KEYS = {
    "state",
    "profile_version",
    "direction_statement",
    "declared_values",
    "matched_declared_values",
    "basis",
    "score_effect",
    "human_review_required",
}
EXPECTED_FACTOR_LABELS = {
    "skills": "요구 기술 일치",
    "experience": "경력 조건",
    "role": "희망 직무 연관",
}
EXPECTED_EXCLUDED_SCORE_FIELDS = [
    "name",
    "phone",
    "email",
    "birthdate",
    "address",
    "school",
    "certificates",
    "self_intro",
]


def explanation_provider_config() -> dict[str, str]:
    """Bind cached explanations to the configured adapter without claiming an invocation."""
    client_region = BEDROCK_REGION if LLM_PROVIDER == "bedrock" else ""
    model_ref = BEDROCK_MODEL_ID if LLM_PROVIDER == "bedrock" else ""
    canonical = json.dumps(
        {
            "client_region": client_region,
            "contract_version": EXPLANATION_CONTRACT_VERSION,
            "model_ref": model_ref,
            "provider": LLM_PROVIDER,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "provider": LLM_PROVIDER,
        "contract_version": EXPLANATION_CONTRACT_VERSION,
        "client_region": client_region or "NOT_APPLICABLE",
        "model_ref_hash": (
            hashlib.sha256(model_ref.encode("utf-8")).hexdigest()
            if model_ref
            else "NOT_APPLICABLE"
        ),
        "provider_config_fingerprint": hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest(),
    }


def explanation_attempt_metadata(
    status: str, *, item_count: int, scope: Literal["CURRENT_REQUEST", "CACHED_ORIGIN_REQUEST"]
) -> dict[str, object]:
    if item_count == 0:
        gateway_receipt_state = "NOT_NEEDED_EMPTY_SET"
        prepared_field_set_state = "NOT_PREPARED_EMPTY_SUBJECT_SET"
        candidate_fields_prepared: list[str] = []
        classified_pii_fields: list[str] = []
        company_fields_prepared: list[str] = []
    elif scope == "CACHED_ORIGIN_REQUEST" and status == "AVAILABLE":
        gateway_receipt_state = "CACHE_ENTRY_ACCEPTED_ORIGIN_NOT_VERIFIED"
        prepared_field_set_state = "CACHE_ORIGIN_FIELD_SET_NOT_VERIFIED"
        candidate_fields_prepared = []
        classified_pii_fields = []
        company_fields_prepared = []
    elif status == "AVAILABLE":
        gateway_receipt_state = "VALIDATED_RESPONSE"
        prepared_field_set_state = "CURRENT_REQUEST_PREPARED_BY_API"
        candidate_fields_prepared = list(EXPECTED_PROMPT_FIELDS)
        classified_pii_fields = list(EXPECTED_PII_FIELDS)
        company_fields_prepared = list(EXPECTED_COMPANY_FIELDS)
    else:
        gateway_receipt_state = "NOT_CONFIRMED"
        prepared_field_set_state = "CURRENT_REQUEST_PREPARED_BY_API"
        candidate_fields_prepared = list(EXPECTED_PROMPT_FIELDS)
        classified_pii_fields = list(EXPECTED_PII_FIELDS)
        company_fields_prepared = list(EXPECTED_COMPANY_FIELDS)
    return {
        "scope": scope,
        "prepared_field_set_state": prepared_field_set_state,
        "candidate_fields_prepared": candidate_fields_prepared,
        "classified_pii_fields": classified_pii_fields,
        "company_fields_prepared": company_fields_prepared,
        "gateway_receipt_state": gateway_receipt_state,
        "external_provider_receipt_state": "NOT_ASSERTED",
        "score_effect": "NONE",
        **explanation_provider_config(),
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    MemberBase.metadata.create_all(bind=member_engine)
    CompanyBase.metadata.create_all(bind=company_engine)
    ensure_runtime_schema()
    if os.getenv("AUTO_SEED", "true").lower() == "true":
        with SessionLocal() as db:
            seed_demo(db)
    yield


app = FastAPI(
    title="J-Career AS-IS recruiting API",
    version="0.1.0",
    description=(
        "Runnable synthetic recruiting service derived from the AS-IS architecture. "
        "It is a lab system, not a live service or certification result."
    ),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=2, max_length=100)

    @field_validator("email")
    @classmethod
    def synthetic_email_only(cls, value: str) -> str:
        normalised = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@(jcareer\.test|example\.invalid)", normalised):
            raise ValueError("합성 전용 .test 또는 .invalid 이메일만 사용할 수 있습니다")
        return normalised

    @field_validator("display_name")
    @classmethod
    def normalise_display_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("표시 이름은 공백을 제외하고 2자 이상이어야 합니다")
        return cleaned


class RecruiterSignupRequest(SignupRequest):
    company_name: str = Field(min_length=2, max_length=120)
    company_address: str = Field(min_length=2, max_length=240)

    @field_validator("company_name", "company_address")
    @classmethod
    def normalise_company_identity(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("기업 이름과 주소는 공백을 제외하고 2자 이상이어야 합니다")
        return cleaned


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def synthetic_email_only(cls, value: str) -> str:
        return SignupRequest.synthetic_email_only(value)


class ConsentRequest(BaseModel):
    action: Literal["grant", "revoke"] = "grant"
    consent_type: Literal["privacy_core", "marketing"] = "privacy_core"
    policy_version: str = Field(default="2026-05", min_length=1, max_length=40)

    @field_validator("policy_version")
    @classmethod
    def normalise_policy_version(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("동의문 버전은 비어 있을 수 없습니다")
        return cleaned


def normalise_skill_values(values: list[str], label: str) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        if len(cleaned) > 80:
            raise ValueError(f"{label}은 각 항목이 80자 이하여야 합니다")
        comparison_key = re.sub(r"[^0-9a-zA-Z가-힣+#.]", "", cleaned).lower()
        if not comparison_key:
            raise ValueError(f"{label}에는 비교 가능한 문자가 필요합니다")
        if comparison_key in seen:
            continue
        seen.add(comparison_key)
        unique.append(cleaned)
    if not unique:
        raise ValueError(f"{label}은 하나 이상 필요합니다")
    return unique


class ResumeRequest(BaseModel):
    phone: str = Field(max_length=40)
    birth_date: date | None = None
    address_region: str = Field(max_length=120)
    education: str = Field(max_length=180)
    desired_role: str = Field(min_length=1, max_length=120)
    years_experience: int = Field(ge=0, le=60)
    skills: list[str] = Field(min_length=1, max_length=30)
    certificates: list[str] = Field(default_factory=list, max_length=30)
    self_intro: str = Field(default="", max_length=5000)

    @field_validator("phone")
    @classmethod
    def synthetic_phone_only(cls, value: str) -> str:
        if not re.fullmatch(r"010-0000-\d{4}", value.strip()):
            raise ValueError("합성 전용 전화번호 010-0000-XXXX 형식만 사용할 수 있습니다")
        return value.strip()

    @field_validator("address_region", "education", "desired_role")
    @classmethod
    def normalise_resume_text(cls, value: str, info) -> str:
        cleaned = value.strip()
        minimums = {"address_region": 2, "education": 2, "desired_role": 1}
        if len(cleaned) < minimums[info.field_name]:
            raise ValueError("이력서 텍스트는 공백을 제외한 최소 길이를 충족해야 합니다")
        return cleaned

    @field_validator("skills")
    @classmethod
    def normalise_resume_skills(cls, values: list[str]) -> list[str]:
        return normalise_skill_values(values, "보유 기술")

    @field_validator("certificates")
    @classmethod
    def normalise_certificates(cls, values: list[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = value.strip()
            if not cleaned:
                continue
            if len(cleaned) > 180:
                raise ValueError("자격증은 각 항목이 180자 이하여야 합니다")
            key = cleaned.casefold()
            if key not in seen:
                seen.add(key)
                unique.append(cleaned)
        return unique

    @field_validator("self_intro")
    @classmethod
    def normalise_self_intro(cls, value: str) -> str:
        return value.strip()


class JobRequest(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    summary: str = Field(min_length=10, max_length=5000)
    location: str = Field(min_length=2, max_length=120)
    employment_type: str = Field(default="정규직", max_length=40)
    required_skills: list[str] = Field(min_length=1, max_length=30)
    min_experience: int = Field(default=0, ge=0, le=50)
    status: Literal["open", "closed"] = "open"

    @field_validator("title", "summary", "location", "employment_type")
    @classmethod
    def normalise_job_text(cls, value: str, info) -> str:
        cleaned = value.strip()
        minimums = {"title": 2, "summary": 10, "location": 2, "employment_type": 1}
        if len(cleaned) < minimums[info.field_name]:
            raise ValueError("공고 텍스트는 공백을 제외한 최소 길이를 충족해야 합니다")
        return cleaned

    @field_validator("required_skills")
    @classmethod
    def normalise_required_skills(cls, values: list[str]) -> list[str]:
        return normalise_skill_values(values, "요구 기술")


class CompanyProfileRequest(BaseModel):
    direction_statement: str = Field(min_length=20, max_length=2000)
    declared_values: list[str] = Field(min_length=1, max_length=10)

    @field_validator("direction_statement")
    @classmethod
    def normalise_direction_statement(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 20:
            raise ValueError("기업 방향 설명은 공백을 제외하고 20자 이상이어야 합니다")
        return cleaned

    @field_validator("declared_values")
    @classmethod
    def normalise_declared_values(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        unique = list(dict.fromkeys(cleaned))
        if not unique or any(len(value) > 80 for value in unique):
            raise ValueError("핵심가치는 1~10개의 80자 이하 값이어야 합니다")
        return unique


class OpenDartRefreshRequest(BaseModel):
    corp_code: str = Field(min_length=8, max_length=8, pattern=r"^[0-9]{8}$")

    @field_validator("corp_code")
    @classmethod
    def normalise_corp_code(cls, value: str) -> str:
        return value.strip()


class ApplicationStatusRequest(BaseModel):
    status: Literal["applied", "reviewing", "interview", "offered", "rejected"]


def pseudonymous_ref(user_id: str) -> str:
    return f"candidate:{uuid.uuid5(uuid.NAMESPACE_URL, 'jcareer/' + user_id).hex[:12]}"


def pseudonymous_user_ref(user_id: str) -> str:
    return f"user:{uuid.uuid5(uuid.NAMESPACE_URL, 'jcareer/user/' + user_id).hex[:12]}"


def audit(
    db: Session,
    *,
    event_type: str,
    actor: User | None,
    target_type: str,
    target_ref: str,
    action: str,
    result: str = "success",
    purpose: str = "service_operation",
    detail: dict[str, object] | None = None,
) -> None:
    db.add(
        AuditEvent(
            event_type=event_type,
            actor_user_id=actor.id if actor else None,
            actor_role=actor.role if actor else "system",
            company_id=actor.company_id if actor else None,
            target_type=target_type,
            target_ref=target_ref,
            purpose=purpose,
            action=action,
            result=result,
            detail=detail or {},
        )
    )


def require_core_consent(db: Session, user: User) -> None:
    latest_action = db.scalar(
        select(ConsentEvent.action)
        .where(
            ConsentEvent.user_id == user.id,
            ConsentEvent.consent_type == "privacy_core",
        )
        .order_by(ConsentEvent.occurred_at.desc(), ConsentEvent.id.desc())
        .limit(1)
    )
    if latest_action != "grant":
        raise HTTPException(
            status_code=409,
            detail="개인정보 수집·이용 동의 후 이 기능을 사용할 수 있습니다",
        )


def require_failure_injection_enabled(mode: str | None) -> None:
    if mode and not FAILURE_INJECTION_ENABLED:
        raise HTTPException(status_code=404, detail="장애 주입 모드를 사용할 수 없습니다")


def user_payload(user: User, company: Company | None = None) -> dict[str, object]:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "company_id": user.company_id,
        "company_name": company.name if company else None,
    }


def opendart_profile_payload(
    company: Company, *, include_linkage: bool = False
) -> dict[str, object]:
    snapshot = public_snapshot(company.opendart_snapshot)
    state = company.opendart_sync_state
    if state.startswith("AVAILABLE") and snapshot is None:
        state = "UNAVAILABLE_INVALID_SNAPSHOT"
    payload: dict[str, object] = {
        "state": state,
        "snapshot_version": company.opendart_snapshot_version,
        "synced_at": (
            company.opendart_synced_at.isoformat()
            if company.opendart_synced_at
            else None
        ),
        "snapshot": snapshot,
        "score_effect": "NONE",
    }
    if include_linkage:
        payload["corp_code"] = company.opendart_corp_code
        payload["last_attempt_at"] = (
            company.opendart_last_attempt_at.isoformat()
            if company.opendart_last_attempt_at
            else None
        )
        payload["pending_request_id"] = company.opendart_pending_request_id
        payload["pending_requested_at"] = (
            company.opendart_pending_requested_at.isoformat()
            if company.opendart_pending_requested_at
            else None
        )
    return payload


def company_profile_payload(
    company: Company, *, include_opendart_linkage: bool = False
) -> dict[str, object]:
    return {
        "company_id": company.id,
        "company_name": company.name,
        "company_address": company.address,
        "direction_statement": company.direction_statement,
        "declared_values": company.declared_values,
        "profile_version": company.profile_version,
        "source": (
            "unset"
            if company.profile_version == "company-profile-unset"
            else (
                "synthetic_recruiter_declared"
                if company.profile_version.startswith("company-profile-seed-")
                else "recruiter_declared"
            )
        ),
        "opendart": opendart_profile_payload(
            company, include_linkage=include_opendart_linkage
        ),
    }


def job_payload(job: Job) -> dict[str, object]:
    return {
        "id": job.id,
        "company_id": job.company_id,
        "company_name": job.company.name if job.company else "",
        "title": job.title,
        "summary": job.summary,
        "location": job.location,
        "employment_type": job.employment_type,
        "required_skills": job.required_skills,
        "min_experience": job.min_experience,
        "status": job.status,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "company_profile": company_profile_payload(job.company) if job.company else None,
    }


def candidate_job_cache_contract(jobs: list[Job]) -> str:
    contract = [
        {
            "id": job.id,
            "company_id": job.company_id,
            "company_profile_version": job.company.profile_version,
            "title": job.title,
            "summary": job.summary,
            "location": job.location,
            "employment_type": job.employment_type,
            "required_skills": job.required_skills,
            "min_experience": job.min_experience,
            "status": job.status,
            "updated_at": job.updated_at.isoformat(),
        }
        for job in sorted(jobs, key=lambda item: item.id)
    ]
    canonical = json.dumps(
        contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def resume_payload(resume: Resume, user: User | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": resume.id,
        "user_id": resume.user_id,
        "phone": resume.phone,
        "birth_date": resume.birth_date,
        "address_region": resume.address_region,
        "education": resume.education,
        "desired_role": resume.desired_role,
        "years_experience": resume.years_experience,
        "skills": resume.skills,
        "certificates": resume.certificates,
        "self_intro": resume.self_intro,
        "updated_at": resume.updated_at,
    }
    if user:
        payload.update({"display_name": user.display_name, "email": user.email})
    return payload


def redis_client() -> async_redis.Redis:
    return async_redis.Redis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=0.3,
        socket_timeout=0.3,
        retry_on_timeout=False,
    )


async def get_cached(key: str) -> dict[str, object] | None:
    client = redis_client()
    try:
        value = await asyncio.wait_for(client.get(key), timeout=0.75)
        if not value:
            return None
        decoded = json.loads(value)
        if (
            not isinstance(decoded, dict)
            or decoded.get("recommendation_status") != "AVAILABLE"
            or not isinstance(decoded.get("items"), list)
            or any(not isinstance(item, dict) for item in decoded.get("items", []))
            or any(
                not isinstance(decoded.get(field), str) or not decoded[field]
                for field in ("explanation_status", "matcher_version", "correlation_id")
            )
            or decoded.get("provider_config_fingerprint")
            != explanation_provider_config()["provider_config_fingerprint"]
            or decoded.get("explanation_freshness")
            != "CURRENT_REQUEST_GATEWAY_RESULT"
            or not isinstance(decoded.get("explanation_attempt"), dict)
        ):
            return None
        return decoded
    except (TimeoutError, redis.RedisError, json.JSONDecodeError):
        return None
    finally:
        await client.aclose()


async def set_cached(key: str, value: dict[str, object]) -> None:
    client = redis_client()
    try:
        await asyncio.wait_for(
            client.setex(key, 86400, json.dumps(value, ensure_ascii=False, default=str)),
            timeout=0.75,
        )
    except (TimeoutError, redis.RedisError):
        pass
    finally:
        await client.aclose()


async def run_matcher(path: str, payload: dict[str, object]) -> dict[str, object]:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(f"{AGENT_BASE_URL}{path}", json=payload)
            response.raise_for_status()
            body = response.json()
            _validate_matcher_response(body, path, payload)
            return body
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="추천 점수 계산 서비스를 사용할 수 없습니다") from exc


def _finite_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("matcher numeric field")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("matcher non-finite field")
    return number


def _normalise_alignment_text(value: object) -> str:
    return "".join(character.lower() for character in str(value) if character.isalnum())


def _validate_matcher_response(
    body: object, path: str, request_payload: dict[str, object]
) -> None:
    if not isinstance(body, dict):
        raise ValueError("matcher body")
    items = body.get("items")
    envelope_version = body.get("matcher_version")
    if (
        body.get("status") != "AVAILABLE"
        or not isinstance(items, list)
        or not isinstance(envelope_version, str)
        or not envelope_version
    ):
        raise ValueError("matcher envelope")

    request_key = "jobs" if path.endswith("/jobs") else "candidates"
    requested = request_payload.get(request_key)
    if not isinstance(requested, list):
        raise ValueError("matcher request references")
    expected_refs = {
        str(item["id"])
        for item in requested
        if isinstance(item, dict) and "id" in item
    }
    requested_limit = request_payload.get("limit", 20)
    if not isinstance(requested_limit, int) or requested_limit < 1:
        raise ValueError("matcher request limit")
    if len(items) != min(len(expected_refs), requested_limit):
        raise ValueError("matcher item count")
    seen: set[str] = set()
    ranking: list[tuple[float, str]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("matcher item")
        subject_ref = str(item.get("subject_ref", ""))
        if not subject_ref or subject_ref not in expected_refs or subject_ref in seen:
            raise ValueError("matcher subject reference")
        seen.add(subject_ref)
        if item.get("matcher_version") != envelope_version:
            raise ValueError("matcher version mismatch")

        score = _finite_number(item.get("score"))
        if not 0 <= score <= 100:
            raise ValueError("matcher score range")
        ranking.append((score, subject_ref))
        breakdown = item.get("score_breakdown")
        if not isinstance(breakdown, dict):
            raise ValueError("matcher score breakdown")
        total = _finite_number(breakdown.get("total_points"))
        maximum = _finite_number(breakdown.get("max_points"))
        factors = breakdown.get("factors")
        if not math.isclose(total, score, abs_tol=1e-9) or not math.isclose(
            maximum, 100.0, abs_tol=1e-9
        ):
            raise ValueError("matcher total mismatch")
        if not isinstance(factors, list) or len(factors) != 3:
            raise ValueError("matcher factors")
        if (
            breakdown.get("formula") != "기술 70 + 경력 20 + 직무 연관 10"
            or breakdown.get("excluded_input_fields")
            != EXPECTED_EXCLUDED_SCORE_FIELDS
        ):
            raise ValueError("matcher display metadata")

        factor_ids: set[str] = set()
        factor_order: list[str] = []
        factor_points: dict[str, float] = {}
        factor_maximums: dict[str, float] = {}
        raw_sum = 0.0
        maximum_sum = 0.0
        for factor in factors:
            if not isinstance(factor, dict):
                raise ValueError("matcher factor")
            factor_id = str(factor.get("factor_id", ""))
            if factor_id not in {"skills", "experience", "role"} or factor_id in factor_ids:
                raise ValueError("matcher factor id")
            factor_ids.add(factor_id)
            factor_order.append(factor_id)
            label = factor.get("label")
            calculation = factor.get("calculation")
            evidence = factor.get("evidence")
            if (
                label != EXPECTED_FACTOR_LABELS[factor_id]
                or not isinstance(calculation, str)
                or not calculation.strip()
                or len(calculation) > 500
                or not isinstance(evidence, list)
                or len(evidence) > 30
                or any(
                    not isinstance(value, str) or not value.strip() or len(value) > 200
                    for value in evidence
                )
                or not isinstance(factor.get("details"), dict)
            ):
                raise ValueError("matcher factor display contract")
            raw_points = _finite_number(factor.get("raw_points"))
            display_points = _finite_number(factor.get("display_points"))
            max_points = _finite_number(factor.get("max_points"))
            if not 0 <= raw_points <= max_points:
                raise ValueError("matcher factor range")
            if not math.isclose(display_points, round(raw_points, 1), abs_tol=1e-9):
                raise ValueError("matcher factor display rounding")
            raw_sum += raw_points
            maximum_sum += max_points
            factor_points[factor_id] = raw_points
            factor_maximums[factor_id] = max_points

        if factor_ids != {"skills", "experience", "role"}:
            raise ValueError("matcher factor set")
        if factor_order != ["skills", "experience", "role"]:
            raise ValueError("matcher factor order")
        if factor_maximums != {"skills": 70.0, "experience": 20.0, "role": 10.0}:
            raise ValueError("matcher factor maximum contract")
        if not math.isclose(maximum_sum, maximum, abs_tol=1e-9):
            raise ValueError("matcher maximum sum")
        if not math.isclose(round(raw_sum, 1), score, abs_tol=1e-9):
            raise ValueError("matcher raw contribution sum")
        if breakdown.get("schema_version") != "score-breakdown-v1":
            raise ValueError("matcher score breakdown version")
        if breakdown.get("formula_version") != "deterministic-70-20-10-v1":
            raise ValueError("matcher formula version")
        if breakdown.get("policy_source") != "platform_default":
            raise ValueError("matcher policy source")
        configured_priority = breakdown.get("configured_priority_factor_id")
        if configured_priority not in factor_ids or factor_maximums[configured_priority] != max(
            factor_maximums.values()
        ):
            raise ValueError("matcher configured priority")
        largest_ids = breakdown.get("largest_contribution_factor_ids")
        expected_largest_ids = {
            factor_id
            for factor_id, points in factor_points.items()
            if math.isclose(points, max(factor_points.values()), abs_tol=1e-9)
        }
        if not isinstance(largest_ids, list) or set(largest_ids) != expected_largest_ids:
            raise ValueError("matcher largest contribution")

        feature_ids = item.get("matched_feature_ids")
        feature_labels = item.get("matched_feature_labels")
        if (
            not isinstance(feature_ids, list)
            or not isinstance(feature_labels, list)
            or len(feature_ids) != len(feature_labels)
            or len(feature_ids) > 30
        ):
            raise ValueError("matcher matched feature envelope")
        if any(
            not isinstance(feature_id, str)
            or not feature_id.strip()
            or len(feature_id) > 160
            or (
                feature_id not in {"experience.minimum_met", "role.title_overlap"}
                and not (
                    feature_id.startswith("skill.")
                    and len(feature_id) > len("skill.")
                )
            )
            for feature_id in feature_ids
        ):
            raise ValueError("matcher matched feature id")
        if len(set(feature_ids)) != len(feature_ids):
            raise ValueError("matcher duplicate feature id")
        if any(
            not isinstance(label, str) or not label.strip() or len(label) > 200
            for label in feature_labels
        ):
            raise ValueError("matcher matched feature label")

    if ranking != sorted(ranking, key=lambda ranked: (-ranked[0], ranked[1])):
        raise ValueError("matcher ranking order")


def _validate_explanation_response(
    body: object,
    expected_items: list[dict[str, object]],
    correlation_id: str,
) -> dict[str, dict[str, object]]:
    if not isinstance(body, dict) or body.get("status") != "AVAILABLE":
        raise ValueError("explanation envelope")
    if body.get("correlation_id") != correlation_id:
        raise ValueError("explanation correlation")
    response_items = body.get("items")
    expected_refs = [
        item.get("subject_ref") for item in expected_items if isinstance(item, dict)
    ]
    if (
        not isinstance(response_items, list)
        or any(not isinstance(ref, str) or not ref for ref in expected_refs)
        or len(set(expected_refs)) != len(expected_refs)
        or len(response_items) != len(expected_refs)
    ):
        raise ValueError("explanation references")
    expected_by_ref = {
        str(item["subject_ref"]): item
        for item in expected_items
        if isinstance(item, dict) and isinstance(item.get("subject_ref"), str)
    }

    expected_provider = explanation_provider_config()
    mapped: dict[str, dict[str, object]] = {}
    for item in response_items:
        if not isinstance(item, dict):
            raise ValueError("explanation item")
        subject_ref = item.get("subject_ref")
        if (
            not isinstance(subject_ref, str)
            or subject_ref not in expected_refs
            or subject_ref in mapped
            or item.get("status") != "AVAILABLE"
            or not isinstance(item.get("text"), str)
            or not item["text"].strip()
            or item.get("contract_version") != EXPLANATION_CONTRACT_VERSION
            or item.get("provider") != expected_provider["provider"]
            or not isinstance(item.get("generation_mode"), str)
            or not item["generation_mode"].strip()
            or item.get("output_validation_state") != "NOT_IMPLEMENTED_ASIS"
            or not isinstance(item.get("company_alignment"), dict)
        ):
            raise ValueError("explanation item contract")
        if (
            item.get("prompt_fields_prepared") != EXPECTED_PROMPT_FIELDS
            or item.get("pii_fields_prepared") != EXPECTED_PII_FIELDS
            or item.get("company_fields_prepared") != EXPECTED_COMPANY_FIELDS
            or item.get("contract_version") != expected_provider["contract_version"]
            or item.get("client_region") != expected_provider["client_region"]
            or item.get("model_ref_hash") != expected_provider["model_ref_hash"]
            or item.get("provider_config_fingerprint")
            != expected_provider["provider_config_fingerprint"]
            or not isinstance(item.get("prompt_hash"), str)
            or re.fullmatch(r"[0-9a-f]{64}", item["prompt_hash"]) is None
        ):
            raise ValueError("explanation metadata contract")
        alignment = item["company_alignment"]
        declared_values = alignment.get("declared_values")
        matched_values = alignment.get("matched_declared_values")
        state = alignment.get("state")
        expected_company = expected_by_ref[subject_ref].get("company_context")
        expected_candidate = expected_by_ref[subject_ref].get("candidate_context")
        expected_declared = (
            expected_company.get("declared_values")
            if isinstance(expected_company, dict)
            else None
        )
        expected_direction = (
            str(expected_company.get("direction_statement", "")).strip()
            if isinstance(expected_company, dict)
            else ""
        )
        expected_intro = (
            str(expected_candidate.get("self_intro", "")).strip()
            if isinstance(expected_candidate, dict)
            else ""
        )
        expected_matches = (
            [
                value
                for value in expected_declared
                if isinstance(value, str)
                and _normalise_alignment_text(value)
                and _normalise_alignment_text(value)
                in _normalise_alignment_text(expected_intro)
            ]
            if isinstance(expected_declared, list) and expected_direction
            else []
        )
        expected_state = (
            "COMPANY_PROFILE_UNAVAILABLE"
            if not expected_direction or not expected_declared
            else "DIRECT_DECLARED_VALUE_EVIDENCE_FOUND"
            if expected_matches
            else "NO_DIRECT_DECLARED_VALUE_EVIDENCE"
        )
        if (
            set(alignment) != EXPECTED_ALIGNMENT_KEYS
            or state not in {
                "COMPANY_PROFILE_UNAVAILABLE",
                "NO_DIRECT_DECLARED_VALUE_EVIDENCE",
                "DIRECT_DECLARED_VALUE_EVIDENCE_FOUND",
            }
            or not isinstance(alignment.get("profile_version"), str)
            or not isinstance(alignment.get("direction_statement"), str)
            or not isinstance(declared_values, list)
            or any(not isinstance(value, str) for value in declared_values)
            or not isinstance(matched_values, list)
            or any(not isinstance(value, str) for value in matched_values)
            or not set(matched_values).issubset(set(declared_values))
            or alignment.get("basis")
            != "company-declared-profile-and-self-introduction"
            or alignment.get("score_effect") != "NONE"
            or alignment.get("human_review_required") is not True
            or (state == "DIRECT_DECLARED_VALUE_EVIDENCE_FOUND" and not matched_values)
            or (state != "DIRECT_DECLARED_VALUE_EVIDENCE_FOUND" and bool(matched_values))
            or not isinstance(expected_company, dict)
            or not isinstance(expected_candidate, dict)
            or alignment.get("profile_version")
            != expected_company.get("profile_version")
            or alignment.get("direction_statement")
            != expected_company.get("direction_statement")
            or declared_values != expected_company.get("declared_values")
            or matched_values != expected_matches
            or state != expected_state
        ):
            raise ValueError("company alignment contract")
        mapped[subject_ref] = item
    if set(mapped) != set(expected_refs):
        raise ValueError("explanation reference set")
    return mapped


async def run_explanations(
    items: list[dict[str, object]],
    correlation_id: str,
    mode: str | None = None,
) -> tuple[str, dict[str, dict[str, object]]]:
    if not items:
        return "AVAILABLE", {}
    try:
        async with httpx.AsyncClient(timeout=LLM_GATEWAY_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{LLM_GATEWAY_BASE_URL}/internal/explanations",
                json={"items": items, "correlation_id": correlation_id, "mode": mode},
            )
            response.raise_for_status()
            body = response.json()
            return "AVAILABLE", _validate_explanation_response(
                body, items, correlation_id
            )
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return "UNAVAILABLE_PROVIDER", {}


def recruiter_company(db: Session, user: User) -> Company:
    if not user.company_id:
        raise HTTPException(status_code=409, detail="기업 정보가 연결되지 않은 계정입니다")
    company = db.get(Company, user.company_id)
    if not company:
        raise HTTPException(status_code=503, detail="기업 계정 연결 정보를 확인할 수 없습니다")
    return company


def recruiter_job(
    db: Session, job_id: str, user: User, *, denied_action: str = "read"
) -> Job:
    recruiter_company(db, user)
    job = db.scalar(select(Job).options(joinedload(Job.company)).where(Job.id == job_id))
    if not job:
        raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다")
    if job.company_id != user.company_id:
        audit(
            db,
            event_type="authorization_denied",
            actor=user,
            target_type="job",
            target_ref=job.id,
            action=denied_action,
            result="denied",
            purpose="recruiting",
        )
        db.commit()
        raise HTTPException(status_code=403, detail="다른 기업의 공고에는 접근할 수 없습니다")
    return job


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, object]:
    with member_engine.connect() as member_connection:
        member_connection.execute(text("SELECT 1"))
    with company_engine.connect() as company_connection:
        company_connection.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "service": "api",
        "databases": {"member": "ok", "company": "ok"},
        "dataset_profile": os.getenv("DATASET_PROFILE", "demo_not_for_measurement"),
    }


@app.get("/api/v1/runtime")
def runtime_info() -> dict[str, object]:
    return {
        "service": "J-Career synthetic AS-IS runtime",
        "live_client_service": False,
        "dataset_profile": os.getenv("DATASET_PROFILE", "demo_not_for_measurement"),
        "explanation_provider": LLM_PROVIDER,
        "score_contract_version": SCORE_RESPONSE_CONTRACT_VERSION,
        "database_boundaries": {
            "member": ["identity", "consent", "resume", "application", "audit"],
            "company": ["company", "company_profile", "job"],
            "cross_database_foreign_keys": False,
            "cross_database_atomic_commit": False,
        },
        "trace_enabled": False,
        "failure_injection_enabled": FAILURE_INJECTION_ENABLED,
    }


@app.post("/api/v1/auth/signup", status_code=201)
def signup(request: SignupRequest, db: Session = Depends(get_db)) -> dict[str, object]:
    user = User(
        email=request.email.lower(),
        password_hash=hash_password(request.password),
        display_name=request.display_name.strip(),
        role="candidate",
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="이미 사용 중인 이메일입니다") from exc
    audit(
        db,
        event_type="signup",
        actor=user,
        target_type="user",
        target_ref=pseudonymous_user_ref(user.id),
        action="create_account",
    )
    db.commit()
    db.refresh(user)
    return {"access_token": issue_token(user), "token_type": "bearer", "user": user_payload(user)}


@app.post("/api/v1/auth/signup/recruiter", status_code=201)
def recruiter_signup(
    request: RecruiterSignupRequest, db: Session = Depends(get_db)
) -> dict[str, object]:
    company = Company(name=request.company_name.strip(), address=request.company_address.strip())
    db.add(company)
    try:
        db.flush()
        user = User(
            email=request.email.lower(),
            password_hash=hash_password(request.password),
            display_name=request.display_name.strip(),
            role="recruiter",
            company_id=company.id,
        )
        db.add(user)
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="이미 등록된 이메일 또는 기업명입니다") from exc
    audit(
        db,
        event_type="recruiter_signup",
        actor=user,
        target_type="company",
        target_ref=company.id,
        action="create_company_account",
    )
    db.commit()
    db.refresh(user)
    return {
        "access_token": issue_token(user),
        "token_type": "bearer",
        "user": user_payload(user, company),
    }


@app.post("/api/v1/auth/login")
def login(request: LoginRequest, db: Session = Depends(get_db)) -> dict[str, object]:
    user = db.scalar(select(User).where(User.email == request.email.lower()))
    if not user or not user.active or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호를 확인해 주세요")
    company = db.get(Company, user.company_id) if user.company_id else None
    if user.role == "recruiter" and not company:
        raise HTTPException(status_code=503, detail="기업 계정 연결 정보를 확인할 수 없습니다")
    audit(
        db,
        event_type="login",
        actor=user,
        target_type="session",
        target_ref=pseudonymous_user_ref(user.id),
        action="create_session",
    )
    db.commit()
    return {
        "access_token": issue_token(user),
        "token_type": "bearer",
        "user": user_payload(user, company),
    }


@app.get("/api/v1/auth/me")
def me(
    db: Session = Depends(get_db), user: User = Depends(current_user)
) -> dict[str, object]:
    company = db.get(Company, user.company_id) if user.company_id else None
    if user.role == "recruiter" and not company:
        raise HTTPException(status_code=503, detail="기업 계정 연결 정보를 확인할 수 없습니다")
    return user_payload(user, company)


@app.post("/api/v1/candidates/me/consents", status_code=201)
def record_consent(
    request: ConsentRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("candidate")),
) -> dict[str, object]:
    if request.consent_type == "privacy_core":
        collected = [
            "name",
            "email",
            "phone",
            "birth_date",
            "address",
            "education",
            "career",
            "certificates",
        ]
        purposes = ["member_management", "job_service", "ai_recommendation"]
    else:
        collected = ["email"]
        purposes = ["marketing"]
    event = ConsentEvent(
        user_id=user.id,
        consent_type=request.consent_type,
        action=request.action,
        policy_version=request.policy_version,
        collected_items=collected,
        purposes=purposes,
    )
    db.add(event)
    audit(
        db,
        event_type=f"consent_{request.action}",
        actor=user,
        target_type="consent",
        target_ref=request.consent_type,
        action=request.action,
        purpose="consent_management",
    )
    db.commit()
    return {"id": event.id, "consent_type": event.consent_type, "action": event.action}


@app.get("/api/v1/candidates/me/consents")
def list_consents(
    db: Session = Depends(get_db), user: User = Depends(require_role("candidate"))
) -> list[dict[str, object]]:
    events = db.scalars(
        select(ConsentEvent)
        .where(ConsentEvent.user_id == user.id)
        .order_by(ConsentEvent.occurred_at.desc(), ConsentEvent.id.desc())
    ).all()
    return [
        {
            "id": event.id,
            "consent_type": event.consent_type,
            "action": event.action,
            "policy_version": event.policy_version,
            "collected_items": event.collected_items,
            "purposes": event.purposes,
            "occurred_at": event.occurred_at,
        }
        for event in events
    ]


@app.delete("/api/v1/candidates/me/consents/{consent_type}", status_code=201)
def revoke_consent(
    consent_type: Literal["privacy_core", "marketing"],
    db: Session = Depends(get_db),
    user: User = Depends(require_role("candidate")),
) -> dict[str, str]:
    request = ConsentRequest(action="revoke", consent_type=consent_type)
    result = record_consent(request, db, user)
    return {"id": str(result["id"]), "action": "revoke"}


@app.get("/api/v1/candidates/me/resume")
def get_resume(
    db: Session = Depends(get_db), user: User = Depends(require_role("candidate"))
) -> dict[str, object]:
    resume = db.scalar(select(Resume).where(Resume.user_id == user.id))
    if not resume:
        raise HTTPException(status_code=404, detail="저장된 이력서가 없습니다")
    return resume_payload(resume, user)


@app.post("/api/v1/candidates/me/resume")
def save_resume(
    request: ResumeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("candidate")),
) -> dict[str, object]:
    require_core_consent(db, user)
    resume = db.scalar(select(Resume).where(Resume.user_id == user.id))
    if not resume:
        resume = Resume(user_id=user.id)
        db.add(resume)
    for field, value in request.model_dump().items():
        setattr(resume, field, value)
    audit(
        db,
        event_type="resume_saved",
        actor=user,
        target_type="resume",
        target_ref=pseudonymous_ref(user.id),
        action="upsert",
        purpose="job_service",
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        resume = db.scalar(select(Resume).where(Resume.user_id == user.id))
        if not resume:
            raise HTTPException(
                status_code=409,
                detail="이력서가 동시에 변경되었습니다. 다시 저장해 주세요",
            )
        for field, value in request.model_dump().items():
            setattr(resume, field, value)
        audit(
            db,
            event_type="resume_saved",
            actor=user,
            target_type="resume",
            target_ref=pseudonymous_ref(user.id),
            action="upsert_after_conflict",
            purpose="job_service",
        )
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="이력서가 동시에 변경되었습니다. 다시 저장해 주세요",
            ) from exc
    db.refresh(resume)
    return resume_payload(resume, user)


@app.get("/api/v1/jobs")
def list_jobs(
    q: str = Query(default="", max_length=100),
    location: str = Query(default="", max_length=100),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    statement = (
        select(Job).options(joinedload(Job.company)).where(Job.status == "open").order_by(Job.created_at.desc())
    )
    if q.strip():
        like = f"%{q.strip()}%"
        statement = statement.where(
            or_(
                Job.title.ilike(like),
                Job.summary.ilike(like),
                cast(Job.required_skills, String).ilike(like),
            )
        )
    if location.strip():
        statement = statement.where(Job.location.ilike(f"%{location.strip()}%"))
    return [job_payload(job) for job in db.scalars(statement).all()]


@app.get("/api/v1/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    job = db.scalar(select(Job).options(joinedload(Job.company)).where(Job.id == job_id))
    if not job:
        raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다")
    return job_payload(job)


@app.post("/api/v1/jobs/{job_id}/applications", status_code=201)
def apply_to_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("candidate")),
) -> dict[str, object]:
    job = db.get(Job, job_id)
    if not job or job.status != "open":
        raise HTTPException(status_code=404, detail="지원 가능한 공고가 아닙니다")
    require_core_consent(db, user)
    if not db.scalar(select(Resume).where(Resume.user_id == user.id)):
        raise HTTPException(status_code=409, detail="지원 전에 이력서를 작성해 주세요")
    existing = db.scalar(
        select(Application).where(
            Application.job_id == job_id, Application.candidate_id == user.id
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="이미 지원한 공고입니다")
    application = Application(job_id=job_id, candidate_id=user.id)
    db.add(application)
    audit(
        db,
        event_type="application_submitted",
        actor=user,
        target_type="job",
        target_ref=job_id,
        action="apply",
        purpose="job_service",
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="이미 지원한 공고입니다") from exc
    return {"id": application.id, "job_id": job_id, "status": application.status}


@app.get("/api/v1/candidates/me/applications")
def candidate_applications(
    db: Session = Depends(get_db), user: User = Depends(require_role("candidate"))
) -> list[dict[str, object]]:
    applications = db.scalars(
        select(Application)
        .where(Application.candidate_id == user.id)
        .order_by(Application.applied_at.desc())
    ).all()
    job_ids = [item.job_id for item in applications]
    jobs = (
        db.scalars(
            select(Job).options(joinedload(Job.company)).where(Job.id.in_(job_ids))
        ).all()
        if job_ids
        else []
    )
    job_map = {job.id: job for job in jobs}
    missing_job_ids = sorted(set(job_ids) - set(job_map))
    if missing_job_ids:
        raise HTTPException(
            status_code=503,
            detail="일부 지원 내역의 기업 DB 공고 참조를 확인할 수 없습니다",
        )
    return [
        {
            "id": item.id,
            "status": item.status,
            "applied_at": item.applied_at,
            "job": job_payload(job_map[item.job_id]),
        }
        for item in applications
        if item.job_id in job_map
    ]


@app.get("/api/v1/candidates/me/recommendations")
async def candidate_recommendations(
    explanation_mode: Literal[
        "success", "timeout", "rate_limit", "provider_error", "malformed", "overclaim"
    ]
    | None = Query(default=None),
    db: Session = Depends(get_db), user: User = Depends(require_role("candidate"))
) -> dict[str, object]:
    require_core_consent(db, user)
    require_failure_injection_enabled(explanation_mode)
    resume = db.scalar(select(Resume).where(Resume.user_id == user.id))
    if not resume:
        raise HTTPException(status_code=409, detail="추천을 받으려면 이력서를 작성해 주세요")

    jobs = db.scalars(
        select(Job).options(joinedload(Job.company)).where(Job.status == "open")
    ).all()
    job_contract = candidate_job_cache_contract(jobs)
    cache_key = (
        f"asis:{SCORE_RESPONSE_CONTRACT_VERSION}:candidate-recommendations:"
        f"{user.id}:{resume.updated_at.isoformat()}:"
        f"{job_contract}:"
        f"{explanation_provider_config()['provider_config_fingerprint']}:"
        f"{explanation_mode or 'success'}"
    )
    cached = await get_cached(cache_key)
    if cached:
        cached["cache"] = "hit"
        cached["explanation_freshness"] = "CACHE_HIT_PROVIDER_NOT_REVALIDATED"
        cached["explanation_attempt"] = explanation_attempt_metadata(
            str(cached["explanation_status"]),
            item_count=len(cached["items"]),
            scope="CACHED_ORIGIN_REQUEST",
        )
        return cached

    match_body = await run_matcher(
        "/internal/match/jobs",
        {
            "candidate": {
                "id": user.id,
                "desired_role": resume.desired_role,
                "skills": resume.skills,
                "years_experience": resume.years_experience,
            },
            "jobs": [
                {
                    "id": job.id,
                    "title": job.title,
                    "required_skills": job.required_skills,
                    "min_experience": job.min_experience,
                }
                for job in jobs
            ],
            "limit": 12,
        },
    )
    job_map = {job.id: job for job in jobs}
    explanation_items = [
        {
            "subject_ref": item["subject_ref"],
            "score": item["score"],
            "score_breakdown": item["score_breakdown"],
            "matched_feature_ids": item["matched_feature_ids"],
            "matched_feature_labels": item["matched_feature_labels"],
            "candidate_context": {
                "name": user.display_name,
                "phone": resume.phone,
                "email": user.email,
                "birthdate": str(resume.birth_date) if resume.birth_date else "",
                "address": resume.address_region,
                "school": resume.education,
                "certificates": resume.certificates,
                "self_intro": resume.self_intro,
            },
            "company_context": {
                "company_name": job_map[str(item["subject_ref"])].company.name,
                "direction_statement": job_map[str(item["subject_ref"])].company.direction_statement,
                "declared_values": job_map[str(item["subject_ref"])].company.declared_values,
                "profile_version": job_map[str(item["subject_ref"])].company.profile_version,
                "job_title": job_map[str(item["subject_ref"])].title,
                "job_summary": job_map[str(item["subject_ref"])].summary,
            },
        }
        for item in match_body["items"]
    ]
    correlation_id = str(uuid.uuid4())
    explanation_status, explanations = await run_explanations(
        explanation_items, correlation_id, explanation_mode
    )
    items: list[dict[str, object]] = []
    for match in match_body["items"]:
        job = job_map.get(str(match["subject_ref"]))
        if not job:
            continue
        explanation = explanations.get(job.id)
        items.append(
            {
                "job": job_payload(job),
                "score": match["score"],
                "score_breakdown": match["score_breakdown"],
                "matched_feature_ids": match["matched_feature_ids"],
                "matched_feature_labels": match["matched_feature_labels"],
                "matcher_version": match["matcher_version"],
                "explanation": explanation
                or {"status": explanation_status, "text": None},
            }
        )
    response = {
        "recommendation_status": "AVAILABLE",
        "explanation_status": explanation_status,
        "matcher_version": match_body["matcher_version"],
        "items": items,
        "cache": "miss",
        "correlation_id": correlation_id,
        "explanation_freshness": "CURRENT_REQUEST_GATEWAY_RESULT",
        "explanation_attempt": explanation_attempt_metadata(
            explanation_status,
            item_count=len(explanation_items),
            scope="CURRENT_REQUEST",
        ),
        "provider_config_fingerprint": explanation_provider_config()[
            "provider_config_fingerprint"
        ],
    }
    if explanation_status == "AVAILABLE":
        await set_cached(cache_key, response)
    return response


@app.delete("/api/v1/candidates/me", status_code=202)
def withdraw_candidate(
    db: Session = Depends(get_db), user: User = Depends(require_role("candidate"))
) -> dict[str, object]:
    reference = pseudonymous_ref(user.id)
    db.add(
        ConsentEvent(
            user_id=user.id,
            consent_type="privacy_core",
            action="revoke",
            policy_version="2026-05",
            collected_items=[],
            purposes=[],
        )
    )
    db.execute(delete(Application).where(Application.candidate_id == user.id))
    db.execute(delete(Resume).where(Resume.user_id == user.id))
    user.display_name = "탈퇴 사용자"
    user.email = f"withdrawn-{user.id}@example.invalid"
    user.password_hash = hash_password(str(uuid.uuid4()))
    user.active = False
    from .models import utcnow

    user.withdrawn_at = utcnow()
    audit(
        db,
        event_type="withdrawal",
        actor=user,
        target_type="user",
        target_ref=reference,
        action="withdraw",
        purpose="account_closure",
        detail={"runtime_scope": "member-database-primary-only"},
    )
    db.commit()
    # AS-IS cache and prompt-log surfaces are deliberately not claimed as purged here.
    return {
        "status": "accepted",
        "subject_ref": reference,
        "message": "계정 탈퇴 처리가 접수되었습니다. 현재 세션을 종료합니다.",
    }


@app.get("/api/v1/recruiter/jobs")
def recruiter_jobs(
    db: Session = Depends(get_db), user: User = Depends(require_role("recruiter"))
) -> list[dict[str, object]]:
    recruiter_company(db, user)
    jobs = db.scalars(
        select(Job)
        .options(joinedload(Job.company))
        .where(Job.company_id == user.company_id)
        .order_by(Job.created_at.desc())
    ).all()
    result = []
    for job in jobs:
        application_count = db.scalar(
            select(func.count(Application.id)).where(Application.job_id == job.id)
        )
        payload = job_payload(job)
        payload["application_count"] = application_count or 0
        result.append(payload)
    return result


@app.get("/api/v1/recruiter/overview")
def recruiter_overview(
    db: Session = Depends(get_db), user: User = Depends(require_role("recruiter"))
) -> dict[str, object]:
    """Return company-scoped operational facts without making hiring judgments."""

    company = recruiter_company(db, user)

    jobs = db.scalars(
        select(Job)
        .options(joinedload(Job.company))
        .where(Job.company_id == user.company_id)
        .order_by(Job.updated_at.desc(), Job.id.asc())
    ).all()
    job_ids = [job.id for job in jobs]

    application_counts: dict[str, int] = {}
    stage_counts = {
        "applied": 0,
        "reviewing": 0,
        "interview": 0,
        "offered": 0,
        "rejected": 0,
    }
    if job_ids:
        application_counts = {
            str(job_id): int(count)
            for job_id, count in db.execute(
                select(Application.job_id, func.count(Application.id))
                .where(Application.job_id.in_(job_ids))
                .group_by(Application.job_id)
            ).all()
        }
        for stage, count in db.execute(
            select(Application.status, func.count(Application.id))
            .where(Application.job_id.in_(job_ids))
            .group_by(Application.status)
        ).all():
            if stage in stage_counts:
                stage_counts[stage] = int(count)

    recent_jobs: list[dict[str, object]] = []
    for job in jobs[:4]:
        payload = job_payload(job)
        payload["application_count"] = application_counts.get(job.id, 0)
        recent_jobs.append(payload)

    total_applications = sum(application_counts.values())
    active_pipeline = sum(
        count for stage, count in stage_counts.items() if stage != "rejected"
    )
    audit(
        db,
        event_type="recruiter_overview_viewed",
        actor=user,
        target_type="company_workspace",
        target_ref=company.id,
        action="view_overview",
        purpose="recruiting_operations",
        detail={
            "job_count": len(jobs),
            "application_count": total_applications,
        },
    )
    db.commit()

    stage_labels = {
        "applied": "지원 완료",
        "reviewing": "서류 검토",
        "interview": "인터뷰",
        "offered": "처우 협의",
        "rejected": "전형 종료",
    }
    return {
        "company": company_profile_payload(company, include_opendart_linkage=True),
        "metrics": {
            "open_jobs": sum(job.status == "open" for job in jobs),
            "closed_jobs": sum(job.status == "closed" for job in jobs),
            "total_applications": total_applications,
            "active_pipeline": active_pipeline,
        },
        "application_stages": [
            {"status": stage, "label": stage_labels[stage], "count": count}
            for stage, count in stage_counts.items()
        ],
        "recent_jobs": recent_jobs,
        "customer_boundary": {
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
            "company_status_record": company.status,
            "company_status_gate_enforced": False,
        },
        "data_boundary": {
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
        },
    }


@app.get("/api/v1/recruiter/company-profile")
def get_recruiter_company_profile(
    db: Session = Depends(get_db), user: User = Depends(require_role("recruiter"))
) -> dict[str, object]:
    company = recruiter_company(db, user)
    return company_profile_payload(company, include_opendart_linkage=True)


@app.put("/api/v1/recruiter/company-profile")
def update_recruiter_company_profile(
    request: CompanyProfileRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("recruiter")),
) -> dict[str, object]:
    company = recruiter_company(db, user)
    company.direction_statement = request.direction_statement.strip()
    company.declared_values = request.declared_values
    company.profile_version = f"company-profile-{uuid.uuid4().hex[:12]}"
    audit(
        db,
        event_type="company_matching_profile_updated",
        actor=user,
        target_type="company_matching_profile",
        target_ref=company.id,
        action="update",
        purpose="recruiting_configuration",
        detail={
            "profile_version": company.profile_version,
            "declared_value_count": len(company.declared_values),
        },
    )
    db.commit()
    db.refresh(company)
    return company_profile_payload(company, include_opendart_linkage=True)


@app.post("/api/v1/recruiter/company-profile/opendart/refresh", status_code=202)
def refresh_recruiter_company_opendart(
    request: OpenDartRefreshRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("recruiter")),
) -> dict[str, object]:
    company = recruiter_company(db, user)
    attempted_at = datetime.now(timezone.utc)
    company.opendart_last_attempt_at = attempted_at
    dispatch_mode = os.getenv("OPENDART_DISPATCH_MODE", "fixture_inline").strip().lower()
    if dispatch_mode == "serverless_queue":
        message = build_refresh_message(
            company_id=company.id,
            corp_code=request.corp_code,
            requested_at=attempted_at,
        )
        company.opendart_sync_state = "REFRESH_DISPATCH_PENDING"
        company.opendart_pending_request_id = message["request_id"]
        company.opendart_pending_requested_at = attempted_at
        audit(
            db,
            event_type="company_opendart_refresh",
            actor=user,
            target_type="company_public_facts",
            target_ref=company.id,
            action="prepare_enqueue",
            result="dispatch_pending",
            purpose="company_profile_enrichment",
            detail={
                "provider": "OpenDART",
                "execution": "serverless_queue",
                "request_id": message["request_id"],
                "previous_snapshot_retained": bool(company.opendart_snapshot),
                "score_effect": "NONE",
            },
        )
        # The worker validates this request id against the company row. Commit the
        # pending marker before publishing so a fast consumer cannot discard a
        # legitimate message simply because the API transaction is still open.
        db.commit()
        try:
            enqueue_refresh(message)
        except OpenDartDispatchError as error:
            previous_snapshot_retained = bool(company.opendart_snapshot)
            company.opendart_sync_state = (
                "STALE_LAST_KNOWN_GOOD"
                if previous_snapshot_retained
                else "UNAVAILABLE_NO_SNAPSHOT"
            )
            company.opendart_pending_request_id = None
            company.opendart_pending_requested_at = None
            audit(
                db,
                event_type="company_opendart_refresh",
                actor=user,
                target_type="company_public_facts",
                target_ref=company.id,
                action="enqueue",
                result="not_queued",
                purpose="company_profile_enrichment",
                detail={
                    "provider": "OpenDART",
                    "execution": "serverless_queue",
                    "error_category": "QUEUE_UNAVAILABLE",
                    "previous_snapshot_retained": previous_snapshot_retained,
                    "score_effect": "NONE",
                },
            )
            db.commit()
            raise HTTPException(status_code=503, detail=str(error)) from None
        transition = db.execute(
            update(Company)
            .where(
                Company.id == company.id,
                Company.opendart_pending_request_id == message["request_id"],
                Company.opendart_sync_state == "REFRESH_DISPATCH_PENDING",
            )
            .values(opendart_sync_state="REFRESH_QUEUED")
            .execution_options(synchronize_session=False)
        )
        audit(
            db,
            event_type="company_opendart_refresh",
            actor=user,
            target_type="company_public_facts",
            target_ref=company.id,
            action="enqueue",
            result="queued",
            purpose="company_profile_enrichment",
            detail={
                "provider": "OpenDART",
                "execution": "serverless_queue",
                "request_id": message["request_id"],
                "previous_snapshot_retained": bool(company.opendart_snapshot),
                "pending_state_transitioned": transition.rowcount == 1,
                "score_effect": "NONE",
            },
        )
        db.commit()
        db.expire_all()
        company = recruiter_company(db, user)
        db.refresh(company)
        return {
            "refresh": {
                "state": "QUEUED",
                "request_id": message["request_id"],
                "execution": "serverless_queue",
            },
            "company_profile": company_profile_payload(
                company, include_opendart_linkage=True
            ),
        }
    if dispatch_mode != "fixture_inline":
        raise HTTPException(
            status_code=409,
            detail="OpenDART 갱신 실행 모드가 비활성화되어 있습니다",
        )
    try:
        snapshot = OpenDartClient(
            mode="fixture", clock=lambda: attempted_at
        ).refresh_company(request.corp_code)
        dart_company = snapshot.get("company")
        dart_name = (
            str(dart_company.get("legal_name", ""))
            if isinstance(dart_company, dict)
            else ""
        )
        if not company_names_match(company.name, dart_name):
            raise OpenDartError(
                "COMPANY_NAME_MISMATCH",
                "등록 기업명과 OpenDART 정식 회사명이 일치하지 않습니다",
            )
    except OpenDartError as error:
        previous_snapshot_retained = bool(company.opendart_snapshot)
        company.opendart_sync_state = (
            "STALE_LAST_KNOWN_GOOD"
            if previous_snapshot_retained
            else "UNAVAILABLE_NO_SNAPSHOT"
        )
        audit(
            db,
            event_type="company_opendart_refresh",
            actor=user,
            target_type="company_public_facts",
            target_ref=company.id,
            action="refresh",
            result="not_updated",
            purpose="company_profile_enrichment",
            detail={
                "provider": "OpenDART",
                "error_category": error.category,
                "previous_snapshot_retained": previous_snapshot_retained,
                "score_effect": "NONE",
            },
        )
        db.commit()
        if error.category in {"DISABLED", "COMPANY_NAME_MISMATCH"}:
            raise HTTPException(status_code=409, detail=str(error)) from None
        if error.category == "INVALID_CORP_CODE":
            raise HTTPException(status_code=422, detail=str(error)) from None
        if error.category == "NO_DATA":
            raise HTTPException(status_code=404, detail=str(error)) from None
        raise HTTPException(status_code=503, detail=str(error)) from None

    company.opendart_corp_code = request.corp_code
    company.opendart_snapshot = snapshot
    company.opendart_sync_state = (
        "AVAILABLE_SYNTHETIC_FIXTURE"
        if snapshot.get("synthetic") is True
        else "AVAILABLE_LIVE"
    )
    company.opendart_snapshot_version = (
        f"opendart-snapshot-{str(snapshot['content_sha256'])[:12]}"
    )
    company.opendart_synced_at = attempted_at
    company.opendart_pending_request_id = None
    company.opendart_pending_requested_at = None
    audit(
        db,
        event_type="company_opendart_refresh",
        actor=user,
        target_type="company_public_facts",
        target_ref=company.id,
        action="refresh",
        purpose="company_profile_enrichment",
        detail={
            "provider": "OpenDART",
            "source_kind": snapshot.get("source_kind"),
            "snapshot_version": company.opendart_snapshot_version,
            "disclosure_state": (
                snapshot.get("disclosures", {}).get("state")
                if isinstance(snapshot.get("disclosures"), dict)
                else "UNAVAILABLE"
            ),
            "score_effect": "NONE",
        },
    )
    db.commit()
    db.refresh(company)
    return {
        "refresh": {
            "state": "UPDATED_SYNTHETIC_FIXTURE",
            "request_id": None,
            "execution": "fixture_inline",
        },
        "company_profile": company_profile_payload(
            company, include_opendart_linkage=True
        ),
    }


@app.post("/api/v1/recruiter/jobs", status_code=201)
def create_recruiter_job(
    request: JobRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("recruiter")),
) -> dict[str, object]:
    company = recruiter_company(db, user)
    job = Job(company_id=user.company_id, **request.model_dump())
    job.company = company
    db.add(job)
    db.flush()
    audit(
        db,
        event_type="job_created",
        actor=user,
        target_type="job",
        target_ref=job.id,
        action="create",
        purpose="recruiting",
    )
    db.commit()
    db.refresh(job)
    return job_payload(job)


@app.put("/api/v1/recruiter/jobs/{job_id}")
def update_recruiter_job(
    job_id: str,
    request: JobRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("recruiter")),
) -> dict[str, object]:
    job = recruiter_job(db, job_id, user, denied_action="update")
    for field, value in request.model_dump().items():
        setattr(job, field, value)
    audit(
        db,
        event_type="job_updated",
        actor=user,
        target_type="job",
        target_ref=job.id,
        action="update",
        purpose="recruiting",
    )
    db.commit()
    db.refresh(job)
    return job_payload(job)


@app.get("/api/v1/recruiter/jobs/{job_id}/pipeline")
def recruiter_pipeline(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("recruiter")),
) -> dict[str, object]:
    job = recruiter_job(db, job_id, user, denied_action="view_pipeline")
    applications = db.scalars(
        select(Application)
        .options(joinedload(Application.candidate))
        .where(Application.job_id == job.id)
        .order_by(Application.applied_at.desc())
    ).all()
    rows: list[dict[str, object]] = []
    for application in applications:
        resume = db.scalar(select(Resume).where(Resume.user_id == application.candidate_id))
        if not resume:
            continue
        rows.append(
            {
                "id": application.id,
                "status": application.status,
                "applied_at": application.applied_at,
                "candidate": resume_payload(resume, application.candidate),
            }
        )
        audit(
            db,
            event_type="candidate_view",
            actor=user,
            target_type="candidate",
            target_ref=pseudonymous_ref(application.candidate_id),
            action="view_in_pipeline",
            purpose="recruiting",
            detail={"job_id": job.id, "application_id": application.id},
        )
    db.commit()
    return {"job": job_payload(job), "items": rows}


@app.patch("/api/v1/recruiter/applications/{application_id}")
def update_application_status(
    application_id: str,
    request: ApplicationStatusRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("recruiter")),
) -> dict[str, object]:
    recruiter_company(db, user)
    application = db.get(Application, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="지원 내역을 찾을 수 없습니다")
    job = db.get(Job, application.job_id)
    if not job:
        raise HTTPException(status_code=409, detail="지원 내역의 공고 참조를 확인할 수 없습니다")
    if job.company_id != user.company_id:
        audit(
            db,
            event_type="authorization_denied",
            actor=user,
            target_type="application",
            target_ref=application.id,
            action="update_status",
            result="denied",
            purpose="recruiting",
        )
        db.commit()
        raise HTTPException(status_code=403, detail="다른 기업의 지원 내역은 변경할 수 없습니다")
    application.status = request.status
    audit(
        db,
        event_type="application_status_changed",
        actor=user,
        target_type="application",
        target_ref=application.id,
        action=request.status,
        purpose="recruiting",
    )
    db.commit()
    return {"id": application.id, "status": application.status}


@app.get("/api/v1/recruiter/jobs/{job_id}/recommendations")
async def recruiter_recommendations(
    job_id: str,
    explanation_mode: Literal[
        "success", "timeout", "rate_limit", "provider_error", "malformed", "overclaim"
    ]
    | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("recruiter")),
) -> dict[str, object]:
    job = recruiter_job(db, job_id, user, denied_action="view_recommendations")
    require_failure_injection_enabled(explanation_mode)
    cache_key = (
        f"asis:{SCORE_RESPONSE_CONTRACT_VERSION}:recruiter-recommendations:"
        f"{job.id}:{job.updated_at.isoformat()}:{job.company.profile_version}:"
        f"{explanation_provider_config()['provider_config_fingerprint']}:"
        f"{explanation_mode or 'success'}"
    )
    cached = await get_cached(cache_key)
    if cached:
        cached["cache"] = "hit"
        cached["explanation_freshness"] = "CACHE_HIT_PROVIDER_NOT_REVALIDATED"
        cached["explanation_attempt"] = explanation_attempt_metadata(
            str(cached["explanation_status"]),
            item_count=len(cached["items"]),
            scope="CACHED_ORIGIN_REQUEST",
        )
        return cached

    rows = db.execute(
        select(User, Resume)
        .join(Resume, Resume.user_id == User.id)
        .join(Application, Application.candidate_id == User.id)
        .where(Application.job_id == job.id, User.active.is_(True))
    ).all()
    rows = list({candidate.id: (candidate, resume) for candidate, resume in rows}.values())
    candidates = [
        {
            "id": candidate.id,
            "desired_role": resume.desired_role,
            "skills": resume.skills,
            "years_experience": resume.years_experience,
        }
        for candidate, resume in rows
    ]
    match_body = await run_matcher(
        "/internal/match/candidates",
        {
            "job": {
                "id": job.id,
                "title": job.title,
                "required_skills": job.required_skills,
                "min_experience": job.min_experience,
            },
            "candidates": candidates,
            "limit": 20,
        },
    )
    row_map = {candidate.id: (candidate, resume) for candidate, resume in rows}
    explanation_items = []
    for item in match_body["items"]:
        candidate, resume = row_map[str(item["subject_ref"])]
        explanation_items.append(
            {
                "subject_ref": candidate.id,
                "score": item["score"],
                "score_breakdown": item["score_breakdown"],
                "matched_feature_ids": item["matched_feature_ids"],
                "matched_feature_labels": item["matched_feature_labels"],
                "candidate_context": {
                    "name": candidate.display_name,
                    "phone": resume.phone,
                    "email": candidate.email,
                    "birthdate": str(resume.birth_date) if resume.birth_date else "",
                    "address": resume.address_region,
                    "school": resume.education,
                    "certificates": resume.certificates,
                    "self_intro": resume.self_intro,
                },
                "company_context": {
                    "company_name": job.company.name,
                    "direction_statement": job.company.direction_statement,
                    "declared_values": job.company.declared_values,
                    "profile_version": job.company.profile_version,
                    "job_title": job.title,
                    "job_summary": job.summary,
                },
            }
        )
    correlation_id = str(uuid.uuid4())
    explanation_status, explanations = await run_explanations(
        explanation_items, correlation_id, explanation_mode
    )
    items: list[dict[str, object]] = []
    for match in match_body["items"]:
        candidate, resume = row_map[str(match["subject_ref"])]
        explanation = explanations.get(candidate.id)
        items.append(
            {
                "candidate": resume_payload(resume, candidate),
                "score": match["score"],
                "score_breakdown": match["score_breakdown"],
                "matched_feature_ids": match["matched_feature_ids"],
                "matched_feature_labels": match["matched_feature_labels"],
                "matcher_version": match["matcher_version"],
                "explanation": explanation
                or {"status": explanation_status, "text": None},
            }
        )
    response = {
        "job": job_payload(job),
        "recommendation_status": "AVAILABLE",
        "explanation_status": explanation_status,
        "matcher_version": match_body["matcher_version"],
        "items": items,
        "cache": "miss",
        "correlation_id": correlation_id,
        "explanation_freshness": "CURRENT_REQUEST_GATEWAY_RESULT",
        "explanation_attempt": explanation_attempt_metadata(
            explanation_status,
            item_count=len(explanation_items),
            scope="CURRENT_REQUEST",
        ),
        "provider_config_fingerprint": explanation_provider_config()[
            "provider_config_fingerprint"
        ],
    }
    # The AS-IS cache intentionally contains candidate display data and expires after 24 hours.
    if explanation_status == "AVAILABLE":
        await set_cached(cache_key, response)
    return response


@app.get("/api/v1/admin/audit")
def admin_audit(
    event_type: str = Query(default="", max_length=50),
    company_id: str = Query(default="", max_length=36),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> list[dict[str, object]]:
    statement = select(AuditEvent).order_by(AuditEvent.occurred_at.desc()).limit(limit)
    if event_type:
        statement = statement.where(AuditEvent.event_type == event_type)
    if company_id:
        statement = statement.where(AuditEvent.company_id == company_id)
    events = db.scalars(statement).all()
    response = [
        {
            "id": event.id,
            "event_type": event.event_type,
            "actor_user_id": event.actor_user_id,
            "actor_role": event.actor_role,
            "company_id": event.company_id,
            "target_type": event.target_type,
            "target_ref": event.target_ref,
            "purpose": event.purpose,
            "action": event.action,
            "result": event.result,
            "correlation_id": event.correlation_id,
            "retention_class": event.retention_class,
            "detail": event.detail,
            "occurred_at": event.occurred_at,
        }
        for event in events
    ]
    audit(
        db,
        event_type="audit_log_viewed",
        actor=user,
        target_type="audit_events",
        target_ref="filtered_query",
        action="list",
        purpose="security_monitoring",
        detail={
            "event_type_filter": event_type or None,
            "company_filter_applied": bool(company_id),
            "requested_limit": limit,
            "returned_count": len(response),
        },
    )
    db.commit()
    return response
