from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import OutcomeBase, get_db, outcome_engine
from .models import Job, User
from .security import current_user, parse_token


TRACE_CONTRACT_VERSION = "jc-receipt-v1"
RECOURSE_CONTRACT_VERSION = "jc-recourse-v1"
REVIEW_CONTRACT_VERSION = "jc-human-review-v1"
TRACE_STORE_NAMESPACE = "trace_rights_evidence"
MATCHER_FORMULA_VERSION = "deterministic-70-20-10-v1"
SCORE_BREAKDOWN_VERSION = "score-breakdown-v1"
TRACE_MODES = {"disabled", "shadow", "enforced"}
USED_FEATURE_IDS = ["feature.skills", "feature.experience", "feature.role"]
PII_EXCLUDED_FIELDS = {
    "address",
    "birthdate",
    "email",
    "name",
    "phone",
    "school",
    "certificates",
    "projects",
    "self_intro",
}
SAFE_FEATURE_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,99}$")
SAFE_SHA256 = re.compile(r"^[0-9a-f]{64}$")
SAFE_STRUCTURED_VALUE = re.compile(r"^[^@\r\n]{0,120}$")
PHONE_LIKE = re.compile(r"(?:\+?\d[\d .()-]{7,}\d)")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DecisionReceipt(OutcomeBase):
    """Immutable, minimal-PII receipt for one candidate/job score observation."""

    __tablename__ = "trace_decision_receipts"
    __table_args__ = (
        UniqueConstraint(
            "request_ref", "item_key", name="uq_trace_receipt_request_item"
        ),
        CheckConstraint(
            "capture_mode IN ('shadow', 'enforced')",
            name="ck_trace_receipt_capture_mode",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_ref: Mapped[str] = mapped_column(String(72), index=True)
    item_key: Mapped[str] = mapped_column(String(64))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    subject_ref: Mapped[str] = mapped_column(String(80), index=True)
    company_ref: Mapped[str] = mapped_column(String(36), index=True)
    job_ref: Mapped[str] = mapped_column(String(36), index=True)
    channel: Mapped[str] = mapped_column(String(48), index=True)
    capture_mode: Mapped[str] = mapped_column(String(16))
    source_status: Mapped[str] = mapped_column(String(32))
    cache_state: Mapped[str] = mapped_column(String(16))
    payload_json: Mapped[dict[str, object]] = mapped_column(JSON)
    integrity_sha256: Mapped[str] = mapped_column(String(64))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class RecourseCase(OutcomeBase):
    """Candidate-owned request plus a no-effect deterministic replay observation."""

    __tablename__ = "trace_recourse_cases"
    __table_args__ = (
        UniqueConstraint("request_ref", name="uq_trace_recourse_request"),
        CheckConstraint(
            "state IN ('PENDING_REVIEW', 'NEEDS_CANDIDATE_INFO', "
            "'ESCALATED', 'CLOSED_UPHELD', 'CLOSED_CHANGED')",
            name="ck_trace_recourse_state",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    receipt_id: Mapped[str] = mapped_column(
        ForeignKey("trace_decision_receipts.id"), index=True
    )
    request_ref: Mapped[str] = mapped_column(String(72), index=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    subject_ref: Mapped[str] = mapped_column(String(80), index=True)
    company_ref: Mapped[str] = mapped_column(String(36), index=True)
    job_ref: Mapped[str] = mapped_column(String(36), index=True)
    state: Mapped[str] = mapped_column(String(32), default="PENDING_REVIEW", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    payload_json: Mapped[dict[str, object]] = mapped_column(JSON)
    integrity_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class HumanReviewRecord(OutcomeBase):
    """Append-only admin reviewer disposition, separate from automated scoring."""

    __tablename__ = "trace_human_review_records"
    __table_args__ = (
        UniqueConstraint("request_ref", name="uq_trace_review_request"),
        CheckConstraint(
            "disposition IN ('UPHOLD', 'CHANGE', 'REQUEST_INFO', 'ESCALATE')",
            name="ck_trace_review_disposition",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("trace_recourse_cases.id"), index=True
    )
    request_ref: Mapped[str] = mapped_column(String(72), index=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    reviewer_ref: Mapped[str] = mapped_column(String(80))
    disposition: Mapped[str] = mapped_column(String(24), index=True)
    basis_code: Mapped[str] = mapped_column(String(48))
    from_state: Mapped[str] = mapped_column(String(32))
    to_state: Mapped[str] = mapped_column(String(32))
    expected_version: Mapped[int] = mapped_column(Integer)
    payload_json: Mapped[dict[str, object]] = mapped_column(JSON)
    integrity_sha256: Mapped[str] = mapped_column(String(64))
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CorrectedFeatures(StrictRequest):
    desired_role: str = Field(max_length=120)
    skills: list[str] = Field(max_length=50)
    years_experience: int = Field(ge=0, le=60)

    @field_validator("desired_role")
    @classmethod
    def safe_role(cls, value: str) -> str:
        value = value.strip()
        if (
            not SAFE_STRUCTURED_VALUE.fullmatch(value)
            or PHONE_LIKE.search(value)
            or "@" in value
        ):
            raise ValueError(
                "desired_role must be a structured role value without contact data"
            )
        return value

    @field_validator("skills")
    @classmethod
    def safe_skills(cls, values: list[str]) -> list[str]:
        normalised: list[str] = []
        seen: set[str] = set()
        for raw in values:
            value = raw.strip()
            if (
                not value
                or not SAFE_STRUCTURED_VALUE.fullmatch(value)
                or PHONE_LIKE.search(value)
                or "@" in value
            ):
                raise ValueError(
                    "skills must contain structured values without contact data"
                )
            key = value.casefold()
            if key not in seen:
                normalised.append(value)
                seen.add(key)
        return normalised


class RecourseRequest(StrictRequest):
    base_integrity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason_code: Literal[
        "FEATURE_INCORRECT", "FEATURE_MISSING", "EVIDENCE_VERSION", "OTHER_STRUCTURED"
    ]
    corrected_features: CorrectedFeatures


class ReviewRequest(StrictRequest):
    disposition: Literal["UPHOLD", "CHANGE", "REQUEST_INFO", "ESCALATE"]
    basis_code: Literal[
        "EVIDENCE_CONFIRMED",
        "CORRECTION_SUPPORTED",
        "MORE_EVIDENCE_NEEDED",
        "SPECIALIST_REVIEW_REQUIRED",
    ]
    expected_version: int = Field(ge=1)


class ReceiptIntegrityError(RuntimeError):
    pass


class TraceConflictError(RuntimeError):
    pass


def trace_mode() -> Literal["disabled", "shadow", "enforced"]:
    value = os.getenv("TRACE_MODE", "disabled").strip().lower()
    return value if value in TRACE_MODES else "disabled"  # type: ignore[return-value]


def trace_configuration_state() -> str:
    value = os.getenv("TRACE_MODE", "disabled").strip().lower()
    return "VALID" if value in TRACE_MODES else "INVALID_DISABLED"


def _canonical_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def canonical_json(value: object) -> str:
    """RFC-8259-compatible stable JSON used for every integrity binding."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=_canonical_default,
    )


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _subject_key() -> bytes:
    return os.getenv(
        "TRACE_SUBJECT_KEY", "synthetic-local-trace-subject-key-change-me"
    ).encode("utf-8")


def pseudonymous_subject_ref(user_id: str) -> str:
    digest = hmac.new(
        _subject_key(), f"candidate/{user_id}".encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"subject:{digest[:32]}"


def pseudonymous_reviewer_ref(user_id: str) -> str:
    digest = hmac.new(
        _subject_key(), f"reviewer/{user_id}".encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"reviewer:{digest[:32]}"


def request_ref(idempotency_key: str | None) -> str:
    opaque = idempotency_key or f"generated:{uuid.uuid4()}"
    return f"request:{hashlib.sha256(opaque.encode('utf-8')).hexdigest()[:40]}"


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _safe_feature_ids(values: object, label: str) -> list[str]:
    if not isinstance(values, list):
        raise ValueError(f"{label} must be a list")
    result: list[str] = []
    for value in values:
        if not isinstance(value, str) or not SAFE_FEATURE_ID.fullmatch(value):
            raise ValueError(f"{label} contains an unsafe feature id")
        if value not in result:
            result.append(value)
    return sorted(result)


def sanitise_score_breakdown(
    value: object, score: object | None = None
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("score_breakdown must be an object")
    factors = value.get("factors")
    if not isinstance(factors, list):
        raise ValueError("score_breakdown factors must be a list")
    safe_factors: list[dict[str, object]] = []
    seen: set[str] = set()
    for factor in factors:
        if not isinstance(factor, dict):
            raise ValueError("score factor must be an object")
        factor_id = factor.get("factor_id")
        if factor_id not in {"skills", "experience", "role"} or factor_id in seen:
            raise ValueError("score factor id is outside the 70/20/10 contract")
        seen.add(str(factor_id))
        safe_factors.append(
            {
                "factor_id": factor_id,
                "raw_points": _finite(factor.get("raw_points"), "raw_points"),
                "display_points": _finite(
                    factor.get("display_points"), "display_points"
                ),
                "max_points": _finite(factor.get("max_points"), "max_points"),
            }
        )
    if seen != {"skills", "experience", "role"}:
        raise ValueError("score factor set is incomplete")
    safe_factors.sort(
        key=lambda item: USED_FEATURE_IDS.index(f"feature.{item['factor_id']}")
    )
    formula_version = value.get("formula_version")
    schema_version = value.get("schema_version")
    policy_source = value.get("policy_source")
    if formula_version != MATCHER_FORMULA_VERSION:
        raise ValueError("formula version is not the existing deterministic contract")
    if schema_version != SCORE_BREAKDOWN_VERSION or policy_source != "platform_default":
        raise ValueError("score breakdown contract drift")
    total_points = _finite(value.get("total_points"), "total_points")
    if score is not None and not math.isclose(
        total_points, _finite(score, "score"), abs_tol=1e-6
    ):
        raise ValueError("score and breakdown total differ")
    excluded = value.get("excluded_input_fields")
    if not isinstance(excluded, list) or not PII_EXCLUDED_FIELDS.issubset(
        {item for item in excluded if isinstance(item, str)}
    ):
        raise ValueError("PII exclusion boundary is incomplete")
    return {
        "schema_version": schema_version,
        "formula_version": formula_version,
        "policy_source": policy_source,
        "total_points": total_points,
        "max_points": _finite(value.get("max_points"), "max_points"),
        "factors": safe_factors,
    }


def _fingerprints(
    *, matcher_version: object, score_breakdown: dict[str, object], provider: object
) -> dict[str, str]:
    if not isinstance(matcher_version, str) or not matcher_version:
        raise ValueError("matcher version missing")
    if not isinstance(provider, str) or not SAFE_SHA256.fullmatch(provider):
        raise ValueError("provider config fingerprint missing")
    weights = [
        [factor["factor_id"], factor["max_points"]]
        for factor in score_breakdown["factors"]  # type: ignore[index]
    ]
    dataset_profile = os.getenv("DATASET_PROFILE", "demo_not_for_measurement")
    return {
        "matcher_config_sha256": canonical_sha256(
            {
                "matcher_version": matcher_version,
                "formula_version": score_breakdown["formula_version"],
                "weights": weights,
            }
        ),
        "formula_sha256": canonical_sha256(
            {
                "formula_version": score_breakdown["formula_version"],
                "weights": weights,
            }
        ),
        "policy_sha256": canonical_sha256(
            {"policy_source": score_breakdown["policy_source"], "weights": weights}
        ),
        "runtime_dataset_sha256": canonical_sha256(
            {"dataset_profile": dataset_profile}
        ),
        "provider_config_sha256": provider,
    }


@dataclass(frozen=True)
class ReceiptDraft:
    id: str
    request_ref: str
    item_key: str
    request_fingerprint: str
    subject_ref: str
    company_ref: str
    job_ref: str
    channel: str
    capture_mode: str
    source_status: str
    cache_state: str
    payload_json: dict[str, object]
    integrity_sha256: str
    recorded_at: datetime


def _receipt_draft(
    *,
    request_reference: str,
    subject_ref: str,
    company_ref: str,
    job_ref: str,
    channel: str,
    capture_mode: str,
    cache_state: object,
    response: dict[str, object],
    item: dict[str, object],
) -> ReceiptDraft:
    receipt_id = str(uuid.uuid4())
    observed_at = utcnow()
    safe_breakdown = sanitise_score_breakdown(
        item.get("score_breakdown"), item.get("score")
    )
    matched_feature_ids = _safe_feature_ids(
        item.get("matched_feature_ids"), "matched_feature_ids"
    )
    excluded_feature_ids = [f"excluded.{name}" for name in sorted(PII_EXCLUDED_FIELDS)]
    cache_value = cache_state if cache_state in {"hit", "miss"} else "unknown"
    source_status = "CACHE_HIT_RESPONSE" if cache_value == "hit" else "CURRENT_RESPONSE"
    fingerprints = _fingerprints(
        matcher_version=item.get("matcher_version") or response.get("matcher_version"),
        score_breakdown=safe_breakdown,
        provider=response.get("provider_config_fingerprint"),
    )
    payload: dict[str, object] = {
        "contract_version": TRACE_CONTRACT_VERSION,
        "receipt_id": receipt_id,
        "request_ref": request_reference,
        "channel": channel,
        "subject_ref": subject_ref,
        "company_ref": company_ref,
        "job_ref": job_ref,
        "source_status": source_status,
        "cache_state": cache_value,
        "used_feature_ids": list(USED_FEATURE_IDS),
        "matched_feature_ids": matched_feature_ids,
        "excluded_feature_ids": excluded_feature_ids,
        "score_breakdown": safe_breakdown,
        "fingerprints": fingerprints,
        "timestamps": {
            "matcher_response_observed_at": observed_at.isoformat().replace(
                "+00:00", "Z"
            ),
            "receipt_recorded_at": observed_at.isoformat().replace("+00:00", "Z"),
        },
        "evidence_refs": [
            f"job:{job_ref}#structured-match-input",
            f"subject:{subject_ref}#structured-match-input",
            f"response:{response.get('correlation_id', 'not-available')}#score-envelope",
        ],
        "human_review_required": True,
        "automatic_hiring_decision": False,
        "automatic_recourse_decision": False,
        "iso_conformance_claimed": False,
        "residual_risk_determined": False,
        "storage_namespace": TRACE_STORE_NAMESPACE,
    }
    semantic_payload = {
        key: value
        for key, value in payload.items()
        if key
        not in {
            "receipt_id",
            "request_ref",
            "timestamps",
            "source_status",
            "cache_state",
        }
    }
    item_key = canonical_sha256(
        {"channel": channel, "subject_ref": subject_ref, "job_ref": job_ref}
    )
    return ReceiptDraft(
        id=receipt_id,
        request_ref=request_reference,
        item_key=item_key,
        request_fingerprint=canonical_sha256(semantic_payload),
        subject_ref=subject_ref,
        company_ref=company_ref,
        job_ref=job_ref,
        channel=channel,
        capture_mode=capture_mode,
        source_status=source_status,
        cache_state=str(cache_value),
        payload_json=payload,
        integrity_sha256=canonical_sha256(payload),
        recorded_at=observed_at,
    )


def build_receipt_drafts(
    *,
    path: str,
    auth_payload: dict[str, object],
    response: dict[str, object],
    idempotency_key: str | None,
    capture_mode: str,
) -> list[ReceiptDraft]:
    user_id = auth_payload.get("sub")
    role = auth_payload.get("role")
    if not isinstance(user_id, str) or not isinstance(role, str):
        raise ValueError("authenticated subject is unavailable")
    request_reference = request_ref(idempotency_key)
    items = response.get("items")
    if not isinstance(items, list):
        raise ValueError("recommendation items missing")
    drafts: list[ReceiptDraft] = []
    if path == "/api/v1/candidates/me/recommendations":
        if role != "candidate":
            raise ValueError("candidate trace channel role mismatch")
        subject = pseudonymous_subject_ref(user_id)
        for raw_item in items:
            if not isinstance(raw_item, dict) or not isinstance(
                raw_item.get("job"), dict
            ):
                raise ValueError("candidate recommendation item malformed")
            job = raw_item["job"]
            job_ref = job.get("id")
            company_ref = job.get("company_id")
            if not isinstance(job_ref, str) or not isinstance(company_ref, str):
                raise ValueError("candidate recommendation reference malformed")
            drafts.append(
                _receipt_draft(
                    request_reference=request_reference,
                    subject_ref=subject,
                    company_ref=company_ref,
                    job_ref=job_ref,
                    channel="CANDIDATE_RECOMMENDATION",
                    capture_mode=capture_mode,
                    cache_state=response.get("cache"),
                    response=response,
                    item=raw_item,
                )
            )
    elif re.fullmatch(r"/api/v1/recruiter/jobs/[^/]+/recommendations", path):
        if role != "recruiter" or not isinstance(response.get("job"), dict):
            raise ValueError("recruiter trace channel role mismatch")
        job = response["job"]
        job_ref = job.get("id")
        company_ref = job.get("company_id")
        if not isinstance(job_ref, str) or not isinstance(company_ref, str):
            raise ValueError("recruiter recommendation reference malformed")
        for raw_item in items:
            if not isinstance(raw_item, dict) or not isinstance(
                raw_item.get("candidate"), dict
            ):
                raise ValueError("recruiter recommendation item malformed")
            candidate_id = raw_item["candidate"].get("user_id")
            if not isinstance(candidate_id, str):
                raise ValueError("candidate reference missing")
            drafts.append(
                _receipt_draft(
                    request_reference=request_reference,
                    subject_ref=pseudonymous_subject_ref(candidate_id),
                    company_ref=company_ref,
                    job_ref=job_ref,
                    channel="RECRUITER_RECOMMENDATION",
                    capture_mode=capture_mode,
                    cache_state=response.get("cache"),
                    response=response,
                    item=raw_item,
                )
            )
    else:
        return []
    return drafts


def _persist_receipt_drafts(
    drafts: list[ReceiptDraft], *, engine=None
) -> list[DecisionReceipt]:
    if not drafts:
        return []
    with Session(bind=engine or outcome_engine, expire_on_commit=False) as session:
        request_reference = drafts[0].request_ref
        existing = session.scalars(
            select(DecisionReceipt).where(
                DecisionReceipt.request_ref == request_reference
            )
        ).all()
        by_key = {item.item_key: item for item in existing}
        for draft in drafts:
            found = by_key.get(draft.item_key)
            if found and not hmac.compare_digest(
                found.request_fingerprint, draft.request_fingerprint
            ):
                raise TraceConflictError(
                    "idempotency key was reused for different scores"
                )
        for draft in drafts:
            if draft.item_key in by_key:
                continue
            session.add(
                DecisionReceipt(
                    id=draft.id,
                    request_ref=draft.request_ref,
                    item_key=draft.item_key,
                    request_fingerprint=draft.request_fingerprint,
                    subject_ref=draft.subject_ref,
                    company_ref=draft.company_ref,
                    job_ref=draft.job_ref,
                    channel=draft.channel,
                    capture_mode=draft.capture_mode,
                    source_status=draft.source_status,
                    cache_state=draft.cache_state,
                    payload_json=draft.payload_json,
                    integrity_sha256=draft.integrity_sha256,
                    recorded_at=draft.recorded_at,
                )
            )
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        stored = session.scalars(
            select(DecisionReceipt).where(
                DecisionReceipt.request_ref == request_reference
            )
        ).all()
        stored_by_key = {item.item_key: item for item in stored}
        result: list[DecisionReceipt] = []
        for draft in drafts:
            found = stored_by_key.get(draft.item_key)
            if not found or not hmac.compare_digest(
                found.request_fingerprint, draft.request_fingerprint
            ):
                raise TraceConflictError("concurrent receipt write conflicted")
            verify_receipt(found)
            result.append(found)
        return result


def verify_receipt(receipt: DecisionReceipt) -> None:
    expected = canonical_sha256(receipt.payload_json)
    payload = receipt.payload_json
    bindings = {
        "receipt_id": receipt.id,
        "request_ref": receipt.request_ref,
        "subject_ref": receipt.subject_ref,
        "company_ref": receipt.company_ref,
        "job_ref": receipt.job_ref,
        "channel": receipt.channel,
        "source_status": receipt.source_status,
        "cache_state": receipt.cache_state,
    }
    if not hmac.compare_digest(expected, receipt.integrity_sha256) or any(
        payload.get(key) != value for key, value in bindings.items()
    ):
        raise ReceiptIntegrityError("decision receipt integrity binding failed")


def verify_case(case: RecourseCase) -> None:
    bindings = {
        "case_id": case.id,
        "receipt_id": case.receipt_id,
        "request_ref": case.request_ref,
        "subject_ref": case.subject_ref,
        "company_ref": case.company_ref,
        "job_ref": case.job_ref,
    }
    if not hmac.compare_digest(
        canonical_sha256(case.payload_json), case.integrity_sha256
    ) or any(case.payload_json.get(key) != value for key, value in bindings.items()):
        raise ReceiptIntegrityError("recourse case integrity binding failed")


def verify_review(review: HumanReviewRecord) -> None:
    bindings = {
        "review_id": review.id,
        "case_id": review.case_id,
        "request_ref": review.request_ref,
        "reviewer_ref": review.reviewer_ref,
        "disposition": review.disposition,
        "basis_code": review.basis_code,
        "from_state": review.from_state,
        "to_state": review.to_state,
        "expected_version": review.expected_version,
    }
    if not hmac.compare_digest(
        canonical_sha256(review.payload_json), review.integrity_sha256
    ) or any(review.payload_json.get(key) != value for key, value in bindings.items()):
        raise ReceiptIntegrityError("human review integrity binding failed")


def _trace_error(status_code: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": detail,
            "error_code": code,
            "automatic_hiring_decision": False,
            "automatic_recourse_decision": False,
        },
        headers={"Cache-Control": "no-store, private", "Pragma": "no-cache"},
    )


async def trace_capture_middleware(request: Request, call_next):
    response = await call_next(request)
    mode = trace_mode()
    path = request.url.path.rstrip("/") or "/"
    is_trace_source = path == "/api/v1/candidates/me/recommendations" or bool(
        re.fullmatch(r"/api/v1/recruiter/jobs/[^/]+/recommendations", path)
    )
    if mode == "disabled" or not is_trace_source or response.status_code != 200:
        return response
    body = b"".join([chunk async for chunk in response.body_iterator])
    headers = dict(response.headers)
    headers.pop("content-length", None)
    status_value = "NOT_RECORDED"
    receipt_refs: list[dict[str, str]] = []
    payload: dict[str, object] | None = None
    try:
        decoded = json.loads(body)
        if not isinstance(decoded, dict):
            raise ValueError("recommendation response is not an object")
        payload = decoded
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer "):
            raise ValueError("authenticated trace subject missing")
        auth_payload = parse_token(authorization.removeprefix("Bearer ").strip())
        drafts = build_receipt_drafts(
            path=path,
            auth_payload=auth_payload,
            response=payload,
            idempotency_key=request.headers.get("idempotency-key"),
            capture_mode=mode,
        )
        stored = _persist_receipt_drafts(drafts)
        if not drafts:
            status_value = "NOT_NEEDED_EMPTY_SET"
        elif all(item.cache_state == "hit" for item in stored):
            status_value = "RECORDED_CACHE_HIT"
        else:
            status_value = "RECORDED_CURRENT"
        receipt_refs = [
            {
                "receipt_id": item.id,
                "job_ref": item.job_ref,
                "integrity_sha256": item.integrity_sha256,
            }
            for item in stored
        ]
    except TraceConflictError:
        if mode == "enforced":
            return _trace_error(
                409,
                "TRACE_IDEMPOTENCY_CONFLICT",
                "The request key is already bound to a different receipt observation.",
            )
        status_value = "IDEMPOTENCY_CONFLICT_SHADOW"
    except Exception:
        if mode == "enforced":
            return _trace_error(
                503,
                "TRACE_RECEIPT_UNAVAILABLE",
                "The enforced receipt boundary could not persist an integrity-bound receipt.",
            )
        status_value = "STORE_UNAVAILABLE_SHADOW"
    if isinstance(payload, dict):
        payload["trace_receipt"] = {
            "contract_version": TRACE_CONTRACT_VERSION,
            "mode": mode,
            "source_status": status_value,
            "receipt_refs": receipt_refs,
            "human_review_required": True,
            "automatic_hiring_decision": False,
        }
        body = canonical_json(payload).encode("utf-8")
    headers["X-JCareer-Trace-Source-Status"] = status_value
    return Response(
        content=body,
        status_code=response.status_code,
        headers=headers,
        media_type="application/json",
        background=response.background,
    )


def _job_in_recruiter_scope(db: Session, user: User, job_ref: str) -> bool:
    if not user.company_id:
        return False
    job = db.get(Job, job_ref)
    return bool(job and job.company_id == user.company_id)


def authorise_receipt(db: Session, user: User, receipt: DecisionReceipt) -> None:
    if user.role == "admin":
        return
    if user.role == "candidate" and receipt.subject_ref == pseudonymous_subject_ref(
        user.id
    ):
        return
    if (
        user.role == "recruiter"
        and receipt.company_ref == user.company_id
        and _job_in_recruiter_scope(db, user, receipt.job_ref)
    ):
        return
    raise HTTPException(
        status_code=403, detail="Receipt is outside the caller's scope."
    )


def _review_payload(review: HumanReviewRecord) -> dict[str, object]:
    verify_review(review)
    return {
        **review.payload_json,
        "integrity_sha256": review.integrity_sha256,
        "integrity_state": "VERIFIED",
    }


def case_payload(db: Session, case: RecourseCase) -> dict[str, object]:
    verify_case(case)
    reviews = db.scalars(
        select(HumanReviewRecord)
        .where(HumanReviewRecord.case_id == case.id)
        .order_by(HumanReviewRecord.expected_version, HumanReviewRecord.id)
    ).all()
    expected_state = "PENDING_REVIEW"
    expected_version = 1
    for review in reviews:
        verify_review(review)
        if (
            review.from_state != expected_state
            or review.expected_version != expected_version
        ):
            raise ReceiptIntegrityError("human review state chain failed")
        expected_state = review.to_state
        expected_version += 1
    if case.state != expected_state or case.version != expected_version:
        raise ReceiptIntegrityError("recourse case state is not review-bound")
    return {
        **case.payload_json,
        "state": case.state,
        "version": case.version,
        "updated_at": case.updated_at,
        "integrity_sha256": case.integrity_sha256,
        "integrity_state": "VERIFIED",
        "human_reviews": [_review_payload(review) for review in reviews],
    }


def receipt_payload(db: Session, receipt: DecisionReceipt) -> dict[str, object]:
    verify_receipt(receipt)
    cases = db.scalars(
        select(RecourseCase)
        .where(RecourseCase.receipt_id == receipt.id)
        .order_by(RecourseCase.created_at.desc())
    ).all()
    return {
        **receipt.payload_json,
        "capture_mode": receipt.capture_mode,
        "integrity_sha256": receipt.integrity_sha256,
        "integrity_state": "VERIFIED",
        "recourse_cases": [case_payload(db, case) for case in cases],
    }


router = APIRouter(prefix="/api/v1/trace", tags=["trace-rights-evidence"])


@router.get("/status")
def get_trace_status() -> dict[str, object]:
    return {
        "contract_version": TRACE_CONTRACT_VERSION,
        "mode": trace_mode(),
        "configuration_state": trace_configuration_state(),
        "default_mode": "disabled",
        "store_namespace": TRACE_STORE_NAMESPACE,
        "mlops_receipt_store_shared": False,
        "automatic_hiring_decision": False,
        "automatic_recourse_decision": False,
        "iso_conformance_claimed": False,
        "residual_risk_determined": False,
    }


@router.get("/receipts")
def list_receipts(
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, object]:
    statement = select(DecisionReceipt)
    if user.role == "candidate":
        statement = statement.where(
            DecisionReceipt.subject_ref == pseudonymous_subject_ref(user.id)
        )
    elif user.role == "recruiter":
        if not user.company_id:
            raise HTTPException(
                status_code=409, detail="Recruiter company link is missing."
            )
        job_refs = db.scalars(
            select(Job.id).where(Job.company_id == user.company_id)
        ).all()
        statement = statement.where(
            DecisionReceipt.company_ref == user.company_id,
            DecisionReceipt.job_ref.in_(job_refs),
        )
    elif user.role != "admin":
        raise HTTPException(status_code=403, detail="Receipt access is not permitted.")
    receipts = db.scalars(
        statement.order_by(DecisionReceipt.recorded_at.desc()).limit(limit)
    ).all()
    try:
        items = [receipt_payload(db, receipt) for receipt in receipts]
    except ReceiptIntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="Receipt integrity verification failed."
        ) from exc
    return {"mode": trace_mode(), "items": items}


@router.get("/receipts/{receipt_id}")
def get_receipt(
    receipt_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, object]:
    receipt = db.get(DecisionReceipt, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Decision receipt not found.")
    authorise_receipt(db, user, receipt)
    try:
        return receipt_payload(db, receipt)
    except ReceiptIntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="Receipt integrity verification failed."
        ) from exc


MatcherRunner = Callable[[str, dict[str, object]], Awaitable[dict[str, object]]]
_matcher_runner: MatcherRunner | None = None


def build_replay_observation(
    receipt: DecisionReceipt, matcher_item: dict[str, object]
) -> dict[str, object]:
    verify_receipt(receipt)
    original = receipt.payload_json["score_breakdown"]
    corrected = sanitise_score_breakdown(
        matcher_item.get("score_breakdown"), matcher_item.get("score")
    )
    matched = _safe_feature_ids(
        matcher_item.get("matched_feature_ids"), "matched_feature_ids"
    )
    original_total = _finite(original["total_points"], "original total")  # type: ignore[index]
    corrected_total = _finite(corrected["total_points"], "corrected total")
    return {
        "observation_version": "recourse-twin-v1",
        "original": {
            "score_breakdown": original,
            "matched_feature_ids": receipt.payload_json["matched_feature_ids"],
        },
        "corrected": {
            "score_breakdown": corrected,
            "matched_feature_ids": matched,
        },
        "delta_points": round(corrected_total - original_total, 6),
        "matcher_version": matcher_item.get("matcher_version"),
        "formula_version": MATCHER_FORMULA_VERSION,
        "observed_at": utcnow().isoformat().replace("+00:00", "Z"),
        "observation_only": True,
        "score_or_ranking_effect": "NONE",
        "automatic_hiring_decision": False,
        "automatic_recourse_decision": False,
        "human_review_required": True,
    }


def _create_recourse_case(
    db: Session,
    *,
    receipt: DecisionReceipt,
    request_reference: str,
    reason_code: str,
    replay: dict[str, object],
) -> RecourseCase:
    replay_fingerprint_view = {
        key: value for key, value in replay.items() if key != "observed_at"
    }
    semantic = {
        "receipt_id": receipt.id,
        "base_integrity_sha256": receipt.integrity_sha256,
        "reason_code": reason_code,
        "corrected_feature_ids": list(USED_FEATURE_IDS),
        "replay_observation": replay_fingerprint_view,
    }
    request_fingerprint = canonical_sha256(semantic)
    existing = db.scalar(
        select(RecourseCase).where(RecourseCase.request_ref == request_reference)
    )
    if existing:
        if not hmac.compare_digest(existing.request_fingerprint, request_fingerprint):
            raise TraceConflictError("recourse idempotency key conflict")
        verify_case(existing)
        return existing
    case_id = str(uuid.uuid4())
    created_at = utcnow()
    payload: dict[str, object] = {
        "contract_version": RECOURSE_CONTRACT_VERSION,
        "case_id": case_id,
        "receipt_id": receipt.id,
        "request_ref": request_reference,
        "subject_ref": receipt.subject_ref,
        "company_ref": receipt.company_ref,
        "job_ref": receipt.job_ref,
        "base_integrity_sha256": receipt.integrity_sha256,
        "reason_code": reason_code,
        "corrected_feature_ids": list(USED_FEATURE_IDS),
        "replay_observation": replay,
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "candidate_owned": True,
        "automatic_recourse_decision": False,
        "human_review_required": True,
    }
    case = RecourseCase(
        id=case_id,
        receipt_id=receipt.id,
        request_ref=request_reference,
        request_fingerprint=request_fingerprint,
        subject_ref=receipt.subject_ref,
        company_ref=receipt.company_ref,
        job_ref=receipt.job_ref,
        state="PENDING_REVIEW",
        version=1,
        payload_json=payload,
        integrity_sha256=canonical_sha256(payload),
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(case)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(RecourseCase).where(RecourseCase.request_ref == request_reference)
        )
        if not existing or not hmac.compare_digest(
            existing.request_fingerprint, request_fingerprint
        ):
            raise TraceConflictError("concurrent recourse request conflict")
        verify_case(existing)
        return existing
    return case


@router.post("/receipts/{receipt_id}/recourse", status_code=201)
async def create_recourse(
    receipt_id: str,
    request: RecourseRequest,
    idempotency_key: str = Header(
        min_length=8, max_length=128, alias="Idempotency-Key"
    ),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, object]:
    if user.role != "candidate":
        raise HTTPException(
            status_code=403, detail="Only the candidate may request recourse."
        )
    receipt = db.get(DecisionReceipt, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Decision receipt not found.")
    authorise_receipt(db, user, receipt)
    try:
        verify_receipt(receipt)
    except ReceiptIntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="Receipt integrity verification failed."
        ) from exc
    if not hmac.compare_digest(receipt.integrity_sha256, request.base_integrity_sha256):
        raise HTTPException(status_code=409, detail="Receipt version conflict.")
    job = db.get(Job, receipt.job_ref)
    if not job or job.company_id != receipt.company_ref:
        raise HTTPException(
            status_code=409, detail="Bound job evidence is unavailable."
        )
    if _matcher_runner is None:
        raise HTTPException(
            status_code=503, detail="Deterministic replay is unavailable."
        )
    match_body = await _matcher_runner(
        "/internal/match/candidates",
        {
            "job": {
                "id": job.id,
                "title": job.title,
                "required_skills": job.required_skills,
                "min_experience": job.min_experience,
            },
            "candidates": [
                {
                    "id": receipt.subject_ref,
                    "desired_role": request.corrected_features.desired_role,
                    "skills": request.corrected_features.skills,
                    "years_experience": request.corrected_features.years_experience,
                }
            ],
            "limit": 1,
        },
    )
    items = match_body.get("items")
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        raise HTTPException(
            status_code=503, detail="Deterministic replay is unavailable."
        )
    replay = build_replay_observation(receipt, items[0])
    try:
        case = _create_recourse_case(
            db,
            receipt=receipt,
            request_reference=request_ref(idempotency_key),
            reason_code=request.reason_code,
            replay=replay,
        )
        return case_payload(db, case)
    except TraceConflictError as exc:
        raise HTTPException(
            status_code=409, detail="Recourse request key conflict."
        ) from exc


def _case_receipt(db: Session, case: RecourseCase) -> DecisionReceipt:
    receipt = db.get(DecisionReceipt, case.receipt_id)
    if not receipt:
        raise HTTPException(
            status_code=409, detail="Bound decision receipt is unavailable."
        )
    return receipt


@router.get("/cases")
def list_cases(
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, object]:
    statement = select(RecourseCase)
    if user.role == "candidate":
        statement = statement.where(
            RecourseCase.subject_ref == pseudonymous_subject_ref(user.id)
        )
    elif user.role == "recruiter":
        if not user.company_id:
            raise HTTPException(
                status_code=409, detail="Recruiter company link is missing."
            )
        job_refs = db.scalars(
            select(Job.id).where(Job.company_id == user.company_id)
        ).all()
        statement = statement.where(
            RecourseCase.company_ref == user.company_id,
            RecourseCase.job_ref.in_(job_refs),
        )
    elif user.role != "admin":
        raise HTTPException(status_code=403, detail="Recourse access is not permitted.")
    cases = db.scalars(
        statement.order_by(RecourseCase.updated_at.desc()).limit(limit)
    ).all()
    try:
        items = [case_payload(db, case) for case in cases]
    except ReceiptIntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="Case integrity verification failed."
        ) from exc
    return {"mode": trace_mode(), "items": items}


@router.get("/cases/{case_id}")
def get_case(
    case_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, object]:
    case = db.get(RecourseCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Recourse case not found.")
    receipt = _case_receipt(db, case)
    authorise_receipt(db, user, receipt)
    try:
        return case_payload(db, case)
    except ReceiptIntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="Case integrity verification failed."
        ) from exc


DISPOSITION_STATE = {
    "UPHOLD": "CLOSED_UPHELD",
    "CHANGE": "CLOSED_CHANGED",
    "REQUEST_INFO": "NEEDS_CANDIDATE_INFO",
    "ESCALATE": "ESCALATED",
}
DISPOSITION_BASIS = {
    "UPHOLD": "EVIDENCE_CONFIRMED",
    "CHANGE": "CORRECTION_SUPPORTED",
    "REQUEST_INFO": "MORE_EVIDENCE_NEEDED",
    "ESCALATE": "SPECIALIST_REVIEW_REQUIRED",
}
REVIEWABLE_STATES = {
    "PENDING_REVIEW": {"UPHOLD", "CHANGE", "REQUEST_INFO", "ESCALATE"},
    "NEEDS_CANDIDATE_INFO": {"UPHOLD", "CHANGE", "REQUEST_INFO", "ESCALATE"},
    "ESCALATED": {"UPHOLD", "CHANGE", "REQUEST_INFO"},
}


def record_human_review(
    db: Session,
    *,
    case: RecourseCase,
    reviewer: User,
    request_reference: str,
    request: ReviewRequest,
) -> HumanReviewRecord:
    if reviewer.role != "admin":
        raise HTTPException(
            status_code=403, detail="Only an admin reviewer may record disposition."
        )
    if DISPOSITION_BASIS[request.disposition] != request.basis_code:
        raise HTTPException(
            status_code=422, detail="Disposition and basis code do not match."
        )
    semantic = {
        "case_id": case.id,
        "disposition": request.disposition,
        "basis_code": request.basis_code,
        "expected_version": request.expected_version,
    }
    request_fingerprint = canonical_sha256(semantic)
    existing = db.scalar(
        select(HumanReviewRecord).where(
            HumanReviewRecord.request_ref == request_reference
        )
    )
    if existing:
        if not hmac.compare_digest(existing.request_fingerprint, request_fingerprint):
            raise TraceConflictError("review idempotency key conflict")
        verify_review(existing)
        return existing
    if request.disposition not in REVIEWABLE_STATES.get(case.state, set()):
        raise TraceConflictError("case state does not allow this disposition")
    if case.version != request.expected_version:
        raise TraceConflictError("case version conflict")
    reviewed_at = utcnow()
    review_id = str(uuid.uuid4())
    to_state = DISPOSITION_STATE[request.disposition]
    payload: dict[str, object] = {
        "contract_version": REVIEW_CONTRACT_VERSION,
        "review_id": review_id,
        "case_id": case.id,
        "request_ref": request_reference,
        "reviewer_ref": pseudonymous_reviewer_ref(reviewer.id),
        "disposition": request.disposition,
        "basis_code": request.basis_code,
        "from_state": case.state,
        "to_state": to_state,
        "expected_version": request.expected_version,
        "reviewed_at": reviewed_at.isoformat().replace("+00:00", "Z"),
        "human_review": True,
        "automatic_recourse_decision": False,
    }
    review = HumanReviewRecord(
        id=review_id,
        case_id=case.id,
        request_ref=request_reference,
        request_fingerprint=request_fingerprint,
        reviewer_ref=str(payload["reviewer_ref"]),
        disposition=request.disposition,
        basis_code=request.basis_code,
        from_state=case.state,
        to_state=to_state,
        expected_version=request.expected_version,
        payload_json=payload,
        integrity_sha256=canonical_sha256(payload),
        reviewed_at=reviewed_at,
    )
    result = db.execute(
        update(RecourseCase)
        .where(
            RecourseCase.id == case.id,
            RecourseCase.version == request.expected_version,
            RecourseCase.state == case.state,
        )
        .values(
            state=to_state,
            version=request.expected_version + 1,
            updated_at=reviewed_at,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise TraceConflictError("concurrent case update conflict")
    db.add(review)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(HumanReviewRecord).where(
                HumanReviewRecord.request_ref == request_reference
            )
        )
        if not existing or not hmac.compare_digest(
            existing.request_fingerprint, request_fingerprint
        ):
            raise TraceConflictError("concurrent review request conflict")
        verify_review(existing)
        return existing
    db.refresh(case)
    return review


@router.post("/cases/{case_id}/reviews", status_code=201)
def create_human_review(
    case_id: str,
    request: ReviewRequest,
    idempotency_key: str = Header(
        min_length=8, max_length=128, alias="Idempotency-Key"
    ),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, object]:
    if user.role != "admin":
        raise HTTPException(
            status_code=403, detail="Only an admin reviewer may record disposition."
        )
    case = db.get(RecourseCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Recourse case not found.")
    try:
        verify_case(case)
        review = record_human_review(
            db,
            case=case,
            reviewer=user,
            request_reference=request_ref(idempotency_key),
            request=request,
        )
        refreshed = db.get(RecourseCase, case.id)
        if not refreshed:
            raise ReceiptIntegrityError("reviewed case disappeared")
        return {
            "review": _review_payload(review),
            "case": case_payload(db, refreshed),
        }
    except TraceConflictError as exc:
        raise HTTPException(
            status_code=409, detail="Review state or request conflict."
        ) from exc
    except ReceiptIntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="Case integrity verification failed."
        ) from exc


def install_trace(app, *, matcher_runner: MatcherRunner) -> None:
    """Register the rights/evidence layer without changing existing route handlers."""

    global _matcher_runner
    _matcher_runner = matcher_runner
    if getattr(app.state, "trace_rights_installed", False):
        return
    app.include_router(router)
    app.middleware("http")(trace_capture_middleware)
    app.state.trace_rights_installed = True
