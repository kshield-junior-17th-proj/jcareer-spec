#!/usr/bin/env python3
"""Validate unexecuted AS-IS observation planning and future receipt schema."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from check_runtime_manifests import load_yaml, parse_yaml_text


PLAN_PATH = Path("src/runtime/contracts/risk_observation_plan.yaml")
RECEIPT_SCHEMA_PATH = Path("src/runtime/contracts/lab_run_receipt.schema.json")
LAB_DEPLOY_PATH = Path("terraform/lab/provisioning/deploy-runtime.ps1")
OBSERVATION_SOURCE_PATH = Path("src/runtime/tests/two_sided_asis_observations.py")
AUTOMATIC_ACTIVATION_DECLARATION_ONLY = {
    Path("scripts/check_runtime_evidence_contracts.py"),
    Path("scripts/check_runtime_infra_contract.py"),
    Path("src/runtime/web/tests/static-contract.mjs"),
    Path("tests/test_runtime_evidence_contracts.py"),
    Path("tests/test_runtime_infra_contract.py"),
}
DECLARATION_ALLOWED_IMPORT_ROOTS = {
    "__future__",
    "argparse",
    "ast",
    "check_runtime_evidence_contracts",
    "check_runtime_infra_contract",
    "check_runtime_manifests",
    "copy",
    "datetime",
    "hashlib",
    "json",
    "jsonschema",
    "os",
    "pathlib",
    "re",
    "sys",
    "tempfile",
    "typing",
}
ACTIVATION_IGNORED_PARTS = {
    ".git",
    ".terraform",
    "__pycache__",
    "dist",
    "node_modules",
}
RISK_OBSERVATION_ACTIVATION = re.compile(
    r"(?<![A-Za-z0-9_])two_sided_asis_observations(?:\.py)?(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
RUNTIME_TEST_DIRECTORY = re.compile(
    r"src[\\/]+runtime[\\/]+tests",
    re.IGNORECASE,
)
RUNTIME_TEST_WILDCARD = re.compile(
    r"\*[^\r\n\"'`]*\.py|(?:r?glob)\s*\(\s*[\"'][^\"']*\.py",
    re.IGNORECASE,
)
RUNTIME_TEST_ENUMERATOR = re.compile(
    r"\b(?:find|ls|dir|get-childitem|readdir(?:sync)?|listdir|iterdir|scandir|walk|r?glob)\b",
    re.IGNORECASE,
)
RUNTIME_TEST_LAUNCHER = re.compile(
    r"\b(?:python3?|pwsh|powershell|bash|sh|node|xargs|subprocess|spawn|popen|"
    r"for(?:each-object)?|while)\b|-exec\b",
    re.IGNORECASE,
)
PLAN_TOP_KEYS = {
    "schema_version",
    "plan_status",
    "execution_status",
    "synthetic_only",
    "runtime_preconditions",
    "source",
    "separation",
    "coverage_limitations",
    "scenarios",
    "cleanup_contract",
    "evidence_ref",
}
PRECONDITION_KEYS = {
    "live_client_service",
    "dataset_profile",
    "explanation_provider",
    "explanation_mode",
    "raw_prompt_log_enabled",
    "bedrock_live_enabled",
}
SOURCE_KEYS = {"script_path", "script_sha256"}
SEPARATION_KEYS = {
    "functional_smoke",
    "automatic_execution",
    "automatic_risk_judgment",
}
COVERAGE_LIMIT_KEYS = {
    "browser_local_storage_state_transition",
    "token_expiration_boundary",
    "organization_membership_and_role_lifecycle",
    "cross_store_partial_commit_fault_injection",
}
EXPECTED_COVERAGE_LIMITS = {
    "browser_local_storage_state_transition": "NOT_OBSERVED_NO_BROWSER_HARNESS",
    "token_expiration_boundary": "NOT_OBSERVED",
    "organization_membership_and_role_lifecycle": "NOT_OBSERVED_NO_API_LIFECYCLE",
    "cross_store_partial_commit_fault_injection": "NOT_OBSERVED_NO_COMMIT_FAULT_INJECTION",
}
SCENARIO_KEYS = {
    "scenario_id",
    "customer_sides",
    "observation_intent",
    "source_assertion_markers",
    "cleanup_surface",
    "automatic_decision",
}
CLEANUP_KEYS = {
    "identifiers",
    "member_user_state",
    "database_rows",
    "redis_keys",
    "raw_prompt_log",
    "cleanup_failure_masks_scenario_failure",
}
EXPECTED_SCENARIOS = {
    "OBS-COMPANY-STATUS-GATE": ("candidate", "company", "platform"),
    "OBS-COMPANY-LIFECYCLE-DECLARATION": ("company", "platform"),
    "OBS-CURRENT-MATERIAL-NOT-SNAPSHOT": ("candidate", "company"),
    "OBS-CONSENT-WITHDRAWAL-ENTERPRISE-READ": ("candidate", "company"),
    "OBS-CONSENT-CATALOG-DRIFT": ("candidate", "platform"),
    "OBS-RECRUITER-CACHE-STALE": ("candidate", "company", "platform"),
    "OBS-RECOMMENDATION-AUDIT-GAP": ("company", "platform"),
    "OBS-APPLICATION-AUDIT-SHAPE": ("candidate", "company", "platform"),
    "OBS-CACHE-ITEM-SCHEMA": ("company", "platform"),
    "OBS-RAW-PROMPT-RETAINED": ("candidate", "platform"),
    "OBS-INTERNAL-SERVICE-UNAUTHENTICATED": ("candidate", "company", "platform"),
    "OBS-PROMPT-FIELD-OVERDISCLOSURE": ("candidate", "company", "platform"),
    "OBS-BOLA-DENIAL-TENANT-SHAPE": ("company", "platform"),
    "OBS-PUBLIC-CLOSED-JOB-DETAIL": ("candidate", "company", "platform"),
    "OBS-API-TOKEN-REUSE-AND-ACCOUNT-ACTIVE-GATE": ("candidate", "platform"),
    "OBS-RECRUITER-LOGICAL-LINK-RESOLUTION": ("company", "platform"),
}
EXPECTED_SCENARIO_COUNT = len(EXPECTED_SCENARIOS)
EXPECTED_SCENARIO_SEQUENCE = {
    scenario_id: index
    for index, scenario_id in enumerate(EXPECTED_SCENARIOS, start=1)
}
EXPECTED_CLEANUP_SURFACES = {
    "OBS-COMPANY-STATUS-GATE": "COMPANY_STATUS_AND_SYNTHETIC_ROWS",
    "OBS-COMPANY-LIFECYCLE-DECLARATION": "SYNTHETIC_ROWS",
    "OBS-CURRENT-MATERIAL-NOT-SNAPSHOT": "SYNTHETIC_ROWS",
    "OBS-CONSENT-WITHDRAWAL-ENTERPRISE-READ": "SYNTHETIC_ROWS_AND_RUN_CACHE_KEYS",
    "OBS-CONSENT-CATALOG-DRIFT": "SYNTHETIC_ROWS",
    "OBS-RECRUITER-CACHE-STALE": "SYNTHETIC_ROWS_AND_RUN_CACHE_KEYS",
    "OBS-RECOMMENDATION-AUDIT-GAP": "SYNTHETIC_ROWS_AND_RUN_CACHE_KEYS",
    "OBS-APPLICATION-AUDIT-SHAPE": "SYNTHETIC_ROWS",
    "OBS-CACHE-ITEM-SCHEMA": "SYNTHETIC_ROWS_AND_RUN_CACHE_KEYS",
    "OBS-RAW-PROMPT-RETAINED": "RAW_PROMPT_OBSERVED_NOT_DELETED",
    "OBS-INTERNAL-SERVICE-UNAUTHENTICATED": "RAW_PROMPT_OBSERVED_NOT_DELETED",
    "OBS-PROMPT-FIELD-OVERDISCLOSURE": "RAW_PROMPT_OBSERVED_NOT_DELETED",
    "OBS-BOLA-DENIAL-TENANT-SHAPE": "SYNTHETIC_ROWS",
    "OBS-PUBLIC-CLOSED-JOB-DETAIL": "SYNTHETIC_ROWS",
    "OBS-API-TOKEN-REUSE-AND-ACCOUNT-ACTIVE-GATE": "MUTATED_MEMBER_STATE_AND_SYNTHETIC_ROWS",
    "OBS-RECRUITER-LOGICAL-LINK-RESOLUTION": "MUTATED_MEMBER_STATE_AND_SYNTHETIC_ROWS",
}
EXPECTED_RECEIPT_PROPERTIES = {
    "schema_version",
    "synthetic_only",
    "run_id",
    "started_at",
    "completed_at",
    "approval_ref",
    "source",
    "platform",
    "provider",
    "artifacts",
    "functional_smoke",
    "risk_observation",
    "cleanup",
    "account_identifiers_included",
    "sensitive_values_included",
    "automatic_assessment_included",
}
RECEIPT_SOURCE_KEYS = {
    "revision",
    "archive_sha256",
    "application_manifest_sha256",
    "endpoint_manifest_sha256",
    "api_surface_sha256",
    "api_effects_sha256",
    "risk_plan_sha256",
    "receipt_schema_sha256",
    "deploy_script_sha256",
}
RECEIPT_SOURCE_HASH_KEYS = RECEIPT_SOURCE_KEYS - {"revision"}
SOURCE_PAYLOAD_KEYS = RECEIPT_SOURCE_HASH_KEYS | {"observation_script_sha256"}
RECEIPT_PLATFORM_KEYS = {
    "architecture",
    "resolved_image_ref_hash",
    "docker_version",
    "compose_version",
    "compose_binary_sha256",
}
RECEIPT_PROVIDER_KEYS = {"mode", "bedrock_live_enabled", "region", "model_ref_hash"}
RECEIPT_ARTIFACT_KEYS = {"service_id", "build_context_sha256", "image_digest"}
RECEIPT_RISK_KEYS = {
    "status",
    "scenario_results",
    "human_review_required",
    "automatic_judgment_included",
}
RECEIPT_SCENARIO_RESULT_KEYS = {
    "scenario_id",
    "sequence_index",
    "source_digest_sha256",
    "execution_status",
    "observation_status",
    "result_digest_sha256",
    "evidence_digest_sha256",
    "evidence_record_count",
    "started_at",
    "completed_at",
    "failure_code",
    "prior_failure_scenario_id",
}
RECEIPT_CLEANUP_KEYS = {
    "runtime_stop_status",
    "synthetic_identifier_set_hash",
    "synthetic_identifier_count",
    "prompt_pair_set_hash",
    "prompt_pair_count",
    "database_residue_count",
    "cache_key_residue_count",
    "raw_prompt_record_count",
}
REDACTED_RESULT_KEYS = {
    "schema_version",
    "scenario_id",
    "execution_status",
    "observation_status",
    "assertion_count",
    "failure_code",
}
REDACTED_EVIDENCE_MANIFEST_KEYS = {
    "schema_version",
    "scenario_id",
    "result_digest_sha256",
    "artifacts",
}
REDACTED_EVIDENCE_ARTIFACT_KEYS = {
    "artifact_kind",
    "content_sha256",
    "record_count",
}
REDACTED_EVIDENCE_ARTIFACT_KINDS = {
    "HTTP_STATUS_SUMMARY",
    "DATABASE_COUNT_SUMMARY",
    "CACHE_STATE_SUMMARY",
    "PROMPT_RECORD_COUNT_SUMMARY",
    "SOURCE_STATE_SUMMARY",
    "CLEANUP_COUNT_SUMMARY",
}
REDACTED_EVIDENCE_PAYLOAD_KEYS = {
    "schema_version",
    "scenario_id",
    "artifact_kind",
    "record_count",
    "metrics",
}
REDACTED_EVIDENCE_METRICS = {
    "HTTP_STATUS_SUMMARY": {
        "request_count",
        "status_2xx_count",
        "status_4xx_count",
        "status_5xx_count",
    },
    "DATABASE_COUNT_SUMMARY": {"before_count", "after_count", "matching_count"},
    "CACHE_STATE_SUMMARY": {
        "key_count",
        "hit_count",
        "miss_count",
        "stale_marker_count",
    },
    "PROMPT_RECORD_COUNT_SUMMARY": {"pair_count", "record_count"},
    "SOURCE_STATE_SUMMARY": {
        "assertion_count",
        "match_count",
        "mismatch_count",
        "incomplete_count",
    },
    "CLEANUP_COUNT_SUMMARY": {"target_count", "remaining_count"},
}
FORBIDDEN_RECEIPT_RECORD_KEYS = {
    "account_id",
    "access_key",
    "secret_key",
    "credential",
    "password",
    "token",
    "candidate_id",
    "company_id",
    "job_id",
    "application_id",
    "correlation_id",
    "subject_ref",
    "prompt",
    "prompt_text",
    "request_body",
    "response_body",
    "error_message",
    "evidence_uri",
    "details",
    "observed_values",
}
EXPECTED_RISK_STATUS_CONDITIONS = [
    {
        "if": {"properties": {"status": {"const": "NOT_RUN"}}, "required": ["status"]},
        "then": {
            "properties": {
                "scenario_results": {
                    "items": {"properties": {"execution_status": {"const": "NOT_RUN"}}}
                }
            }
        },
    },
    {
        "if": {
            "properties": {"status": {"const": "OBSERVATIONS_RECORDED"}},
            "required": ["status"],
        },
        "then": {
            "properties": {
                "scenario_results": {
                    "items": {
                        "properties": {"execution_status": {"const": "COMPLETED"}}
                    }
                }
            }
        },
    },
    {
        "if": {
            "properties": {"status": {"const": "SCRIPT_FAILED"}},
            "required": ["status"],
        },
        "then": {
            "properties": {
                "scenario_results": {
                    "items": {
                        "properties": {
                            "execution_status": {
                                "enum": [
                                    "COMPLETED",
                                    "FAILED",
                                    "SKIPPED_AFTER_FAILURE",
                                ]
                            }
                        }
                    },
                    "contains": {
                        "properties": {
                            "execution_status": {"const": "FAILED"}
                        },
                        "required": ["execution_status"],
                    },
                    "minContains": 1,
                    "maxContains": 1,
                }
            }
        },
    },
]
EXPECTED_SCENARIO_EXECUTION_CONDITIONS = [
    {
        "if": {
            "properties": {"execution_status": {"const": "NOT_RUN"}},
            "required": ["execution_status"],
        },
        "then": {
            "properties": {
                "observation_status": {"const": "NOT_OBSERVED"},
                "result_digest_sha256": {"type": "null"},
                "evidence_digest_sha256": {"type": "null"},
                "evidence_record_count": {"const": 0},
                "started_at": {"type": "null"},
                "completed_at": {"type": "null"},
                "failure_code": {"type": "null"},
                "prior_failure_scenario_id": {"type": "null"},
            }
        },
    },
    {
        "if": {
            "properties": {"execution_status": {"const": "COMPLETED"}},
            "required": ["execution_status"],
        },
        "then": {
            "properties": {
                "observation_status": {
                    "enum": ["SOURCE_ASSERTION_MATCH", "SOURCE_ASSERTION_MISMATCH"]
                },
                "result_digest_sha256": {"$ref": "#/$defs/sha256"},
                "evidence_digest_sha256": {"$ref": "#/$defs/sha256"},
                "evidence_record_count": {"type": "integer", "minimum": 1},
                "started_at": {"type": "string", "format": "date-time"},
                "completed_at": {"type": "string", "format": "date-time"},
                "failure_code": {"type": "null"},
                "prior_failure_scenario_id": {"type": "null"},
            }
        },
    },
    {
        "if": {
            "properties": {"execution_status": {"const": "FAILED"}},
            "required": ["execution_status"],
        },
        "then": {
            "properties": {
                "observation_status": {"const": "OBSERVATION_INCOMPLETE"},
                "result_digest_sha256": {"$ref": "#/$defs/sha256"},
                "evidence_digest_sha256": {"$ref": "#/$defs/sha256"},
                "evidence_record_count": {"type": "integer", "minimum": 1},
                "started_at": {"type": "string", "format": "date-time"},
                "completed_at": {"type": "string", "format": "date-time"},
                "failure_code": {
                    "type": "string",
                    "pattern": "^[A-Z][A-Z0-9_]{0,79}$",
                },
                "prior_failure_scenario_id": {"type": "null"},
            }
        },
    },
    {
        "if": {
            "properties": {
                "execution_status": {"const": "SKIPPED_AFTER_FAILURE"}
            },
            "required": ["execution_status"],
        },
        "then": {
            "properties": {
                "observation_status": {"const": "NOT_OBSERVED"},
                "result_digest_sha256": {"type": "null"},
                "evidence_digest_sha256": {"type": "null"},
                "evidence_record_count": {"const": 0},
                "started_at": {"type": "null"},
                "completed_at": {"type": "null"},
                "failure_code": {"type": "null"},
                "prior_failure_scenario_id": {"enum": list(EXPECTED_SCENARIOS)},
            }
        },
    },
]
EXPECTED_BEDROCK_RISK_CONDITION = [
    {
        "if": {
            "properties": {
                "provider": {
                    "properties": {"mode": {"const": "bedrock"}},
                    "required": ["mode"],
                }
            },
            "required": ["provider"],
        },
        "then": {
            "properties": {
                "risk_observation": {
                    "properties": {"status": {"const": "NOT_RUN"}}
                }
            }
        },
    }
]


class DuplicateKeyError(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise DuplicateKeyError(key)
        value[key] = item
    return value


def load_json(path: Path, label: str, errors: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, json.JSONDecodeError, DuplicateKeyError):
        errors.append(f"{label}: JSON parse 또는 중복 key 오류")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{label}: 최상위 object 필요")
        return {}
    return value


def exact_keys(value: object, expected: set[str], label: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{label}: mapping/object 필요")
        return False
    actual = set(value)
    if actual != expected:
        errors.append(
            f"{label}: field 집합 불일치 "
            f"(missing={sorted(expected - actual)}, unknown={sorted(actual - expected)})"
        )
        return False
    return True


def check_plan_document(
    document: dict[str, Any], root: Path, script_text: str | None = None
) -> list[str]:
    errors: list[str] = []
    if not exact_keys(document, PLAN_TOP_KEYS, "risk observation plan", errors):
        return errors
    expected_scalars = {
        "schema_version": "jcareer-asis-risk-observation-plan-v1",
        "plan_status": "DRAFT_NOT_APPROVED",
        "execution_status": "NOT_EXECUTED",
        "synthetic_only": True,
        "evidence_ref": None,
    }
    for field, expected in expected_scalars.items():
        if document.get(field) != expected or type(document.get(field)) is not type(expected):
            errors.append(f"risk observation plan: {field} 고정값 불일치")

    preconditions = document.get("runtime_preconditions")
    if exact_keys(preconditions, PRECONDITION_KEYS, "runtime preconditions", errors):
        expected = {
            "live_client_service": False,
            "dataset_profile": "demo_not_for_measurement",
            "explanation_provider": "local-synthetic-stub",
            "explanation_mode": "success",
            "raw_prompt_log_enabled": True,
            "bedrock_live_enabled": False,
        }
        if preconditions != expected:
            errors.append("runtime preconditions: 합성 stub 전용 경계 불일치")

    source = document.get("source")
    if exact_keys(source, SOURCE_KEYS, "observation source", errors):
        relative = source.get("script_path")
        if relative != "src/runtime/tests/two_sided_asis_observations.py":
            errors.append("observation source: 고정 script 경로 불일치")
        elif Path(relative).is_absolute() or ".." in Path(relative).parts:
            errors.append("observation source: 저장소 밖 경로 금지")
        else:
            path = root / relative
            if script_text is None:
                try:
                    script_text = path.read_text(encoding="utf-8")
                except OSError:
                    errors.append("observation source: script를 읽을 수 없음")
            if script_text is not None:
                observed_hash = hashlib.sha256(script_text.encode("utf-8")).hexdigest()
                if source.get("script_sha256") != observed_hash:
                    errors.append("observation source: script SHA-256 불일치")

    separation = document.get("separation")
    if exact_keys(separation, SEPARATION_KEYS, "observation separation", errors):
        expected = {
            "functional_smoke": "SEPARATE_EVIDENCE_CLASS",
            "automatic_execution": False,
            "automatic_risk_judgment": False,
        }
        if separation != expected:
            errors.append("observation separation: 기능 smoke·위험 관찰 경계 불일치")

    coverage_limitations = document.get("coverage_limitations")
    if exact_keys(
        coverage_limitations,
        COVERAGE_LIMIT_KEYS,
        "observation coverage limitations",
        errors,
    ) and coverage_limitations != EXPECTED_COVERAGE_LIMITS:
        errors.append("observation coverage limitations: 미관찰 표면 선언 불일치")

    scenarios = document.get("scenarios")
    if not isinstance(scenarios, list):
        errors.append("risk observation scenarios: list 필요")
    else:
        seen: set[str] = set()
        for index, scenario in enumerate(scenarios):
            label = f"risk observation scenario[{index}]"
            if not exact_keys(scenario, SCENARIO_KEYS, label, errors):
                continue
            scenario_id = scenario.get("scenario_id")
            if scenario_id not in EXPECTED_SCENARIOS:
                errors.append(f"{label}: scenario_id 불일치")
                continue
            if scenario_id in seen:
                errors.append(f"{label}: scenario_id 중복")
            seen.add(scenario_id)
            if scenario.get("customer_sides") != list(EXPECTED_SCENARIOS[scenario_id]):
                errors.append(f"{label}: customer_sides 불일치")
            if scenario.get("cleanup_surface") != EXPECTED_CLEANUP_SURFACES[scenario_id]:
                errors.append(f"{label}: cleanup_surface 불일치")
            if scenario.get("automatic_decision") is not False:
                errors.append(f"{label}: 자동 판정 금지")
            if not isinstance(scenario.get("observation_intent"), str) or not scenario["observation_intent"].strip():
                errors.append(f"{label}: observation_intent 필요")
            markers = scenario.get("source_assertion_markers")
            if not isinstance(markers, list) or len(markers) < 2:
                errors.append(f"{label}: source marker 두 개 이상 필요")
            elif script_text is not None:
                missing = [marker for marker in markers if not isinstance(marker, str) or marker not in script_text]
                if missing:
                    errors.append(f"{label}: source assertion marker 불일치")
        if seen != set(EXPECTED_SCENARIOS):
            errors.append(
                f"risk observation scenarios: 고정 {EXPECTED_SCENARIO_COUNT}개 ID 집합 불일치"
            )

    cleanup = document.get("cleanup_contract")
    if exact_keys(cleanup, CLEANUP_KEYS, "observation cleanup", errors):
        expected = {
            "identifiers": "CURRENT_RUN_CANONICAL_UUIDS_ONLY",
            "member_user_state": "CONDITIONAL_EXACT_RESTORE_WITH_DELETE_FALLBACK",
            "database_rows": "DELETE_AND_VERIFY_ZERO",
            "redis_keys": "DELETE_MATCHED_RUN_KEYS_AND_VERIFY_ZERO",
            "raw_prompt_log": "RETAIN_AND_VERIFY_EXACT_RECORDED_PAIRS",
            "cleanup_failure_masks_scenario_failure": False,
        }
        if cleanup != expected:
            errors.append("observation cleanup: source 관찰 경계 불일치")
    return errors


def _walk_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(_walk_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_walk_keys(item) for item in value), set())
    return set()


def strict_schema_properties(
    schema: object, expected: set[str], label: str, errors: list[str]
) -> dict[str, Any]:
    if not isinstance(schema, dict):
        errors.append(f"{label}: schema object 필요")
        return {}
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        errors.append(f"{label}: strict object 필요")
    properties = schema.get("properties")
    if not isinstance(properties, dict) or set(properties) != expected:
        errors.append(f"{label}: property 집합 불일치")
        return {}
    if set(schema.get("required", [])) != expected:
        errors.append(f"{label}: 모든 property required 필요")
    return properties


def contains_exactly_once_ids(
    schema: object, id_field: str, expected: set[str], label: str, errors: list[str]
) -> None:
    if not isinstance(schema, dict):
        errors.append(f"{label}: array schema 필요")
        return
    clauses = schema.get("allOf")
    if not isinstance(clauses, list):
        errors.append(f"{label}: ID별 contains 계약 필요")
        return
    observed: list[str] = []
    for clause in clauses:
        if not isinstance(clause, dict) or clause.get("minContains") != 1 or clause.get("maxContains") != 1:
            errors.append(f"{label}: 각 ID는 정확히 한 번 필요")
            continue
        contains = clause.get("contains")
        if not isinstance(contains, dict) or contains.get("required") != [id_field]:
            errors.append(f"{label}: contains required 불일치")
            continue
        value = (
            contains.get("properties", {})
            .get(id_field, {})
            .get("const")
        )
        if isinstance(value, str):
            observed.append(value)
        else:
            errors.append(f"{label}: contains const 불일치")
    if len(observed) != len(set(observed)) or set(observed) != expected:
        errors.append(f"{label}: ID별 exactly-once 집합 불일치")


def contains_exactly_once_scenario_sequence(
    schema: object, expected: dict[str, int], label: str, errors: list[str]
) -> None:
    if not isinstance(schema, dict):
        errors.append(f"{label}: array schema 필요")
        return
    clauses = schema.get("allOf")
    if not isinstance(clauses, list):
        errors.append(f"{label}: ID·sequence별 contains 계약 필요")
        return
    observed: dict[str, int] = {}
    for clause in clauses:
        if (
            not isinstance(clause, dict)
            or clause.get("minContains") != 1
            or clause.get("maxContains") != 1
        ):
            errors.append(f"{label}: 각 ID·sequence는 정확히 한 번 필요")
            continue
        contains = clause.get("contains")
        if not isinstance(contains, dict) or contains.get("required") != [
            "scenario_id",
            "sequence_index",
        ]:
            errors.append(f"{label}: contains ID·sequence required 불일치")
            continue
        properties = contains.get("properties", {})
        scenario_id = properties.get("scenario_id", {}).get("const")
        sequence_index = properties.get("sequence_index", {}).get("const")
        if not isinstance(scenario_id, str) or not isinstance(sequence_index, int):
            errors.append(f"{label}: contains ID·sequence const 불일치")
            continue
        if scenario_id in observed:
            errors.append(f"{label}: scenario ID 중복")
            continue
        observed[scenario_id] = sequence_index
    if observed != expected:
        errors.append(f"{label}: canonical ID·sequence 집합 불일치")


def check_receipt_schema(document: dict[str, Any], deploy_text: str) -> list[str]:
    errors: list[str] = []
    if document.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        errors.append("lab receipt schema: JSON Schema draft 불일치")
    if document.get("$id") != "https://jcareer.test/schemas/lab-run-receipt-v2.json":
        errors.append("lab receipt schema: v2 $id 불일치")
    if document.get("description") != "Schema only. Its presence is not evidence that a lab run occurred.":
        errors.append("lab receipt schema: 실행 증거 아님 설명 불일치")
    if document.get("x-jcareer-artifact-state") != "SCHEMA_ONLY_NO_RECEIPT_NO_EXECUTION_EVIDENCE":
        errors.append("lab receipt schema: schema-only artifact 상태 불일치")
    if document.get("type") != "object" or document.get("additionalProperties") is not False:
        errors.append("lab receipt schema: strict root object 필요")
    if document.get("allOf") != EXPECTED_BEDROCK_RISK_CONDITION:
        errors.append("lab receipt schema: Bedrock이면 위험 관찰 NOT_RUN 조건 필요")
    properties = document.get("properties")
    if not isinstance(properties, dict) or set(properties) != EXPECTED_RECEIPT_PROPERTIES:
        errors.append("lab receipt schema: root property 집합 불일치")
        return errors
    if set(document.get("required", [])) != EXPECTED_RECEIPT_PROPERTIES:
        errors.append("lab receipt schema: 모든 root property required 필요")
    consts = {
        "schema_version": "jcareer-synthetic-lab-run-receipt-v2",
        "synthetic_only": True,
        "account_identifiers_included": False,
        "sensitive_values_included": False,
        "automatic_assessment_included": False,
    }
    for field, expected in consts.items():
        if properties.get(field, {}).get("const") != expected:
            errors.append(f"lab receipt schema: {field} const 불일치")

    source = strict_schema_properties(
        properties.get("source"), RECEIPT_SOURCE_KEYS, "lab receipt source", errors
    )
    for field in RECEIPT_SOURCE_KEYS - {"revision"}:
        if source.get(field) != {"$ref": "#/$defs/sha256"}:
            errors.append(f"lab receipt source: {field} SHA-256 ref 불일치")

    platform = strict_schema_properties(
        properties.get("platform"), RECEIPT_PLATFORM_KEYS, "lab receipt platform", errors
    )
    if platform.get("resolved_image_ref_hash") != {"$ref": "#/$defs/sha256"}:
        errors.append("lab receipt platform: image ref 원문 대신 hash 필요")

    provider_schema = properties.get("provider")
    provider = strict_schema_properties(
        provider_schema, RECEIPT_PROVIDER_KEYS, "lab receipt provider", errors
    )
    modes: dict[str, dict[str, Any]] = {}
    if isinstance(provider_schema, dict):
        for clause in provider_schema.get("allOf", []):
            if not isinstance(clause, dict):
                continue
            condition = clause.get("if", {})
            mode = condition.get("properties", {}).get("mode", {}).get("const")
            if condition.get("required") == ["mode"] and isinstance(mode, str):
                modes[mode] = clause.get("then", {}).get("properties", {})
    if set(modes) != {"local-synthetic-stub", "bedrock"}:
        errors.append("lab receipt provider: stub/Bedrock 조건부 계약 불일치")
    else:
        stub = modes["local-synthetic-stub"]
        bedrock = modes["bedrock"]
        if stub != {
            "bedrock_live_enabled": {"const": False},
            "region": {"type": "null"},
            "model_ref_hash": {"type": "null"},
        }:
            errors.append("lab receipt provider: local stub는 Bedrock 비활성·식별자 없음 필요")
        if bedrock != {
            "bedrock_live_enabled": {"const": True},
            "region": {"type": "string", "minLength": 1, "maxLength": 40},
            "model_ref_hash": {"$ref": "#/$defs/sha256"},
        }:
            errors.append("lab receipt provider: Bedrock 사용 조건 계약 불일치")
    if provider.get("mode", {}).get("enum") != ["local-synthetic-stub", "bedrock"]:
        errors.append("lab receipt provider: mode enum 불일치")

    artifacts = properties.get("artifacts", {})
    artifact_properties = strict_schema_properties(
        artifacts.get("items") if isinstance(artifacts, dict) else None,
        RECEIPT_ARTIFACT_KEYS,
        "lab receipt artifact",
        errors,
    )
    services = artifact_properties.get("service_id", {}).get("enum")
    if services != ["web", "api", "agent", "llm-gateway"]:
        errors.append("lab receipt schema: 네 app artifact ID 불일치")
    if artifacts.get("minItems") != 4 or artifacts.get("maxItems") != 4:
        errors.append("lab receipt schema: app artifact 정확히 네 개 필요")
    contains_exactly_once_ids(
        artifacts,
        "service_id",
        {"web", "api", "agent", "llm-gateway"},
        "lab receipt artifacts",
        errors,
    )

    if properties.get("functional_smoke") != {"$ref": "#/$defs/checkClass"}:
        errors.append("lab receipt functional smoke: 독립 checkClass ref 필요")
    risk_schema = properties.get("risk_observation")
    if not isinstance(risk_schema, dict) or risk_schema.get("allOf") != EXPECTED_RISK_STATUS_CONDITIONS:
        errors.append("lab receipt risk observation: 상태별 관찰 결과 조건 불일치")
    risk = strict_schema_properties(
        risk_schema, RECEIPT_RISK_KEYS, "lab receipt risk observation", errors
    )
    if risk.get("status", {}).get("enum") != ["NOT_RUN", "OBSERVATIONS_RECORDED", "SCRIPT_FAILED"]:
        errors.append("lab receipt risk observation: PASS/FAIL 아닌 관찰 상태 필요")
    if risk.get("human_review_required", {}).get("const") is not True:
        errors.append("lab receipt risk observation: human review 고정 필요")
    if risk.get("automatic_judgment_included", {}).get("const") is not False:
        errors.append("lab receipt risk observation: 자동 판정 금지")
    scenario_results = risk.get("scenario_results", {})
    result_properties = strict_schema_properties(
        scenario_results.get("items") if isinstance(scenario_results, dict) else None,
        RECEIPT_SCENARIO_RESULT_KEYS,
        "lab receipt scenario result",
        errors,
    )
    if result_properties.get("execution_status", {}).get("enum") != [
        "NOT_RUN",
        "COMPLETED",
        "FAILED",
        "SKIPPED_AFTER_FAILURE",
    ]:
        errors.append("lab receipt scenario result: 실행 상태 불일치")
    if result_properties.get("observation_status", {}).get("enum") != [
        "NOT_OBSERVED",
        "SOURCE_ASSERTION_MATCH",
        "SOURCE_ASSERTION_MISMATCH",
        "OBSERVATION_INCOMPLETE",
    ]:
        errors.append("lab receipt scenario result: 비판정 관찰 상태 불일치")
    if result_properties.get("sequence_index") != {
        "type": "integer",
        "minimum": 1,
        "maximum": EXPECTED_SCENARIO_COUNT,
    }:
        errors.append("lab receipt scenario result: sequence 범위 불일치")
    if result_properties.get("source_digest_sha256") != {"$ref": "#/$defs/sha256"}:
        errors.append("lab receipt scenario result: source digest 필요")
    nullable_digest = {
        "anyOf": [{"$ref": "#/$defs/sha256"}, {"type": "null"}]
    }
    for field in ("result_digest_sha256", "evidence_digest_sha256"):
        if result_properties.get(field) != nullable_digest:
            errors.append(f"lab receipt scenario result: {field} digest/null 계약 불일치")
    if result_properties.get("evidence_record_count") != {
        "type": "integer",
        "minimum": 0,
    }:
        errors.append("lab receipt scenario result: evidence count 불일치")
    for field in ("started_at", "completed_at"):
        if result_properties.get(field) != {
            "type": ["string", "null"],
            "format": "date-time",
        }:
            errors.append(f"lab receipt scenario result: {field} date-time/null 계약 불일치")
    if result_properties.get("failure_code") != {
        "anyOf": [
            {
                "type": "string",
                "pattern": "^[A-Z][A-Z0-9_]{0,79}$",
            },
            {"type": "null"},
        ]
    }:
        errors.append("lab receipt scenario result: bounded failure code 계약 불일치")
    if result_properties.get("prior_failure_scenario_id") != {
        "anyOf": [{"enum": list(EXPECTED_SCENARIOS)}, {"type": "null"}]
    }:
        errors.append("lab receipt scenario result: prior failure ref 계약 불일치")
    result_schema = scenario_results.get("items", {}) if isinstance(scenario_results, dict) else {}
    if not isinstance(result_schema, dict) or result_schema.get("allOf") != EXPECTED_SCENARIO_EXECUTION_CONDITIONS:
        errors.append("lab receipt scenario result: 실행별 digest·중단 조건 불일치")
    if (
        scenario_results.get("minItems") != EXPECTED_SCENARIO_COUNT
        or scenario_results.get("maxItems") != EXPECTED_SCENARIO_COUNT
    ):
        errors.append(
            f"lab receipt scenario result: 정확히 {EXPECTED_SCENARIO_COUNT}개 필요"
        )
    contains_exactly_once_scenario_sequence(
        scenario_results,
        EXPECTED_SCENARIO_SEQUENCE,
        "lab receipt scenario results",
        errors,
    )

    cleanup = strict_schema_properties(
        properties.get("cleanup"), RECEIPT_CLEANUP_KEYS, "lab receipt cleanup", errors
    )
    if cleanup.get("runtime_stop_status", {}).get("enum") != [
        "NOT_REQUESTED",
        "REQUESTED",
        "CONFIRMED",
        "FAILED",
    ]:
        errors.append("lab receipt cleanup: runtime stop 상태 불일치")
    for field in ("synthetic_identifier_set_hash", "prompt_pair_set_hash"):
        if cleanup.get(field) != {"$ref": "#/$defs/sha256"}:
            errors.append(f"lab receipt cleanup: {field} redacted SHA-256 필요")
    for field in (
        "synthetic_identifier_count",
        "prompt_pair_count",
        "database_residue_count",
        "cache_key_residue_count",
        "raw_prompt_record_count",
    ):
        if cleanup.get(field) != {"type": "integer", "minimum": 0}:
            errors.append(f"lab receipt cleanup: {field} nonnegative integer 필요")

    definitions = document.get("$defs", {})
    check_class = strict_schema_properties(
        definitions.get("checkClass") if isinstance(definitions, dict) else None,
        {"status", "check_ids"},
        "lab receipt checkClass",
        errors,
    )
    if check_class.get("status", {}).get("enum") != ["NOT_RUN", "PASS", "FAIL"]:
        errors.append("lab receipt functional smoke 상태 불일치")
    observed_forbidden = sorted(_walk_keys(document) & FORBIDDEN_RECEIPT_RECORD_KEYS)
    if observed_forbidden:
        errors.append(f"lab receipt schema: 민감·계정 field 금지 {observed_forbidden}")
    check_automatic_activation_text(
        deploy_text,
        "provided activation surface",
        errors,
    )
    return errors


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def scenario_source_digest(plan: dict[str, Any], scenario_id: str) -> str:
    scenarios = plan.get("scenarios", [])
    scenario = next(
        (
            candidate
            for candidate in scenarios
            if isinstance(candidate, dict)
            and candidate.get("scenario_id") == scenario_id
        ),
        None,
    )
    if scenario is None:
        raise ValueError(f"unknown scenario_id: {scenario_id}")
    source = plan.get("source", {})
    return canonical_sha256(
        {
            "schema_version": "jcareer-risk-observation-source-v1",
            "plan_schema_version": plan.get("schema_version"),
            "script_sha256": source.get("script_sha256")
            if isinstance(source, dict)
            else None,
            "scenario": scenario,
        }
    )


def redacted_result_digest(record: dict[str, Any]) -> str:
    return canonical_sha256(record)


def redacted_evidence_digest(manifest: dict[str, Any]) -> str:
    canonical = dict(manifest)
    artifacts = canonical.get("artifacts")
    if isinstance(artifacts, list):
        canonical["artifacts"] = sorted(
            artifacts,
            key=lambda item: json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
    return canonical_sha256(canonical)


def redacted_evidence_payload_digest(payload: dict[str, Any]) -> str:
    return canonical_sha256(payload)


def _parse_aware_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def validate_receipt_instance(
    receipt: dict[str, Any],
    plan: dict[str, Any],
    source_payloads: dict[str, bytes],
    redacted_results: dict[str, dict[str, Any]],
    redacted_evidence_manifests: dict[str, dict[str, Any]],
    redacted_evidence_payloads: dict[str, list[dict[str, Any]]],
) -> list[str]:
    """Validate a future redacted receipt against supplied source and aggregate bytes."""

    errors: list[str] = []
    if receipt.get("schema_version") != "jcareer-synthetic-lab-run-receipt-v2":
        errors.append("receipt instance: v2 schema_version 필요")
    source = receipt.get("source")
    if not isinstance(source, dict):
        errors.append("receipt instance: source object 필요")
    if set(source_payloads) != SOURCE_PAYLOAD_KEYS:
        errors.append("receipt instance: source payload 집합 불일치")
    if isinstance(source, dict):
        for field in RECEIPT_SOURCE_HASH_KEYS:
            payload = source_payloads.get(field)
            if not isinstance(payload, bytes):
                errors.append(f"receipt instance: source payload bytes 필요 {field}")
                continue
            computed = hashlib.sha256(payload).hexdigest()
            if source.get(field) != computed:
                errors.append(f"receipt instance: global source digest 불일치 {field}")

    risk_plan_payload = source_payloads.get("risk_plan_sha256")
    if isinstance(risk_plan_payload, bytes):
        plan_parse_errors: list[str] = []
        try:
            parsed_plan = parse_yaml_text(
                risk_plan_payload.decode("utf-8"),
                "receipt instance risk plan payload",
                plan_parse_errors,
            )
        except UnicodeDecodeError:
            parsed_plan = {}
            plan_parse_errors.append("receipt instance risk plan payload: UTF-8 필요")
        errors.extend(plan_parse_errors)
        if parsed_plan != plan:
            errors.append("receipt instance: parsed risk plan과 payload 불일치")

    observation_script_payload = source_payloads.get("observation_script_sha256")
    plan_source = plan.get("source")
    if not isinstance(observation_script_payload, bytes):
        errors.append("receipt instance: observation script payload bytes 필요")
    elif not isinstance(plan_source, dict) or plan_source.get(
        "script_sha256"
    ) != hashlib.sha256(observation_script_payload).hexdigest():
        errors.append("receipt instance: observation script digest와 plan 불일치")

    risk = receipt.get("risk_observation")
    if not isinstance(risk, dict):
        return errors + ["receipt instance: risk_observation object 필요"]
    scenario_results = risk.get("scenario_results")
    if not isinstance(scenario_results, list):
        return errors + ["receipt instance: scenario_results array 필요"]

    expected_ids = list(EXPECTED_SCENARIOS)
    observed_ids = [
        result.get("scenario_id") if isinstance(result, dict) else None
        for result in scenario_results
    ]
    if observed_ids != expected_ids:
        errors.append("receipt instance: scenario canonical order 불일치")
    if len(scenario_results) != len(expected_ids):
        errors.append(
            f"receipt instance: scenario 결과 정확히 {EXPECTED_SCENARIO_COUNT}개 필요"
        )

    result_by_id = {
        result.get("scenario_id"): result
        for result in scenario_results
        if isinstance(result, dict) and isinstance(result.get("scenario_id"), str)
    }
    for scenario_id, sequence_index in EXPECTED_SCENARIO_SEQUENCE.items():
        result = result_by_id.get(scenario_id)
        if not isinstance(result, dict):
            errors.append(f"receipt instance: scenario 누락 {scenario_id}")
            continue
        if result.get("sequence_index") != sequence_index:
            errors.append(f"receipt instance: scenario sequence 불일치 {scenario_id}")
        try:
            expected_source_digest = scenario_source_digest(plan, scenario_id)
        except ValueError as exc:
            errors.append(f"receipt instance: {exc}")
        else:
            if result.get("source_digest_sha256") != expected_source_digest:
                errors.append(f"receipt instance: source digest 불일치 {scenario_id}")

    top_status = risk.get("status")
    provider = receipt.get("provider")
    if (
        isinstance(provider, dict)
        and provider.get("mode") == "bedrock"
        and top_status != "NOT_RUN"
    ):
        errors.append("receipt instance: Bedrock mode 위험 관찰은 NOT_RUN 필요")
    execution_statuses = [
        result.get("execution_status")
        for result in scenario_results
        if isinstance(result, dict)
    ]
    if top_status == "NOT_RUN":
        if any(status != "NOT_RUN" for status in execution_statuses):
            errors.append("receipt instance: NOT_RUN이면 모든 scenario가 NOT_RUN이어야 함")
    elif top_status == "OBSERVATIONS_RECORDED":
        if any(status != "COMPLETED" for status in execution_statuses):
            errors.append("receipt instance: 관찰 기록이면 모든 scenario가 COMPLETED여야 함")
    elif top_status == "SCRIPT_FAILED":
        failed_indexes = [
            index
            for index, status in enumerate(execution_statuses)
            if status == "FAILED"
        ]
        if len(failed_indexes) != 1:
            errors.append("receipt instance: SCRIPT_FAILED는 FAILED scenario 정확히 한 개 필요")
        else:
            failed_index = failed_indexes[0]
            failed_id = observed_ids[failed_index]
            if any(status != "COMPLETED" for status in execution_statuses[:failed_index]):
                errors.append("receipt instance: FAILED 이전 scenario는 모두 COMPLETED여야 함")
            if any(
                status != "SKIPPED_AFTER_FAILURE"
                for status in execution_statuses[failed_index + 1 :]
            ):
                errors.append("receipt instance: FAILED 이후 scenario는 모두 SKIPPED_AFTER_FAILURE여야 함")
            for result in scenario_results[failed_index + 1 :]:
                if (
                    isinstance(result, dict)
                    and result.get("prior_failure_scenario_id") != failed_id
                ):
                    errors.append("receipt instance: skipped scenario의 prior failure 참조 불일치")
    else:
        errors.append("receipt instance: risk observation status 불일치")

    attempted_ids = {
        result.get("scenario_id")
        for result in scenario_results
        if isinstance(result, dict)
        and isinstance(result.get("scenario_id"), str)
        and isinstance(result.get("execution_status"), str)
        and result.get("execution_status") in {"COMPLETED", "FAILED"}
    }
    if set(redacted_results) != attempted_ids:
        errors.append("receipt instance: redacted result 집합과 실행 scenario 집합 불일치")
    if set(redacted_evidence_manifests) != attempted_ids:
        errors.append("receipt instance: evidence manifest 집합과 실행 scenario 집합 불일치")
    if set(redacted_evidence_payloads) != attempted_ids:
        errors.append("receipt instance: evidence payload 집합과 실행 scenario 집합 불일치")

    sha_pattern = re.compile(r"^[0-9a-f]{64}$")
    plan_scenarios = {
        scenario.get("scenario_id"): scenario
        for scenario in plan.get("scenarios", [])
        if isinstance(scenario, dict) and isinstance(scenario.get("scenario_id"), str)
    }
    for scenario_id in sorted(attempted_ids):
        receipt_result = result_by_id.get(scenario_id)
        result_record = redacted_results.get(scenario_id)
        manifest = redacted_evidence_manifests.get(scenario_id)
        evidence_payloads = redacted_evidence_payloads.get(scenario_id)
        if not isinstance(receipt_result, dict):
            continue
        if not isinstance(result_record, dict):
            errors.append(f"receipt instance: redacted result 누락 {scenario_id}")
            continue
        forbidden = sorted(_walk_keys(result_record) & FORBIDDEN_RECEIPT_RECORD_KEYS)
        if forbidden:
            errors.append(f"receipt instance: redacted result 원문 field 금지 {scenario_id} {forbidden}")
        if set(result_record) != REDACTED_RESULT_KEYS:
            errors.append(f"receipt instance: redacted result property 집합 불일치 {scenario_id}")
            continue
        if result_record.get("schema_version") != "jcareer-risk-observation-result-v1":
            errors.append(f"receipt instance: redacted result version 불일치 {scenario_id}")
        for field in ("scenario_id", "execution_status", "observation_status", "failure_code"):
            if result_record.get(field) != receipt_result.get(field):
                errors.append(f"receipt instance: redacted result {field} 불일치 {scenario_id}")
        assertion_count = result_record.get("assertion_count")
        if (
            not isinstance(assertion_count, int)
            or isinstance(assertion_count, bool)
            or assertion_count < 0
        ):
            errors.append(f"receipt instance: assertion_count 불일치 {scenario_id}")
        else:
            scenario_plan = plan_scenarios.get(scenario_id, {})
            source_markers = (
                scenario_plan.get("source_assertion_markers", [])
                if isinstance(scenario_plan, dict)
                else []
            )
            expected_assertion_count = len(source_markers) if isinstance(source_markers, list) else 0
            if (
                receipt_result.get("execution_status") == "COMPLETED"
                and assertion_count != expected_assertion_count
            ):
                errors.append(f"receipt instance: completed assertion count 불일치 {scenario_id}")
            if (
                receipt_result.get("execution_status") == "FAILED"
                and assertion_count > expected_assertion_count
            ):
                errors.append(f"receipt instance: failed assertion count 범위 불일치 {scenario_id}")
        computed_result_digest = redacted_result_digest(result_record)
        if receipt_result.get("result_digest_sha256") != computed_result_digest:
            errors.append(f"receipt instance: result digest 불일치 {scenario_id}")

        if not isinstance(manifest, dict):
            errors.append(f"receipt instance: evidence manifest 누락 {scenario_id}")
            continue
        forbidden = sorted(_walk_keys(manifest) & FORBIDDEN_RECEIPT_RECORD_KEYS)
        if forbidden:
            errors.append(f"receipt instance: evidence manifest 원문 field 금지 {scenario_id} {forbidden}")
        if set(manifest) != REDACTED_EVIDENCE_MANIFEST_KEYS:
            errors.append(f"receipt instance: evidence manifest property 집합 불일치 {scenario_id}")
            continue
        if manifest.get("schema_version") != "jcareer-risk-observation-evidence-v1":
            errors.append(f"receipt instance: evidence manifest version 불일치 {scenario_id}")
        if manifest.get("scenario_id") != scenario_id:
            errors.append(f"receipt instance: evidence manifest scenario 불일치 {scenario_id}")
        if manifest.get("result_digest_sha256") != computed_result_digest:
            errors.append(f"receipt instance: evidence manifest result 결속 불일치 {scenario_id}")
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            errors.append(f"receipt instance: redacted evidence artifact 필요 {scenario_id}")
            continue
        if not isinstance(evidence_payloads, list) or not evidence_payloads:
            errors.append(f"receipt instance: redacted evidence payload 필요 {scenario_id}")
            continue
        payload_artifacts: list[tuple[str, str, int]] = []
        source_state_payload_count = 0
        for payload in evidence_payloads:
            if not isinstance(payload, dict) or set(payload) != REDACTED_EVIDENCE_PAYLOAD_KEYS:
                errors.append(f"receipt instance: evidence payload property 집합 불일치 {scenario_id}")
                continue
            forbidden = sorted(_walk_keys(payload) & FORBIDDEN_RECEIPT_RECORD_KEYS)
            if forbidden:
                errors.append(f"receipt instance: evidence payload 원문 field 금지 {scenario_id} {forbidden}")
            payload_kind = payload.get("artifact_kind")
            payload_count = payload.get("record_count")
            payload_metrics = payload.get("metrics")
            if payload.get("schema_version") != "jcareer-risk-observation-artifact-v1":
                errors.append(f"receipt instance: evidence payload version 불일치 {scenario_id}")
            if payload.get("scenario_id") != scenario_id:
                errors.append(f"receipt instance: evidence payload scenario 불일치 {scenario_id}")
            if not isinstance(payload_kind, str) or payload_kind not in REDACTED_EVIDENCE_ARTIFACT_KINDS:
                errors.append(f"receipt instance: evidence payload kind 불일치 {scenario_id}")
            if (
                not isinstance(payload_count, int)
                or isinstance(payload_count, bool)
                or payload_count < 1
            ):
                errors.append(f"receipt instance: evidence payload count 불일치 {scenario_id}")
                payload_count = 0
            allowed_metrics = (
                REDACTED_EVIDENCE_METRICS.get(payload_kind, set())
                if isinstance(payload_kind, str)
                else set()
            )
            if not isinstance(payload_metrics, dict) or not payload_metrics or not set(
                payload_metrics
            ).issubset(allowed_metrics):
                errors.append(f"receipt instance: evidence payload metric 집합 불일치 {scenario_id}")
            elif any(
                not isinstance(value, int) or isinstance(value, bool) or value < 0
                for value in payload_metrics.values()
            ):
                errors.append(f"receipt instance: evidence payload metric 값 불일치 {scenario_id}")
            elif payload_kind == "SOURCE_STATE_SUMMARY":
                source_state_payload_count += 1
                if set(payload_metrics) != REDACTED_EVIDENCE_METRICS["SOURCE_STATE_SUMMARY"]:
                    errors.append(f"receipt instance: source state metric 집합 불일치 {scenario_id}")
                else:
                    payload_assertions = payload_metrics["assertion_count"]
                    payload_matches = payload_metrics["match_count"]
                    payload_mismatches = payload_metrics["mismatch_count"]
                    payload_incomplete = payload_metrics["incomplete_count"]
                    observation_status = result_record.get("observation_status")
                    if payload_assertions != result_record.get("assertion_count"):
                        errors.append(f"receipt instance: source state assertion 결속 불일치 {scenario_id}")
                    if observation_status == "SOURCE_ASSERTION_MATCH" and (
                        payload_matches != payload_assertions
                        or payload_mismatches != 0
                        or payload_incomplete != 0
                    ):
                        errors.append(f"receipt instance: source state match 의미 불일치 {scenario_id}")
                    if observation_status == "SOURCE_ASSERTION_MISMATCH" and (
                        payload_matches + payload_mismatches != payload_assertions
                        or payload_mismatches < 1
                        or payload_incomplete != 0
                    ):
                        errors.append(f"receipt instance: source state mismatch 의미 불일치 {scenario_id}")
                    if observation_status == "OBSERVATION_INCOMPLETE" and (
                        payload_matches + payload_mismatches > payload_assertions
                        or payload_incomplete < 1
                    ):
                        errors.append(f"receipt instance: source state incomplete 의미 불일치 {scenario_id}")
            payload_artifacts.append(
                (
                    str(payload_kind),
                    redacted_evidence_payload_digest(payload),
                    payload_count,
                )
            )
        if source_state_payload_count != 1:
            errors.append(f"receipt instance: source state payload 정확히 한 개 필요 {scenario_id}")
        observed_artifacts: set[tuple[str, str, int]] = set()
        record_count = 0
        for artifact in artifacts:
            if not isinstance(artifact, dict) or set(artifact) != REDACTED_EVIDENCE_ARTIFACT_KEYS:
                errors.append(f"receipt instance: evidence artifact property 집합 불일치 {scenario_id}")
                continue
            kind = artifact.get("artifact_kind")
            content_sha256 = artifact.get("content_sha256")
            count = artifact.get("record_count")
            if not isinstance(kind, str) or kind not in REDACTED_EVIDENCE_ARTIFACT_KINDS:
                errors.append(f"receipt instance: evidence artifact kind 불일치 {scenario_id}")
            if not isinstance(content_sha256, str) or not sha_pattern.fullmatch(content_sha256):
                errors.append(f"receipt instance: evidence artifact digest 불일치 {scenario_id}")
            if not isinstance(count, int) or isinstance(count, bool) or count < 1:
                errors.append(f"receipt instance: evidence artifact count 불일치 {scenario_id}")
                count = 0
            identity = (str(kind), str(content_sha256), count)
            if identity in observed_artifacts:
                errors.append(f"receipt instance: evidence artifact 중복 {scenario_id}")
            observed_artifacts.add(identity)
            record_count += count
        if sorted(payload_artifacts) != sorted(observed_artifacts):
            errors.append(f"receipt instance: evidence payload와 manifest 결속 불일치 {scenario_id}")
        if receipt_result.get("evidence_record_count") != record_count:
            errors.append(f"receipt instance: evidence record count 불일치 {scenario_id}")
        computed_evidence_digest = redacted_evidence_digest(manifest)
        if receipt_result.get("evidence_digest_sha256") != computed_evidence_digest:
            errors.append(f"receipt instance: evidence digest 불일치 {scenario_id}")

        started_at = _parse_aware_datetime(receipt_result.get("started_at"))
        completed_at = _parse_aware_datetime(receipt_result.get("completed_at"))
        if started_at is None or completed_at is None:
            errors.append(f"receipt instance: scenario 시간 형식 불일치 {scenario_id}")
        elif completed_at < started_at:
            errors.append(f"receipt instance: scenario 시간 역전 {scenario_id}")

    return errors


def _active_surface_text(text: str) -> str:
    return "\n".join(
        line
        for line in text.splitlines()
        if not line.lstrip().startswith(("#", "//", ";"))
    )


def _dotted_name(node: ast.AST, aliases: dict[str, str]) -> str:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value, aliases)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def check_declaration_only_python(
    text: str,
    label: str,
    errors: list[str],
) -> None:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        errors.append(f"{label}: declaration-only Python parse 실패")
        return

    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".")[0]] = alias.name
                if "two_sided_asis_observations" in alias.name.lower():
                    errors.append(f"{label}: 위험 관찰 module import 금지")
                    return
                if alias.name.split(".")[0] not in DECLARATION_ALLOWED_IMPORT_ROOTS:
                    errors.append(
                        f"{label}: declaration-only checker의 process/module 실행 금지 "
                        "(import allowlist 밖)"
                    )
                    return
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imported = f"{module}.{alias.name}".strip(".")
                aliases[alias.asname or alias.name] = imported
                if "two_sided_asis_observations" in imported.lower():
                    errors.append(f"{label}: 위험 관찰 module import 금지")
                    return
                if module.split(".")[0] not in DECLARATION_ALLOWED_IMPORT_ROOTS:
                    errors.append(
                        f"{label}: declaration-only checker의 process/module 실행 금지 "
                        "(import allowlist 밖)"
                    )
                    return

    forbidden_calls = {
        "exec",
        "eval",
        "__import__",
        "builtins.exec",
        "builtins.eval",
        "builtins.__import__",
    }
    forbidden_prefixes = (
        "subprocess.",
        "runpy.",
        "importlib.import_module",
        "asyncio.create_subprocess",
        "multiprocessing.",
        "ctypes.",
        "builtins.exec",
        "builtins.eval",
        "builtins.__import__",
        "os.system",
        "os.popen",
        "os.startfile",
        "os.exec",
        "os.spawn",
        "os.posix_spawn",
    )
    for node in ast.walk(tree):
        dotted = _dotted_name(node, aliases)
        if dotted.startswith(forbidden_prefixes):
            errors.append(f"{label}: declaration-only checker의 process/module 실행 금지")
            return
        if not isinstance(node, ast.Call):
            continue
        call_name = _dotted_name(node.func, aliases)
        if call_name in forbidden_calls:
            errors.append(f"{label}: declaration-only checker의 process/module 실행 금지")
            return
        if (
            call_name == "getattr"
            and len(node.args) >= 2
            and _dotted_name(node.args[0], aliases)
            in {"os", "subprocess", "runpy", "importlib", "asyncio", "builtins"}
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            errors.append(f"{label}: declaration-only checker의 process/module 실행 금지")
            return


def check_declaration_only_javascript(
    text: str,
    label: str,
    errors: list[str],
) -> None:
    active_text = _active_surface_text(text)
    imports = re.findall(
        r"^\s*import(?:[\s\S]*?\sfrom\s*)?[\"']([^\"']+)[\"']\s*;?",
        active_text,
        re.MULTILINE,
    )
    if any(module not in {"node:fs", "node:path", "node:url"} for module in imports):
        errors.append(
            f"{label}: declaration-only checker의 process/module 실행 금지 "
            "(import allowlist 밖)"
        )
        return
    if re.search(
        r"(?:node:child_process|child_process|execa|shelljs|Bun\.spawn|"
        r"Deno\.Command|process\.binding|\beval\s*\(|\bFunction\s*\()",
        active_text,
        re.IGNORECASE,
    ):
        errors.append(f"{label}: declaration-only checker의 process/module 실행 금지")


def check_observation_source_guard(
    text: str,
    label: str,
    errors: list[str],
) -> None:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        errors.append(f"{label}: Python parse 실패")
        return

    allowed_declarations = (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef)
    if not tree.body or not isinstance(tree.body[-1], ast.If):
        errors.append(f"{label}: 최종 __main__ guard 필요")
        return
    for node in tree.body[:-1]:
        if not isinstance(node, allowed_declarations):
            errors.append(f"{label}: import-time 실행 가능 top-level 문장 금지")
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.decorator_list:
                errors.append(f"{label}: import-time decorator 호출 금지")
                return
            evaluated_at_definition = [
                *node.args.defaults,
                *[default for default in node.args.kw_defaults if default is not None],
            ]
            if any(isinstance(item, ast.Call) for value in evaluated_at_definition for item in ast.walk(value)):
                errors.append(f"{label}: import-time decorator/default 호출 금지")
                return

    guard = tree.body[-1]
    assert isinstance(guard, ast.If)
    valid_test = (
        isinstance(guard.test, ast.Compare)
        and isinstance(guard.test.left, ast.Name)
        and guard.test.left.id == "__name__"
        and len(guard.test.ops) == 1
        and isinstance(guard.test.ops[0], ast.Eq)
        and len(guard.test.comparators) == 1
        and isinstance(guard.test.comparators[0], ast.Constant)
        and guard.test.comparators[0].value == "__main__"
    )
    valid_body = (
        len(guard.body) == 1
        and isinstance(guard.body[0], ast.Expr)
        and isinstance(guard.body[0].value, ast.Call)
        and isinstance(guard.body[0].value.func, ast.Name)
        and guard.body[0].value.func.id == "main"
        and not guard.body[0].value.args
        and not guard.body[0].value.keywords
        and not guard.orelse
    )
    if not valid_test or not valid_body:
        errors.append(f"{label}: 최종 __main__ guard는 인자 없는 main()만 호출해야 함")


def _has_runtime_test_bulk_activation(active_text: str) -> bool:
    lines = active_text.splitlines()
    for index in range(len(lines)):
        window = "\n".join(lines[index : index + 8])
        if RUNTIME_TEST_DIRECTORY.search(window) is None:
            continue
        if RUNTIME_TEST_WILDCARD.search(window) is not None:
            return True
        if (
            RUNTIME_TEST_ENUMERATOR.search(window) is not None
            and RUNTIME_TEST_LAUNCHER.search(window) is not None
        ):
            return True

    aliases = {
        match.group(1)
        for match in re.finditer(
            r"^\s*(?:(?:const|let|var)\s+)?\$?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
            r"(?:Path\s*\(\s*)?[\"']?src[\\/]+runtime[\\/]+tests",
            active_text,
            re.IGNORECASE | re.MULTILINE,
        )
    }
    for alias in aliases:
        escaped = re.escape(alias)
        alias_reference = re.compile(
            rf"(?:\$\{{{escaped}\}}|\${escaped}\b|%{escaped}%|\b{escaped}\b)",
            re.IGNORECASE,
        )
        for index in range(len(lines)):
            window = "\n".join(lines[index : index + 8])
            if alias_reference.search(window) is None:
                continue
            if (
                RUNTIME_TEST_ENUMERATOR.search(window) is not None
                and RUNTIME_TEST_LAUNCHER.search(window) is not None
            ):
                return True
    return False


def check_automatic_activation_text(
    text: str,
    label: str,
    errors: list[str],
    *,
    declaration_only: bool = False,
) -> None:
    if declaration_only:
        if label.lower().endswith((".js", ".mjs", ".cjs", ".ts")):
            check_declaration_only_javascript(text, label, errors)
        else:
            check_declaration_only_python(text, label, errors)
        return

    active_text = _active_surface_text(text)
    if RISK_OBSERVATION_ACTIVATION.search(active_text):
        errors.append(f"{label}: 위험 관찰 script 자동 실행 금지")
    if _has_runtime_test_bulk_activation(active_text):
        errors.append(f"{label}: runtime tests wildcard 자동 실행 금지")


def is_automatic_activation_surface(relative: Path) -> bool:
    if relative == OBSERVATION_SOURCE_PATH:
        return False
    if any(part in ACTIVATION_IGNORED_PARTS for part in relative.parts):
        return False

    name = relative.name.lower()
    suffix = relative.suffix.lower()
    if suffix in {
        ".sh",
        ".ps1",
        ".bat",
        ".cmd",
        ".tf",
        ".tftpl",
        ".js",
        ".mjs",
        ".cjs",
        ".ts",
    }:
        return True
    if name in {"package.json", "pyproject.toml", "tox.ini"}:
        return True
    if name.startswith(("dockerfile", "makefile", "taskfile", "noxfile")):
        return True
    if (
        "compose" in name
        and suffix in {".yml", ".yaml"}
    ):
        return True
    if suffix in {".yml", ".yaml"} and relative.parts[:1] == (".github",):
        return True
    if suffix == ".py":
        return relative.parts[:1] in {("scripts",), ("tests",)} or relative.parts[:3] == (
            "src",
            "runtime",
            "tests",
        )
    return False


def read_automatic_activation_surfaces(
    root: Path,
    errors: list[str],
) -> list[tuple[Path, str]]:
    surfaces: list[tuple[Path, str]] = []
    for directory, directory_names, file_names in os.walk(root, topdown=True):
        directory_names[:] = sorted(
            name for name in directory_names if name not in ACTIVATION_IGNORED_PARTS
        )
        base = Path(directory)
        for file_name in sorted(file_names):
            path = base / file_name
            relative = path.relative_to(root)
            if not is_automatic_activation_surface(relative):
                continue
            try:
                surfaces.append((relative, path.read_text(encoding="utf-8")))
            except OSError:
                errors.append(f"automatic activation surface: 파일을 읽을 수 없음 {path}")
    return surfaces


def check(root: Path) -> list[str]:
    parse_errors: list[str] = []
    plan = load_yaml(root / PLAN_PATH, str(PLAN_PATH), parse_errors)
    schema = load_json(root / RECEIPT_SCHEMA_PATH, str(RECEIPT_SCHEMA_PATH), parse_errors)
    activation_surfaces = read_automatic_activation_surfaces(root, parse_errors)
    activation_errors: list[str] = []
    try:
        observation_source = (root / OBSERVATION_SOURCE_PATH).read_text(encoding="utf-8")
    except OSError:
        parse_errors.append(
            f"observation source guard: 파일을 읽을 수 없음 {root / OBSERVATION_SOURCE_PATH}"
        )
    else:
        check_observation_source_guard(
            observation_source,
            OBSERVATION_SOURCE_PATH.as_posix(),
            activation_errors,
        )
    for relative, text in activation_surfaces:
        check_automatic_activation_text(
            text,
            relative.as_posix(),
            activation_errors,
            declaration_only=relative in AUTOMATIC_ACTIVATION_DECLARATION_ONLY,
        )
    return (
        parse_errors
        + check_plan_document(plan, root)
        + check_receipt_schema(schema, "")
        + activation_errors
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    errors = check(args.root.resolve())
    if errors:
        for error in errors:
            print(f"::error::{error}")
        return 1
    print("J-Career observation/receipt source contracts (판정 아님)")
    print(
        f"risk observations: {EXPECTED_SCENARIO_COUNT} planned, "
        "DRAFT_NOT_APPROVED, NOT_EXECUTED"
    )
    print("lab receipt: schema only, no receipt or execution evidence present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
