from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .bedrock_response import parse_bedrock_explanations


logger = logging.getLogger("jcareer.llm_gateway")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

app = FastAPI(
    title="J-Career synthetic LLM gateway",
    version="0.2.0",
    description="Synthetic AS-IS explanation gateway with local stub and optional Bedrock provider.",
)
FAILURE_INJECTION_ENABLED = os.getenv("ENABLE_FAILURE_INJECTION", "false").lower() == "true"
PII_FIELD_NAMES = {"name", "phone", "email", "birthdate", "address", "school"}
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "local-synthetic-stub")
ALLOW_BEDROCK_LIVE = os.getenv("ALLOW_BEDROCK_LIVE", "false").lower() == "true"
BEDROCK_REGION = os.getenv("BEDROCK_REGION", os.getenv("AWS_REGION", "ap-northeast-2"))
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "apac.amazon.nova-lite-v1:0")
EXPLANATION_CONTRACT_VERSION = os.getenv(
    "EXPLANATION_CONTRACT_VERSION", "score-explanation-v1"
)

if LLM_PROVIDER not in {"local-synthetic-stub", "bedrock"}:
    raise RuntimeError("LLM_PROVIDER must be local-synthetic-stub or bedrock")


def _provider_config_metadata() -> dict[str, str]:
    """Describe configured client inputs without asserting provider receipt or processing."""
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


class ScoreFactor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factor_id: Literal["skills", "experience", "role"]
    label: str
    raw_points: float
    display_points: float
    max_points: float
    calculation: str
    evidence: list[str] = Field(default_factory=list)
    details: dict[str, object] = Field(default_factory=dict)


class ScoreBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    formula_version: str
    policy_source: Literal["platform_default"]
    formula: str
    total_points: float
    max_points: float
    configured_priority_factor_id: Literal["skills", "experience", "role"]
    largest_contribution_factor_ids: list[Literal["skills", "experience", "role"]]
    factors: list[ScoreFactor]
    excluded_input_fields: list[str]


