"""Pure qualitative-evidence construction for candidate/job decision support.

This module only records directly verifiable text overlap.  It deliberately
does not calculate a score, infer semantic similarity, assess candidate fit or
quality, or make a hiring recommendation.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any


CONTRACT_VERSION = "candidate-qualitative-evidence-v1"
METHOD = "literal-source-span-v1"
MAX_CLAIMS = 8
PROJECT_TEXT_FIELDS = ("title", "role", "summary", "outcome")
SENSITIVE_TERM_PATTERN = re.compile(
    r"(?:"
    r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"
    r"|(?:01[016789])[- .]?\d{3,4}[- .]?\d{4}"
    r"|\d{6}[- ]?[1-4]\d{6}"
    r"|(?:19|20)\d{2}[-./]\d{1,2}[-./]\d{1,2}"
    r"|(?:이름|성명|생년|주민등록|전화|연락처|이메일|주소|학교|대학교|고등학교)"
    r")",
    re.IGNORECASE,
)


def _text(value: object) -> str:
    """Return a string value without coercing arbitrary objects."""

    return value if isinstance(value, str) else ""


def _sequence(value: object) -> Sequence[object]:
    """Return a non-string sequence or an empty immutable sequence."""

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _safe_employer_terms(values: object) -> list[tuple[int, str]]:
    """Deduplicate allowed employer terms and reject obvious PII-like terms."""

    terms: list[tuple[int, str]] = []
    seen: set[str] = set()
    for index, value in enumerate(_sequence(values)):
        term = _text(value).strip()
        canonical = term.casefold()
        if (
            not term
            or len(term) > 120
            or canonical in seen
            or SENSITIVE_TERM_PATTERN.search(term) is not None
        ):
            continue
        seen.add(canonical)
        terms.append((index, term))
    return terms


def _literal_span(source: str, term: str) -> tuple[int, int] | None:
    """Find one case-insensitive literal occurrence with conservative boundaries."""

    if not source or not term:
        return None
    escaped = re.escape(term)
    prefix = r"(?<!\w)" if term[0].isalnum() else ""
    suffix = r"(?!\w)" if term[-1].isalnum() else ""
    match = re.search(f"{prefix}{escaped}{suffix}", source, flags=re.IGNORECASE)
    return match.span() if match else None


def _employer_source(
    *,
    term: str,
    term_index: int,
    term_kind: str,
    narrative: str,
) -> dict[str, object]:
    """Prefer a verifiable narrative span, falling back to the structured term."""

    span = _literal_span(narrative, term)
    if span is not None:
        start, end = span
        return {
            "employer_source_type": (
                "JOB_SUMMARY" if term_kind == "required_skill" else "DIRECTION_STATEMENT"
            ),
            "employer_source_ref": (
                "job_summary"
                if term_kind == "required_skill"
                else "direction_statement"
            ),
            "employer_excerpt": narrative[start:end],
            "employer_span_start": start,
            "employer_span_end": end,
        }
    return {
        "employer_source_type": (
            "REQUIRED_SKILL" if term_kind == "required_skill" else "DECLARED_VALUE"
        ),
        "employer_source_ref": f"{term_kind}s[{term_index}]",
        "employer_excerpt": term,
        "employer_span_start": None,
        "employer_span_end": None,
    }


def _claim_id(claim: Mapping[str, object]) -> str:
    """Create a stable content-derived identifier without a secret or raw record ID."""

    identity_fields = {
        key: claim[key]
        for key in (
            "relation_type",
            "matched_term",
            "candidate_source_type",
            "candidate_source_ref",
            "candidate_excerpt",
            "candidate_span_start",
            "candidate_span_end",
            "employer_source_type",
            "employer_source_ref",
            "employer_excerpt",
            "employer_span_start",
            "employer_span_end",
        )
    }
    canonical = json.dumps(
        identity_fields,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"claim-{hashlib.sha256(canonical).hexdigest()[:20]}"


def _make_claim(
    *,
    matched_term: str,
    candidate_source_type: str,
    candidate_source_ref: str,
    candidate_excerpt: str,
    candidate_span: tuple[int, int] | None,
    employer_source: Mapping[str, object],
) -> dict[str, object]:
    """Build one exact-overlap claim with no evaluative interpretation."""

    claim: dict[str, object] = {
        "relation_type": "exact_overlap",
        "matched_term": matched_term,
        "candidate_source_type": candidate_source_type,
        "candidate_source_ref": candidate_source_ref,
        "candidate_excerpt": candidate_excerpt,
        "candidate_span_start": candidate_span[0] if candidate_span else None,
        "candidate_span_end": candidate_span[1] if candidate_span else None,
        **employer_source,
        "support_state": "DIRECT_TEXT_EVIDENCE",
        "score_effect": "NONE",
        "human_review_required": True,
    }
    claim["claim_id"] = _claim_id(claim)
    return {"claim_id": claim.pop("claim_id"), **claim}


def build_qualitative_evidence(
    *,
    self_intro: str,
    projects: Sequence[object],
    job_summary: str,
    required_skills: Sequence[object],
    direction_statement: str,
    declared_values: Sequence[object],
    resume_version: str,
    job_version: str,
    company_profile_version: str,
) -> dict[str, Any]:
    """Build bounded, literal qualitative evidence without scoring or inference.

    Employer-controlled match terms come exclusively from ``required_skills``
    and ``declared_values``. Candidate evidence comes exclusively from
    ``self_intro`` and the allowed project fields. Malformed projects are
    ignored, and no input collection or mapping is mutated.
    """

    candidate_text_sources: list[tuple[str, str, str]] = []
    introduction = _text(self_intro)
    if introduction:
        candidate_text_sources.append(("SELF_INTRO", "self_intro", introduction))

    candidate_technologies: list[tuple[str, str]] = []
    for project_index, project_value in enumerate(_sequence(projects)):
        if not isinstance(project_value, Mapping):
            continue
        project: Mapping[object, object] = project_value
        for field in PROJECT_TEXT_FIELDS:
            source = _text(project.get(field))
            if source:
                candidate_text_sources.append(
                    (
                        f"PROJECT_{field.upper()}",
                        f"projects[{project_index}].{field}",
                        source,
                    )
                )
        for technology_index, technology_value in enumerate(
            _sequence(project.get("technologies"))
        ):
            technology = _text(technology_value).strip()
            if technology and SENSITIVE_TERM_PATTERN.search(technology) is None:
                candidate_technologies.append(
                    (
                        f"projects[{project_index}].technologies[{technology_index}]",
                        technology,
                    )
                )

    employer_terms: list[tuple[int, str, str, str]] = [
        (index, term, "required_skill", _text(job_summary))
        for index, term in _safe_employer_terms(required_skills)
    ] + [
        (index, term, "declared_value", _text(direction_statement))
        for index, term in _safe_employer_terms(declared_values)
    ]

    claims: list[dict[str, object]] = []
    seen_claim_ids: set[str] = set()
    for term_index, term, term_kind, narrative in employer_terms:
        employer_source = _employer_source(
            term=term,
            term_index=term_index,
            term_kind=term_kind,
            narrative=narrative,
        )
        for source_type, source_ref, source in candidate_text_sources:
            span = _literal_span(source, term)
            if span is None:
                continue
            start, end = span
            claim = _make_claim(
                matched_term=term,
                candidate_source_type=source_type,
                candidate_source_ref=source_ref,
                candidate_excerpt=source[start:end],
                candidate_span=span,
                employer_source=employer_source,
            )
            if claim["claim_id"] not in seen_claim_ids:
                seen_claim_ids.add(str(claim["claim_id"]))
                claims.append(claim)
            if len(claims) >= MAX_CLAIMS:
                break
        if len(claims) >= MAX_CLAIMS:
            break

        term_key = term.casefold()
        for source_ref, technology in candidate_technologies:
            if technology.casefold() != term_key:
                continue
            claim = _make_claim(
                matched_term=term,
                candidate_source_type="PROJECT_TECHNOLOGY",
                candidate_source_ref=source_ref,
                candidate_excerpt=technology,
                candidate_span=None,
                employer_source=employer_source,
            )
            if claim["claim_id"] not in seen_claim_ids:
                seen_claim_ids.add(str(claim["claim_id"]))
                claims.append(claim)
            if len(claims) >= MAX_CLAIMS:
                break
        if len(claims) >= MAX_CLAIMS:
            break

    return {
        "contract_version": CONTRACT_VERSION,
        "method": METHOD,
        "state": "AVAILABLE" if claims else "NO_DIRECT_TEXT_EVIDENCE",
        "claims": claims,
        "source_versions": {
            "resume_version": _text(resume_version),
            "job_version": _text(job_version),
            "company_profile_version": _text(company_profile_version),
        },
        "score_effect": "NONE",
        "ranking_effect": "NONE",
        "human_review_required": True,
        "limitations": [
            "token overlap is not semantic similarity",
            "repeated keywords can game literal overlap evidence",
            "experience depth and claim authenticity are not assessed",
        ],
    }
