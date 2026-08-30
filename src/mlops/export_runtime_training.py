#!/usr/bin/env python3
"""Export a feature-only training dataset from the synthetic runtime databases.

The exporter reads the full synthetic candidate and company records so that the
lineage receipt covers the real runtime path. Direct identifiers and free-text
source values are never written to the dataset or receipt.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from generate_synthetic_training import safe_output_directory, stable_split, write_artifact


SCHEMA_VERSION = "jcareer-synthetic-runtime-ranking-dataset-v1"
RECEIPT_SCHEMA_VERSION = "jcareer-synthetic-runtime-source-read-receipt-v1"
SYNTHETIC_ATTESTATION = "JCAREER_SYNTHETIC_ONLY"
TRAINING_FEATURES = [
    "skill_overlap",
    "experience_fit",
    "role_overlap",
    "self_intro_job_overlap",
    "company_direction_overlap",
]
LABEL_NAME = "pipeline_progression_proxy"
FIELDNAMES = [
    "candidate_ref",
    "job_ref",
    "company_ref",
    *TRAINING_FEATURES,
    LABEL_NAME,
    "evaluation_group",
    "split",
]
POSITIVE_STATUSES = {"reviewing", "interview", "offered"}
NEGATIVE_STATUSES = {"rejected"}
EXCLUDED_UNRESOLVED_STATUSES = {"applied"}
TOKEN_PATTERN = re.compile(r"[0-9a-zA-Z가-힣+#.]+")
MEMBER_SOURCE_FIELDS = [
    "user.id",
    "user.email",
    "user.display_name",
    "user.role",
    "user.active",
    "user.withdrawn_at",
    "resume.phone",
    "resume.birth_date",
    "resume.address_region",
    "resume.education",
    "resume.desired_role",
    "resume.years_experience",
    "resume.skills",
    "resume.certificates",
    "resume.self_intro",
    "application.id",
    "application.job_id",
    "application.status",
    "application.applied_at",
    "application.updated_at",
    "consent_event.id",
    "consent_event.consent_type",
    "consent_event.action",
    "consent_event.policy_version",
    "consent_event.collected_items",
    "consent_event.purposes",
    "consent_event.legal_basis",
    "consent_event.occurred_at",
]
COMPANY_SOURCE_FIELDS = [
    "company.id",
    "company.name",
    "company.direction_statement",
    "company.declared_values",
    "company.profile_version",
    "company.status",
    "job.id",
    "job.company_id",
    "job.title",
    "job.summary",
    "job.required_skills",
    "job.min_experience",
    "job.status",
]
DIRECT_OR_FREE_TEXT_FIELDS_NOT_PERSISTED = [
    "name",
    "email",
    "phone",
    "birth_date",
    "address_region",
    "education",
    "certificates",
    "self_intro_raw",
    "company_name",
    "company_direction_statement_raw",
    "job_summary_raw",
]


def _json_value(value: object, default: object) -> object:
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return default
        return parsed if isinstance(parsed, type(default)) else default
    return default


def _serialisable(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _serialisable(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_serialisable(item) for item in value]
    return value


def _canonical_hash(value: object) -> str:
    content = json.dumps(
        _serialisable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _stable_ref(kind: str, raw_identifier: object) -> str:
    digest = hashlib.sha256(f"jcareer-runtime/{kind}/{raw_identifier}".encode("utf-8")).hexdigest()
    return f"syn-{kind}-db-{digest[:20]}"


def _database_target(database_url: str) -> tuple[object, ...]:
    parsed = make_url(database_url)
    if parsed.get_backend_name() == "sqlite":
        database = parsed.database or ":memory:"
        if database != ":memory:":
            database = str(Path(database).expanduser().resolve())
        return ("sqlite", database)
    return (
        parsed.get_backend_name(),
        (parsed.host or "").casefold(),
        parsed.port,
        parsed.database or "",
    )


def _tokens(value: object) -> set[str]:
    return {
        token.casefold()
        for token in TOKEN_PATTERN.findall(str(value))
        if len(token) > 1 or token.isdigit()
    }


def _list_tokens(values: Iterable[object]) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        tokens.update(_tokens(value))
    return tokens


def _coverage(left: set[str], right: set[str]) -> float:
    if not right:
        return 0.0
    return len(left.intersection(right)) / len(right)


def _normalised_skill(value: object) -> str:
    return "".join(character for character in str(value).casefold() if character.isalnum() or character in "+#")


def _feature_values(member: dict[str, object], job: dict[str, object]) -> dict[str, float]:
    candidate_skills = {
        _normalised_skill(value)
        for value in member["skills"]
        if _normalised_skill(value)
    }
    required_skills = {
        _normalised_skill(value)
        for value in job["required_skills"]
        if _normalised_skill(value)
    }
    skill_overlap = _coverage(candidate_skills, required_skills)
    minimum_experience = max(0, int(job["min_experience"] or 0))
    years_experience = max(0, int(member["years_experience"] or 0))
    experience_fit = 1.0 if minimum_experience == 0 else min(1.0, years_experience / minimum_experience)

    desired_role_tokens = _tokens(member["desired_role"])
    job_title_tokens = _tokens(job["title"])
    role_overlap = _coverage(desired_role_tokens, job_title_tokens)

    intro_tokens = _tokens(member["self_intro"])
    job_tokens = _tokens(job["title"]) | _tokens(job["summary"]) | _list_tokens(job["required_skills"])
    direction_tokens = _tokens(job["direction_statement"]) | _list_tokens(job["declared_values"])
    return {
        "skill_overlap": skill_overlap,
        "experience_fit": experience_fit,
        "role_overlap": role_overlap,
        "self_intro_job_overlap": _coverage(intro_tokens, job_tokens),
        "company_direction_overlap": _coverage(intro_tokens, direction_tokens),
    }


def _fetch_rows(database_url: str, statement: str) -> list[dict[str, object]]:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            return [dict(row) for row in connection.execute(text(statement)).mappings().all()]
    finally:
        engine.dispose()


def _read_member_source(database_url: str) -> tuple[dict[str, dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    raw_members = _fetch_rows(
        database_url,
        """
        SELECT u.id, u.email, u.display_name, u.role, u.active, u.withdrawn_at,
               r.phone, r.birth_date, r.address_region, r.education,
               r.desired_role, r.years_experience, r.skills, r.certificates,
               r.self_intro
          FROM users u
          JOIN resumes r ON r.user_id = u.id
         WHERE u.role = 'candidate'
        """,
    )
    applications = _fetch_rows(
        database_url,
        """
        SELECT id, job_id, candidate_id, status, applied_at, updated_at
          FROM applications
        """,
    )
    consents = _fetch_rows(
        database_url,
        """
        SELECT id, user_id, consent_type, action, policy_version, collected_items,
               purposes, legal_basis, occurred_at
          FROM consent_events
         WHERE consent_type = 'privacy_core'
        """,
    )
    latest_consent: dict[str, dict[str, object]] = {}
    for consent in sorted(
        consents,
        key=lambda item: (
            str(item.get("occurred_at") or ""),
            str(item.get("id") or ""),
        ),
    ):
        latest_consent[str(consent["user_id"])] = consent

    members: dict[str, dict[str, object]] = {}
    for raw in raw_members:
        member = dict(raw)
        member["skills"] = list(_json_value(member.get("skills"), []))
        member["certificates"] = list(_json_value(member.get("certificates"), []))
        member["latest_privacy_core_action"] = (
            latest_consent.get(str(member["id"]), {}).get("action")
        )
        members[str(member["id"])] = member
    return members, applications, consents


def _read_company_source(database_url: str) -> tuple[dict[str, dict[str, object]], list[dict[str, object]]]:
    raw_jobs = _fetch_rows(
        database_url,
        """
        SELECT j.id, j.company_id, j.title, j.summary, j.required_skills,
               j.min_experience, j.status AS job_status,
               c.name AS company_name, c.direction_statement, c.declared_values,
               c.profile_version, c.status AS company_status
          FROM jobs j
          JOIN companies c ON c.id = j.company_id
        """,
    )
    jobs: dict[str, dict[str, object]] = {}
    for raw in raw_jobs:
        job = dict(raw)
        job["required_skills"] = list(_json_value(job.get("required_skills"), []))
        job["declared_values"] = list(_json_value(job.get("declared_values"), []))
        jobs[str(job["id"])] = job
    return jobs, raw_jobs


def _assert_synthetic_member(member: dict[str, object]) -> None:
    email = str(member.get("email") or "").casefold()
    phone = re.sub(r"\s+", "", str(member.get("phone") or ""))
    if not (email.endswith("@example.invalid") or email.endswith("@jcareer.test")):
        raise ValueError("synthetic source check rejected a candidate email domain")
    if phone and not phone.startswith("010-0000-"):
        raise ValueError("synthetic source check rejected a candidate phone marker")


def _csv_bytes(rows: list[dict[str, object]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDNAMES, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def export_runtime_dataset(
    *,
    member_database_url: str,
    company_database_url: str,
    output_directory: Path,
    synthetic_attestation: str,
    overwrite: bool = False,
) -> dict[str, Path]:
    if synthetic_attestation != SYNTHETIC_ATTESTATION:
        raise ValueError("synthetic runtime attestation is required")
    if _database_target(member_database_url) == _database_target(company_database_url):
        raise ValueError("member and company database URLs must be different")

    members, applications, consents = _read_member_source(member_database_url)
    jobs, raw_jobs = _read_company_source(company_database_url)
    if not members or not applications or not jobs:
        raise ValueError("synthetic runtime sources must contain members, applications, and jobs")

    rows: list[dict[str, object]] = []
    excluded_status_counts: dict[str, int] = {}
    dangling_reference_counts = {"member_missing": 0, "job_missing": 0}
    eligible_candidate_ids: set[str] = set()
    company_ids: set[str] = set()
    for application in sorted(applications, key=lambda item: str(item["id"])):
        member = members.get(str(application["candidate_id"]))
        job = jobs.get(str(application["job_id"]))
        if member is None:
            dangling_reference_counts["member_missing"] += 1
            continue
        if job is None:
            dangling_reference_counts["job_missing"] += 1
            continue
        if not bool(member.get("active")) or member.get("withdrawn_at") is not None:
            continue
        if member.get("latest_privacy_core_action") != "grant":
            continue
        _assert_synthetic_member(member)
        status = str(application.get("status") or "")
        if status in POSITIVE_STATUSES:
            label = 1
        elif status in NEGATIVE_STATUSES:
            label = 0
        else:
            excluded_status_counts[status or "EMPTY"] = excluded_status_counts.get(status or "EMPTY", 0) + 1
            continue
        candidate_ref = _stable_ref("candidate", member["id"])
        job_ref = _stable_ref("job", job["id"])
        company_ref = _stable_ref("company", job["company_id"])
        feature_values = _feature_values(member, job)
        evaluation_group = (
            "synthetic-cohort-a"
            if int(hashlib.sha256(candidate_ref.encode("utf-8")).hexdigest(), 16) % 2
            else "synthetic-cohort-b"
        )
        rows.append(
            {
                "candidate_ref": candidate_ref,
                "job_ref": job_ref,
                "company_ref": company_ref,
                **{name: f"{feature_values[name]:.6f}" for name in TRAINING_FEATURES},
                LABEL_NAME: label,
                "evaluation_group": evaluation_group,
                "split": stable_split(candidate_ref),
            }
        )
        eligible_candidate_ids.add(str(member["id"]))
        company_ids.add(str(job["company_id"]))

    if not rows:
        raise ValueError("no resolved synthetic application rows are available")
    if not any(row["split"] == "train" for row in rows) or not any(row["split"] == "test" for row in rows):
        raise ValueError("resolved synthetic applications must cover train and test candidates")
    if {int(row[LABEL_NAME]) for row in rows} != {0, 1}:
        raise ValueError("resolved synthetic applications must contain both proxy label values")

    source_material = {
        "members": [members[key] for key in sorted(members)],
        "applications": sorted(applications, key=lambda item: str(item["id"])),
        "consents": sorted(consents, key=lambda item: str(item["id"])),
        "jobs_and_companies": sorted(raw_jobs, key=lambda item: str(item["id"])),
    }
    source_digest = _canonical_hash(source_material)
    dataset_content = _csv_bytes(rows)
    dataset_sha256 = hashlib.sha256(dataset_content).hexdigest()
    dataset_path = output_directory / "ranking_dataset.csv"
    manifest_path = output_directory / "dataset_manifest.json"
    receipt_path = output_directory / "source_read_receipt.json"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "synthetic_only": True,
        "synthetic_attestation": SYNTHETIC_ATTESTATION,
        "member_data_used": True,
        "company_customer_data_used": True,
        "purpose": "synthetic_runtime_challenger_training_demonstration",
        "source_runtime_db_wired": True,
        "ranking_runtime_wired": False,
        "runtime_wired": False,
        "row_count": len(rows),
        "candidate_count": len(eligible_candidate_ids),
        "company_count": len(company_ids),
        "dataset_file": dataset_path.name,
        "dataset_sha256": dataset_sha256,
        "source_receipt_file": receipt_path.name,
        "source_digest": source_digest,
        "field_roles": {
            "training_features": TRAINING_FEATURES,
            "label": LABEL_NAME,
            "evaluation_only": ["evaluation_group"],
            "logical_identifiers_not_features": ["candidate_ref", "job_ref", "company_ref"],
            "split": "split",
        },
        "label_semantics": "historical_pipeline_progression_proxy_not_candidate_quality_or_hiring_probability",
        "excluded_unresolved_status_counts": excluded_status_counts,
        "dangling_reference_counts": dangling_reference_counts,
        "direct_or_free_text_fields_not_persisted": DIRECT_OR_FREE_TEXT_FIELDS_NOT_PERSISTED,
        "human_decision_required_before_runtime_use": True,
    }
    receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "synthetic_only": True,
        "synthetic_attestation": SYNTHETIC_ATTESTATION,
        "source_runtime_db_wired": True,
        "member_source_fields_read": MEMBER_SOURCE_FIELDS,
        "company_source_fields_read": COMPANY_SOURCE_FIELDS,
        "source_record_counts": {
            "candidate_resume_records": len(members),
            "application_records": len(applications),
            "privacy_core_events": len(consents),
            "job_company_records": len(raw_jobs),
            "exported_resolved_rows": len(rows),
        },
        "dangling_reference_counts": dangling_reference_counts,
        "source_digest": source_digest,
        "raw_source_values_persisted": False,
        "name_and_email_role": "lineage_digest_input_only_not_model_features",
        "self_intro_role": "read_then_derived_to_overlap_features_raw_text_not_persisted",
        "privacy_core_role": "synthetic_lifecycle_filter_not_model_training_consent",
        "training_feature_allowlist": TRAINING_FEATURES,
        "limitations": [
            "application status is a proxy and can reproduce historical recruiter behavior",
            "synthetic runtime data does not establish production model quality",
            "no automatic release, compliance conclusion, or fairness conclusion is produced",
        ],
        "human_interpretation_required": True,
    }
    write_artifact(dataset_path, dataset_content, overwrite)
    write_artifact(
        manifest_path,
        (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        overwrite,
    )
    write_artifact(
        receipt_path,
        (json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        overwrite,
    )
    return {"dataset": dataset_path, "manifest": manifest_path, "receipt": receipt_path}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--member-database-url", required=True)
    parser.add_argument("--company-database-url", required=True)
    parser.add_argument("--synthetic-attestation", required=True)
    parser.add_argument("--out-dir", default="measurement/out/mlops-runtime")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_directory = safe_output_directory(args.out_dir)
    paths = export_runtime_dataset(
        member_database_url=args.member_database_url,
        company_database_url=args.company_database_url,
        output_directory=output_directory,
        synthetic_attestation=args.synthetic_attestation,
        overwrite=args.overwrite,
    )
    print(f"RUNTIME_DATASET=CREATED manifest={paths['manifest'].name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