class CandidateContext(BaseModel):
    """Bound the AS-IS provider payload without changing which fields it exposes."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=100)
    phone: str = Field(max_length=40)
    email: str = Field(max_length=254)
    birthdate: str = Field(max_length=20)
    address: str = Field(max_length=120)
    school: str = Field(max_length=180)
    certificates: list[str] = Field(default_factory=list, max_length=30)
    self_intro: str = Field(default="", max_length=5000)


class CompanyContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_name: str = Field(max_length=120)
    direction_statement: str = Field(max_length=2000)
    declared_values: list[str] = Field(default_factory=list, max_length=10)
    profile_version: str = Field(max_length=120)
    job_title: str = Field(max_length=180)
    job_summary: str = Field(max_length=5000)


class ExplanationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_ref: str = Field(min_length=1, max_length=128)
    score: float = Field(ge=0, le=100)
    score_breakdown: ScoreBreakdown | None = None
    matched_feature_ids: list[str] = Field(default_factory=list, max_length=64)
    matched_feature_labels: list[str] = Field(default_factory=list, max_length=64)
    candidate_context: CandidateContext
    company_context: CompanyContext


class ExplanationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ExplanationItem] = Field(min_length=1, max_length=20)
    mode: Literal[
        "success",
        "timeout",
        "rate_limit",
        "provider_error",
        "malformed",
        "overclaim",
    ] | None = None
    correlation_id: str | None = Field(default=None, max_length=128)


def _mode(requested: str | None) -> str:
    return requested or os.getenv("LLM_STUB_MODE", "success")


def _prompt_record(item: ExplanationItem) -> tuple[str, list[str], list[str], list[str]]:
    # This deliberately records which structured fields the AS-IS path attempted to send.
    # All runtime fixtures are synthetic; values are not written to the structured log.
    candidate_context = item.candidate_context.model_dump()
    company_context = item.company_context.model_dump()
    prompt_fields = sorted(candidate_context)
    company_fields = sorted(company_context)
    pii_fields = sorted(PII_FIELD_NAMES.intersection(prompt_fields))
    material = json.dumps(
        {
            "subject_ref": item.subject_ref,
            "score": item.score,
            "features": item.matched_feature_labels,
            "score_breakdown": (
                item.score_breakdown.model_dump() if item.score_breakdown else None
            ),
            "candidate_context": candidate_context,
            "company_context": company_context,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return (
        hashlib.sha256(material.encode("utf-8")).hexdigest(),
        pii_fields,
        prompt_fields,
        company_fields,
    )


def _normalise_text(value: object) -> str:
    return "".join(character.lower() for character in str(value) if character.isalnum())


def _company_alignment(item: ExplanationItem) -> dict[str, object]:
    company_context = item.company_context.model_dump()
    candidate_context = item.candidate_context.model_dump()
    direction = str(company_context.get("direction_statement", "")).strip()
    values = [
        str(value).strip()
        for value in company_context.get("declared_values", [])
        if str(value).strip()
    ]
    self_intro = str(candidate_context.get("self_intro", "")).strip()
    if not direction or not values:
        return {
            "state": "COMPANY_PROFILE_UNAVAILABLE",
            "profile_version": company_context.get("profile_version"),
            "direction_statement": direction,
            "declared_values": values,
            "matched_declared_values": [],
            "basis": "company-declared-profile-and-self-introduction",
            "score_effect": "NONE",
            "human_review_required": True,
        }

    normalised_intro = _normalise_text(self_intro)
    matched = [
        value
        for value in values
        if _normalise_text(value) and _normalise_text(value) in normalised_intro
    ]
    return {
        "state": (
            "DIRECT_DECLARED_VALUE_EVIDENCE_FOUND"
            if matched
            else "NO_DIRECT_DECLARED_VALUE_EVIDENCE"
        ),
        "profile_version": company_context.get("profile_version"),
        "direction_statement": direction,
        "declared_values": values,
        "matched_declared_values": matched,
        "basis": "company-declared-profile-and-self-introduction",
        "score_effect": "NONE",
        "human_review_required": True,
    }


def _explanation(item: ExplanationItem) -> str:
    if item.score_breakdown:
        factors = item.score_breakdown.factors
        rendered = ", ".join(
            f"{factor.label} {factor.display_points:g}/{factor.max_points:g}점"
            for factor in factors
        )
        largest = [
            factor.label
            for factor in factors
            if factor.factor_id in item.score_breakdown.largest_contribution_factor_ids
        ]
        alignment = _company_alignment(item)
        matched_values = alignment["matched_declared_values"]
        alignment_text = (
            f" 자소서에서 기업 선언 가치 {', '.join(matched_values)}와 직접 겹치는 표현을 확인했습니다."
            if matched_values
            else " 자소서와 기업 선언 가치 사이의 직접 일치 표현은 확인되지 않았습니다."
        )
        return (
            f"총 {item.score:g}점은 반올림 전 기여도를 합산해 산정했고, "
            f"화면 표시값은 {rendered}입니다. "
            f"이번 결과에서 가장 크게 더해진 항목은 {', '.join(largest)}이며, "
            "설명 생성기는 점수와 순위를 변경하지 않습니다."
            f"{alignment_text}"
        )
    if not item.matched_feature_labels:
        return "구조화된 직무 조건에서 확인된 일치 항목이 아직 없습니다."
    primary = item.matched_feature_labels[:3]
    if len(primary) == 1:
        evidence = primary[0]
    else:
        evidence = ", ".join(primary[:-1]) + f", {primary[-1]}"
    return f"{evidence} 항목을 바탕으로 산출된 추천입니다."


def _bedrock_explanations(items: list[ExplanationItem]) -> dict[str, str]:
    import boto3
    from botocore.config import Config
    from botocore.exceptions import BotoCoreError, ClientError

    prompt_items = [
        {
            "subject_ref": item.subject_ref,
            "score": item.score,
            "score_breakdown": (
                item.score_breakdown.model_dump() if item.score_breakdown else None
            ),
            "matched_feature_labels": item.matched_feature_labels,
            # AS-IS 관찰을 위해 현재 경로가 받는 합성 후보자 필드를 그대로 포함한다.
            # 점수 계산에는 쓰이지 않지만 provider 입력과 raw prompt 기록에는 남는다.
            "candidate_context": item.candidate_context.model_dump(),
            "company_context": item.company_context.model_dump(),
        }
        for item in items
    ]
    system_text = (
        "당신은 채용 점수를 계산하지 않는 한국어 설명 생성기다. "
        "입력의 결정론적 점수와 요인별 기여도를 바꾸거나 새 근거를 만들지 말라. "
        "기업 방향은 company_context의 기업 선언문만 사용하고, 자소서 근거는 candidate_context의 self_intro에서만 찾아라. "
        "각 subject_ref마다 두 문장 이하의 설명만 작성하라. "
        "합격, 탈락, 채용 결정은 내리지 말라. "
        "반드시 JSON 객체 {\"items\":[{\"subject_ref\":\"...\",\"text\":\"...\"}]}만 출력하라."
    )
    client = boto3.client(
        "bedrock-runtime",
        region_name=BEDROCK_REGION,
        config=Config(
            connect_timeout=2,
            read_timeout=12,
            retries={"max_attempts": 1, "mode": "standard"},
        ),
    )
    try:
        response = client.converse(
            modelId=BEDROCK_MODEL_ID,
            system=[{"text": system_text}],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "text": json.dumps(
                                {
                                    "contract_version": EXPLANATION_CONTRACT_VERSION,
                                    "items": prompt_items,
                                },
                                ensure_ascii=False,
                                sort_keys=True,
                            )
                        }
                    ],
                }
            ],
            inferenceConfig={"maxTokens": 1200, "temperature": 0.0, "topP": 0.1},
        )
    except (BotoCoreError, ClientError) as exc:
        raise RuntimeError("Bedrock explanation request failed") from exc

    content = response.get("output", {}).get("message", {}).get("content", [])
    rendered = "".join(
        str(block.get("text", "")) for block in content if isinstance(block, dict)
    ).strip()
    if rendered.startswith("```"):
        rendered = rendered.removeprefix("```json").removeprefix("```")
        rendered = rendered.removesuffix("```").strip()
    expected = {item.subject_ref for item in items}
    try:
        mapped = parse_bedrock_explanations(rendered, expected)
    except ValueError as exc:
        raise RuntimeError("Bedrock explanation response schema is invalid") from exc
    return mapped


@app.get("/llm/health")
@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "llm-gateway",
        "mode": os.getenv("LLM_STUB_MODE", "success"),
        "raw_prompt_log_enabled": str(
            os.getenv("ASIS_RAW_PROMPT_LOG", "true").lower() == "true"
        ).lower(),
        "bedrock_live_enabled": str(LLM_PROVIDER == "bedrock" and ALLOW_BEDROCK_LIVE).lower(),
        **_provider_config_metadata(),
    }


@app.post("/llm/internal/explanations")
@app.post("/internal/explanations")
async def explanations(request: ExplanationRequest) -> dict[str, object]:
    if request.mode and not FAILURE_INJECTION_ENABLED:
        raise HTTPException(status_code=404, detail="synthetic failure injection is disabled")
    prompt_records: dict[str, tuple[str, list[str], list[str], list[str]]] = {}
    provider_config = _provider_config_metadata()
    for item in request.items:
        prompt_hash, pii_fields, prompt_fields, company_fields = _prompt_record(item)
        prompt_records[item.subject_ref] = (
            prompt_hash,
            pii_fields,
            prompt_fields,
            company_fields,
        )
        logger.info(
            "prompt_event=%s",
            json.dumps(
                {
                    "correlation_id": request.correlation_id,
                    "subject_ref": item.subject_ref,
                    "prompt_hash": prompt_hash,
                    "pii_fields_prepared": pii_fields,
                    "prompt_fields_prepared": prompt_fields,
                    "company_fields_prepared": company_fields,
                    **provider_config,
                    "preparation_status": "PREPARED",
                },
                ensure_ascii=False,
            ),
        )
        if os.getenv("ASIS_RAW_PROMPT_LOG", "true").lower() == "true":
            log_path = Path(os.getenv("PROMPT_LOG_PATH", "/data/prompt-log.jsonl"))
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "operator_declared_synthetic": True,
                            "classification_enforcement": "reserved_email_and_phone_only",
                            "correlation_id": request.correlation_id,
                            "subject_ref": item.subject_ref,
                            "score": item.score,
                            "score_breakdown": (
                                item.score_breakdown.model_dump()
                                if item.score_breakdown
                                else None
                            ),
                            "matched_feature_labels": item.matched_feature_labels,
                            "candidate_context": item.candidate_context.model_dump(),
                            "company_context": item.company_context.model_dump(),
                            "prompt_hash": prompt_hash,
                            "pii_fields_prepared": pii_fields,
                            "prompt_fields_prepared": prompt_fields,
                            "company_fields_prepared": company_fields,
                            **provider_config,
                            "preparation_status": "PREPARED",
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    mode = _mode(request.mode)
    if mode == "timeout":
        await asyncio.sleep(float(os.getenv("LLM_STUB_TIMEOUT_SECONDS", "3")))
        raise HTTPException(status_code=504, detail="synthetic provider timeout")
    if mode == "rate_limit":
        raise HTTPException(status_code=429, detail="synthetic provider rate limit")
    if mode == "provider_error":
        raise HTTPException(status_code=503, detail="synthetic provider unavailable")
    if mode == "malformed":
        return {"unexpected": "synthetic malformed response"}

    if mode == "overclaim":
        generated = {
            item.subject_ref: "이 지원자는 해당 직무에 매우 적합하므로 우선 채용을 권고합니다."
            for item in request.items
        }
        generation_mode = "synthetic-overclaim-injection"
    elif LLM_PROVIDER == "bedrock":
        if not ALLOW_BEDROCK_LIVE:
            raise HTTPException(
                status_code=503,
                detail="Bedrock live invocation is disabled for the AS-IS runtime",
            )
        try:
            generated = await asyncio.to_thread(_bedrock_explanations, request.items)
        except RuntimeError as exc:
            logger.exception("bedrock_explanation_failed")
            raise HTTPException(status_code=503, detail="Bedrock explanation unavailable") from exc
        generation_mode = "bedrock-converse"
    else:
        generated = {item.subject_ref: _explanation(item) for item in request.items}
        generation_mode = "deterministic-local-stub"

    items: list[dict[str, object]] = []
    for item in request.items:
        prompt_hash, pii_fields, prompt_fields, company_fields = prompt_records[item.subject_ref]
        items.append(
            {
                "subject_ref": item.subject_ref,
                "status": "AVAILABLE",
                "text": generated[item.subject_ref],
                "prompt_hash": prompt_hash,
                "pii_fields_prepared": pii_fields,
                "prompt_fields_prepared": prompt_fields,
                "company_fields_prepared": company_fields,
                "company_alignment": _company_alignment(item),
                **provider_config,
                "generation_mode": generation_mode,
                "output_validation_state": "NOT_IMPLEMENTED_ASIS",
            }
        )
    return {"status": "AVAILABLE", "correlation_id": request.correlation_id, "items": items}
