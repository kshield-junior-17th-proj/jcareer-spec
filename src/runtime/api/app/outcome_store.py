"""Isolated synthetic document-outcome observations for the J-Career demo.

This module stores generated labels and bounded numeric features in the
separate outcome database. It does not store resume/project source text or
direct identifiers, does not activate a model, and does not produce a hiring
probability or candidate-quality judgment.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, validates

from .database import OutcomeBase


DATASET_VERSION = "synthetic-document-outcomes-v1"
FEATURE_SCHEMA_VERSION = "jcareer-document-feature-snapshot-v1"
LABEL_SEMANTICS = (
    "synthetic_document_rule_outcome_not_hiring_decision_quality_or_probability"
)
GENERATION_METHOD = "stable_hash_plus_bounded_feature_rule_v1"
SOURCE_PROFILE = "jcareer_synthetic_runtime_seed_v1"
RESULT_SOURCE = "synthetic_rule_v1"
NO_EFFECT = "NONE"
FEATURE_ALLOWLIST = (
    "skill_overlap",
    "experience_fit",
    "role_overlap",
    "self_intro_job_overlap",
    "company_direction_overlap",
)
DOCUMENT_RESULTS = frozenset({"passed", "not_passed", "pending"})
_TOKEN_PATTERN = re.compile(r"[\w#+.]+", re.UNICODE)
_DEFAULT_OBSERVED_AT = datetime(2026, 8, 28, tzinfo=timezone.utc)
_PSEUDONYM_NAMESPACE = uuid.UUID("dc4009f2-cae3-56ae-9856-83c24d0d58d0")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OutcomeDataset(OutcomeBase):
    """Metadata for a synthetic-only, non-runtime-effect outcome dataset."""

    __tablename__ = "outcome_datasets"
    __table_args__ = (
        CheckConstraint("synthetic = true", name="ck_outcome_dataset_synthetic"),
        CheckConstraint("runtime_effect = 'NONE'", name="ck_outcome_dataset_runtime_none"),
        CheckConstraint("ranking_effect = 'NONE'", name="ck_outcome_dataset_ranking_none"),
        CheckConstraint(
            "approved_for_model_training = false",
            name="ck_outcome_dataset_training_unapproved",
        ),
    )

    dataset_version: Mapped[str] = mapped_column(String(80), primary_key=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    label_semantics: Mapped[str] = mapped_column(Text, nullable=False)
    generation_method: Mapped[str] = mapped_column(String(120), nullable=False)
    source_profile: Mapped[str] = mapped_column(String(120), nullable=False)
    runtime_effect: Mapped[str] = mapped_column(
        String(20), default=NO_EFFECT, nullable=False
    )
    ranking_effect: Mapped[str] = mapped_column(
        String(20), default=NO_EFFECT, nullable=False
    )
    approved_for_model_training: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class SyntheticDocumentOutcome(OutcomeBase):
    """A generated observation containing no source document text or PII."""

    __tablename__ = "synthetic_document_outcomes"
    __table_args__ = (
        UniqueConstraint(
            "dataset_version",
            "application_ref",
            name="uq_synthetic_outcome_dataset_application",
        ),
        CheckConstraint(
            "document_result IN ('passed', 'not_passed', 'pending')",
            name="ck_synthetic_outcome_result",
        ),
        CheckConstraint(
            "result_source = 'synthetic_rule_v1'",
            name="ck_synthetic_outcome_source",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_version: Mapped[str] = mapped_column(
        ForeignKey("outcome_datasets.dataset_version"), index=True, nullable=False
    )
    application_ref: Mapped[str] = mapped_column(String(80), nullable=False)
    candidate_ref: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    job_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    company_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    feature_snapshot: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False)
    evidence_tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    document_result: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    result_source: Mapped[str] = mapped_column(
        String(40), default=RESULT_SOURCE, nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    @validates("feature_snapshot")
    def _validate_feature_snapshot(
        self, _key: str, value: Mapping[str, object]
    ) -> dict[str, float]:
        if not isinstance(value, Mapping) or set(value) != set(FEATURE_ALLOWLIST):
            raise ValueError("feature_snapshot must use the exact numeric allowlist")
        validated: dict[str, float] = {}
        for name in FEATURE_ALLOWLIST:
            raw = value[name]
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ValueError("feature_snapshot values must be numeric")
            numeric = float(raw)
            if not 0.0 <= numeric <= 1.0:
                raise ValueError("feature_snapshot values must be within 0..1")
            validated[name] = round(numeric, 6)
        return validated

    @validates("evidence_tags")
    def _validate_evidence_tags(
        self, _key: str, value: Sequence[object]
    ) -> list[str]:
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise ValueError("evidence_tags must be a list of controlled terms")
        tags: list[str] = []
        for raw in value:
            if not isinstance(raw, str):
                raise ValueError("evidence_tags must contain strings only")
            tag = raw.strip()
            if not tag or len(tag) > 120 or "@" in tag:
                raise ValueError("evidence_tags contains an unsafe term")
            if tag not in tags:
                tags.append(tag)
        return tags

    @validates("document_result")
    def _validate_document_result(self, _key: str, value: str) -> str:
        if value not in DOCUMENT_RESULTS:
            raise ValueError("document_result is outside the generated-label contract")
        return value

    @validates("candidate_ref")
    def _validate_candidate_ref(self, _key: str, value: str) -> str:
        if not re.fullmatch(r"syn-candidate-[0-9a-f]{24}", value):
            raise ValueError("candidate_ref must be a bounded pseudonymous reference")
        return value


def _value(record: object, name: str, default: object = None) -> object:
    if isinstance(record, Mapping):
        return record.get(name, default)
    return getattr(record, name, default)


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, Iterable) or isinstance(value, (bytes, Mapping)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _project_documents(value: object) -> list[str]:
    """Flatten only the reviewed project fields; ignore arbitrary mapping keys."""

    documents: list[str] = []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return documents
    for project in value:
        if not isinstance(project, Mapping):
            continue
        for field in ("title", "role", "summary", "outcome"):
            text_value = project.get(field)
            if isinstance(text_value, str) and text_value.strip():
                documents.append(text_value.strip())
        documents.extend(_string_list(project.get("technologies", [])))
    return documents


def _tokens(value: object) -> set[str]:
    return {
        token.casefold()
        for token in _TOKEN_PATTERN.findall(str(value or ""))
        if token.strip("_.")
    }


def _list_tokens(values: Iterable[object]) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        tokens.update(_tokens(value))
    return tokens


def _coverage(observed: set[str], target: set[str]) -> float:
    if not target:
        return 0.0
    return len(observed.intersection(target)) / len(target)


def _normalised_skill(value: object) -> str:
    return "".join(
        character
        for character in str(value).casefold()
        if character.isalnum() or character in "+#."
    )


def _stable_ref(kind: str, raw_identifier: object) -> str:
    digest = hashlib.sha256(
        f"{DATASET_VERSION}/{kind}/{raw_identifier}".encode("utf-8")
    ).hexdigest()
    return f"syn-{kind}-{digest[:24]}"


def _stable_id(application_ref: str) -> str:
    return str(
        uuid.uuid5(
            _PSEUDONYM_NAMESPACE,
            f"{DATASET_VERSION}/{application_ref}",
        )
    )


def _as_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return _DEFAULT_OBSERVED_AT
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return _DEFAULT_OBSERVED_AT


def _company_fields(job: object) -> tuple[str, list[str]]:
    company = _value(job, "company")
    direction = _value(job, "direction_statement", "")
    declared = _value(job, "declared_values", [])
    if company is not None:
        direction = _value(company, "direction_statement", direction)
        declared = _value(company, "declared_values", declared)
    return str(direction or ""), _string_list(declared)


def _feature_values(resume: object, job: object) -> dict[str, float]:
    candidate_skills = {
        normalised
        for normalised in (
            _normalised_skill(value) for value in _string_list(_value(resume, "skills", []))
        )
        if normalised
    }
    required_skills = {
        normalised
        for normalised in (
            _normalised_skill(value)
            for value in _string_list(_value(job, "required_skills", []))
        )
        if normalised
    }
    skill_overlap = _coverage(candidate_skills, required_skills)

    minimum_experience = max(0, int(_value(job, "min_experience", 0) or 0))
    years_experience = max(0, int(_value(resume, "years_experience", 0) or 0))
    experience_fit = (
        1.0
        if minimum_experience == 0
        else min(1.0, years_experience / minimum_experience)
    )

    desired_role_tokens = _tokens(_value(resume, "desired_role", ""))
    job_title_tokens = _tokens(_value(job, "title", ""))
    role_overlap = _coverage(desired_role_tokens, job_title_tokens)

    self_intro = str(_value(resume, "self_intro", "") or "")
    projects = _project_documents(_value(resume, "projects", []))
    document_tokens = _tokens(self_intro) | _list_tokens(projects)
    job_tokens = (
        job_title_tokens
        | _tokens(_value(job, "summary", ""))
        | _list_tokens(_string_list(_value(job, "required_skills", [])))
    )
    direction, declared_values = _company_fields(job)
    company_tokens = _tokens(direction) | _list_tokens(declared_values)
    values = {
        "skill_overlap": skill_overlap,
        "experience_fit": experience_fit,
        "role_overlap": role_overlap,
        "self_intro_job_overlap": _coverage(document_tokens, job_tokens),
        "company_direction_overlap": _coverage(document_tokens, company_tokens),
    }
    return {name: round(max(0.0, min(1.0, values[name])), 6) for name in FEATURE_ALLOWLIST}


def _literal_evidence_tags(resume: object, job: object) -> list[str]:
    direction, declared_values = _company_fields(job)
    del direction  # Direction text is context, not a controlled evidence vocabulary.
    controlled = _string_list(_value(job, "required_skills", [])) + declared_values
    candidate_skills = {
        _normalised_skill(value)
        for value in _string_list(_value(resume, "skills", []))
        if _normalised_skill(value)
    }
    document_text = "\n".join(
        [str(_value(resume, "self_intro", "") or "")]
        + _project_documents(_value(resume, "projects", []))
    ).casefold()
    observed: list[str] = []
    seen: set[str] = set()
    for raw in controlled:
        term = raw.strip()
        folded = term.casefold()
        if not term or folded in seen:
            continue
        literal_in_skills = _normalised_skill(term) in candidate_skills
        literal_in_documents = folded in document_text
        if literal_in_skills or literal_in_documents:
            observed.append(term)
            seen.add(folded)
    return observed


def _rule_score(features: Mapping[str, float]) -> float:
    return (
        0.35 * features["skill_overlap"]
        + 0.20 * features["experience_fit"]
        + 0.15 * features["role_overlap"]
        + 0.15 * features["self_intro_job_overlap"]
        + 0.15 * features["company_direction_overlap"]
    )


def _generated_result(application_ref: str, features: Mapping[str, float]) -> str:
    bucket = int(
        hashlib.sha256(
            f"{GENERATION_METHOD}/{application_ref}".encode("utf-8")
        ).hexdigest()[:8],
        16,
    ) % 100
    score = _rule_score(features)
    if bucket < 8:
        return "pending"
    if score >= 0.46 or (score >= 0.26 and bucket < 54):
        return "passed"
    return "not_passed"


def _ensure_binary_examples(drafts: list[dict[str, Any]]) -> None:
    """Ensure both generated binary labels when at least two inputs exist."""

    if len(drafts) < 2:
        return
    if not any(draft["document_result"] == "passed" for draft in drafts):
        winner = max(
            drafts,
            key=lambda draft: (
                _rule_score(draft["feature_snapshot"]),
                draft["application_ref"],
            ),
        )
        winner["document_result"] = "passed"
    if not any(draft["document_result"] == "not_passed" for draft in drafts):
        eligible = [draft for draft in drafts if draft["document_result"] != "passed"]
        if not eligible:
            passed = sorted(
                drafts,
                key=lambda draft: (
                    _rule_score(draft["feature_snapshot"]),
                    draft["application_ref"],
                ),
            )
            eligible = passed[:-1] or passed[:1]
        loser = min(
            eligible,
            key=lambda draft: (
                _rule_score(draft["feature_snapshot"]),
                draft["application_ref"],
            ),
        )
        loser["document_result"] = "not_passed"


def _mapping_item(values: Mapping[object, object], key: object) -> object | None:
    if key in values:
        return values[key]
    string_key = str(key)
    if string_key in values:
        return values[string_key]
    return None


def _session_instance(
    session: Session, model: type[Any], primary_key: object
) -> object | None:
    current = session.get(model, primary_key)
    if current is not None:
        return current
    for pending in session.new:
        if isinstance(pending, model):
            identity_name = (
                "dataset_version" if model is OutcomeDataset else "id"
            )
            if getattr(pending, identity_name) == primary_key:
                return pending
    return None


def _datetime_key(value: object) -> str:
    return _as_datetime(value).astimezone(timezone.utc).isoformat()


def seed_synthetic_outcome_dataset(
    session: Session,
    applications: Iterable[object],
    resumes_by_candidate: Mapping[object, object],
    jobs_by_id: Mapping[object, object],
) -> dict[str, object]:
    """Idempotently seed generated observations without committing the session."""

    dataset = _session_instance(session, OutcomeDataset, DATASET_VERSION)
    if dataset is None:
        dataset = OutcomeDataset(
            dataset_version=DATASET_VERSION,
            synthetic=True,
            label_semantics=LABEL_SEMANTICS,
            generation_method=GENERATION_METHOD,
            source_profile=SOURCE_PROFILE,
            runtime_effect=NO_EFFECT,
            ranking_effect=NO_EFFECT,
            approved_for_model_training=False,
            created_at=_DEFAULT_OBSERVED_AT,
        )
        session.add(dataset)
    else:
        expected = {
            "synthetic": True,
            "label_semantics": LABEL_SEMANTICS,
            "generation_method": GENERATION_METHOD,
            "source_profile": SOURCE_PROFILE,
            "runtime_effect": NO_EFFECT,
            "ranking_effect": NO_EFFECT,
            "approved_for_model_training": False,
        }
        if any(getattr(dataset, key) != value for key, value in expected.items()):
            raise ValueError("existing synthetic outcome dataset contract has drifted")

    drafts: list[dict[str, Any]] = []
    ordered_applications = sorted(
        applications,
        key=lambda application: str(_value(application, "id", "")),
    )
    for application in ordered_applications:
        application_id = str(_value(application, "id", "") or "")
        candidate_id = _value(application, "candidate_id")
        job_id_value = _value(application, "job_id")
        if not application_id or candidate_id is None or job_id_value is None:
            continue
        resume = _mapping_item(resumes_by_candidate, candidate_id)
        job = _mapping_item(jobs_by_id, job_id_value)
        if resume is None or job is None:
            continue
        company_id = str(_value(job, "company_id", "") or "")
        job_id = str(job_id_value)
        if not company_id or not job_id:
            continue
        application_ref = _stable_ref("application", application_id)
        features = _feature_values(resume, job)
        observed_at = _as_datetime(
            _value(application, "updated_at")
            or _value(application, "applied_at")
            or _DEFAULT_OBSERVED_AT
        )
        drafts.append(
            {
                "id": _stable_id(application_ref),
                "dataset_version": DATASET_VERSION,
                "application_ref": application_ref,
                "candidate_ref": _stable_ref("candidate", candidate_id),
                "job_id": job_id,
                "company_id": company_id,
                "feature_schema_version": FEATURE_SCHEMA_VERSION,
                "feature_snapshot": features,
                "evidence_tags": _literal_evidence_tags(resume, job),
                "document_result": _generated_result(application_ref, features),
                "result_source": RESULT_SOURCE,
                "observed_at": observed_at,
                "created_at": observed_at,
            }
        )

    drafts_by_job: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for draft in drafts:
        drafts_by_job.setdefault(
            (str(draft["company_id"]), str(draft["job_id"])), []
        ).append(draft)
    for scoped_drafts in drafts_by_job.values():
        _ensure_binary_examples(scoped_drafts)
    created = 0
    existing = 0
    for draft in drafts:
        current = _session_instance(session, SyntheticDocumentOutcome, draft["id"])
        if current is None:
            session.add(SyntheticDocumentOutcome(**draft))
            created += 1
            continue
        immutable_fields = (
            "dataset_version",
            "application_ref",
            "candidate_ref",
            "job_id",
            "company_id",
            "feature_schema_version",
            "feature_snapshot",
            "evidence_tags",
            "document_result",
            "result_source",
            "observed_at",
        )
        drifted = any(
            (
                _datetime_key(getattr(current, name))
                != _datetime_key(draft[name])
                if name == "observed_at"
                else getattr(current, name) != draft[name]
            )
            for name in immutable_fields
        )
        if drifted:
            raise ValueError("existing synthetic document outcome has deterministic drift")
        existing += 1

    return {
        "dataset_version": DATASET_VERSION,
        "synthetic": True,
        "generated_label_semantics": LABEL_SEMANTICS,
        "created_count": created,
        "existing_count": existing,
        "eligible_observation_count": len(drafts),
        "binary_examples_present": (
            any(draft["document_result"] == "passed" for draft in drafts)
            and any(draft["document_result"] == "not_passed" for draft in drafts)
        ),
        "runtime_effect": NO_EFFECT,
        "ranking_effect": NO_EFFECT,
        "model_effect": NO_EFFECT,
        "approved_for_model_training": False,
        "human_review_required": True,
    }


def _candidate_tags(candidate_features_or_tags: object) -> set[str]:
    values: list[str] = []
    if isinstance(candidate_features_or_tags, Mapping):
        for key in ("evidence_tags", "matched_evidence_tags", "skills"):
            values.extend(_string_list(candidate_features_or_tags.get(key, [])))
    else:
        values.extend(_string_list(candidate_features_or_tags))
    return {value.casefold() for value in values if value.strip()}


def _count_band(count: int) -> str:
    if count < 5:
        return "LT_5"
    if count < 10:
        return "5_TO_9"
    if count < 25:
        return "10_TO_24"
    if count < 50:
        return "25_TO_49"
    return "50_PLUS"


def outcome_observation_revision(session: Session) -> str:
    """Hash the non-source-text material used by the active synthetic dataset.

    The revision contains no source text or direct identifier. It exists only to
    partition recommendation caches when a restarted demo seeds additional
    observations under the same reviewed dataset contract.
    """

    rows = session.scalars(
        select(SyntheticDocumentOutcome)
        .where(SyntheticDocumentOutcome.dataset_version == DATASET_VERSION)
        .order_by(SyntheticDocumentOutcome.id)
    ).all()
    material = json.dumps(
        {
            "dataset_version": DATASET_VERSION,
            "rows": [
                {
                    "id": row.id,
                    "feature_schema_version": row.feature_schema_version,
                    "feature_snapshot": row.feature_snapshot,
                    "evidence_tags": row.evidence_tags,
                    "document_result": row.document_result,
                    "result_source": row.result_source,
                    "observed_at": _datetime_key(row.observed_at),
                }
                for row in rows
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def candidate_historical_observation(
    session: Session,
    company_id: str,
    job_id: str,
    candidate_features_or_tags: object,
) -> dict[str, object]:
    """Return a tenant/job-scoped synthetic observation, never a prediction."""

    if not str(company_id).strip() or not str(job_id).strip():
        raise ValueError("company_id and job_id are required for an exact scope")
    rows = list(
        session.scalars(
            select(SyntheticDocumentOutcome).where(
                SyntheticDocumentOutcome.dataset_version == DATASET_VERSION,
                SyntheticDocumentOutcome.company_id == str(company_id),
                SyntheticDocumentOutcome.job_id == str(job_id),
            )
        )
    )
    count = len(rows)
    candidate_tags = _candidate_tags(candidate_features_or_tags)
    passed_rows = [row for row in rows if row.document_result == "passed"]
    not_passed_rows = [row for row in rows if row.document_result == "not_passed"]
    pending_rows = [row for row in rows if row.document_result == "pending"]
    cohort_vocabulary: dict[str, str] = {}
    for row in passed_rows:
        for tag in row.evidence_tags or []:
            if isinstance(tag, str) and tag.strip():
                cohort_vocabulary.setdefault(tag.casefold(), tag)
    shared_tags = [
        cohort_vocabulary[key]
        for key in sorted(candidate_tags.intersection(cohort_vocabulary))[:5]
    ]
    state = "AVAILABLE_SYNTHETIC_DEMO_ONLY"
    if count < 5 or not passed_rows or not not_passed_rows:
        state = "INSUFFICIENT_SYNTHETIC_COHORT"
    return {
        "state": state,
        "dataset_version": DATASET_VERSION,
        "scope": {"company_id": str(company_id), "job_id": str(job_id)},
        "cross_tenant_pooling": False,
        "sample_count_bands": {
            "total": _count_band(count),
            "passed": _count_band(len(passed_rows)),
            "not_passed": _count_band(len(not_passed_rows)),
            "pending": _count_band(len(pending_rows)),
        },
        "shared_evidence_tags": (
            shared_tags if state == "AVAILABLE_SYNTHETIC_DEMO_ONLY" else []
        ),
        "shared_evidence_basis": "observed_in_synthetic_passed_records_not_predictive",
        "label_semantics": LABEL_SEMANTICS,
        "generation_method": GENERATION_METHOD,
        "approved_for_model_training": False,
        "runtime_effect": NO_EFFECT,
        "ranking_effect": NO_EFFECT,
        "model_effect": NO_EFFECT,
        "is_hiring_probability": False,
        "is_causal": False,
        "synthetic_demo_only": True,
        "human_review_required": True,
        "limitations": [
            "synthetic observations are not production evidence",
            "the generated document result is not candidate quality or a hiring decision",
            "descriptive overlap is non-causal and can be gamed",
            "historical or generated labels can encode rule artifacts",
        ],
    }
