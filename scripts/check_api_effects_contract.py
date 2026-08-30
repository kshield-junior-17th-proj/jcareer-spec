#!/usr/bin/env python3
"""Validate the source-bound AS-IS operation-effect inventory without starting services."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

from check_api_surface_contract import (
    CONTRACT_PATH as API_SURFACE_PATH,
    ContractError as SurfaceContractError,
    _function_fingerprint,
    _function_map,
    load_contract,
    validate as validate_api_surface,
)


CONTRACT_PATH = Path("src/runtime/contracts/api_effects.json")
TOP_LEVEL_KEYS = {
    "schema_version",
    "contract_id",
    "contract_status",
    "scope",
    "limitations",
    "effect_registry",
    "helper_bindings",
    "operations",
    "ordered_paths",
}
SCOPE_KEYS = {
    "operation_coverage",
    "runtime_verification",
    "effect_semantics",
    "source_binding",
    "cfg_dominance",
    "transitive_helper_closure",
    "compliance_or_risk_decision",
}
EXPECTED_SCOPE = {
    "operation_coverage": "ALL_35_DECLARED_HANDLERS",
    "runtime_verification": "NOT_CURRENT",
    "effect_semantics": "SOURCE_REVIEW_DECLARATION",
    "source_binding": "FUNCTION_AST_SHA256_AND_SELECTED_ORDERED_MARKERS",
    "cfg_dominance": "NOT_PROVEN",
    "transitive_helper_closure": "DECLARED_AND_HELPER_FINGERPRINTED_NOT_AUTOMATICALLY_EXPANDED",
    "compliance_or_risk_decision": "HUMAN_ONLY",
}
REGISTRY_KEYS = {
    "targets",
    "actions",
    "member_models",
    "company_models",
    "outcome_models",
}
EXPECTED_TARGETS = {
    "agent",
    "audit",
    "bedrock",
    "company_db",
    "dynamodb",
    "llm_gateway",
    "member_db",
    "outcome_db",
    "process",
    "prompt_log",
    "redis",
    "structured_log",
    "sqs",
    "transaction",
}
EXPECTED_ACTIONS = {
    "append",
    "call",
    "commit",
    "compute",
    "delete",
    "emit",
    "get",
    "insert",
    "read",
    "rollback",
    "send",
    "setex",
    "update",
}
EXPECTED_MEMBER_MODELS = {"Application", "AuditEvent", "ConsentEvent", "Resume", "User"}
EXPECTED_COMPANY_MODELS = {"Company", "Job"}
EXPECTED_OUTCOME_MODELS = {"OutcomeDataset", "SyntheticDocumentOutcome"}
HELPER_KEYS = {
    "helper_ref",
    "source",
    "source_function_sha256",
    "effect_tags",
}
OPERATION_KEYS = {
    "operation_ref",
    "source_function_sha256",
    "effect_tags",
    "branches",
}
ORDERED_PATH_KEYS = {"path_ref", "ordered_source_markers"}
TAG_SUBJECT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_+.-]*$")
BRANCH_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]*$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_ORDERED_PATHS = {
    "api:recruiter_signup:success",
    "api:candidate_recommendations:cache_hit",
    "api:candidate_recommendations:cache_miss_nonempty_available",
    "api:recruiter_recommendations:cache_hit",
    "api:recruiter_recommendations:cache_miss_nonempty_available",
    "api:recruiter_overview:with_jobs",
    "api:recruiter_pipeline:success",
    "api:admin_audit:success",
    "llm-gateway:explanations:bedrock_live",
}
EXPECTED_HELPER_SOURCES = {
    "api-security:current_user": "src/runtime/api/app/security.py",
    "api-security:require_role": "src/runtime/api/app/security.py",
    "api:audit": "src/runtime/api/app/main.py",
    "api:require_core_consent": "src/runtime/api/app/main.py",
    "api:build_recruiter_review_support": "src/runtime/api/app/main.py",
    "api:recruiter_company": "src/runtime/api/app/main.py",
    "api:recruiter_job": "src/runtime/api/app/main.py",
    "api:get_cached": "src/runtime/api/app/main.py",
    "api:set_cached": "src/runtime/api/app/main.py",
    "api:run_matcher": "src/runtime/api/app/main.py",
    "api:run_explanations": "src/runtime/api/app/main.py",
    "api:_probe_internal_health": "src/runtime/api/app/main.py",
    "api:ai_service_operations_snapshot": "src/runtime/api/app/main.py",
    "api:candidate_historical_observation": "src/runtime/api/app/outcome_store.py",
    "api:outcome_observation_revision": "src/runtime/api/app/outcome_store.py",
    "api:unavailable_historical_observation": "src/runtime/api/app/main.py",
    "api:enqueue_refresh": "src/runtime/api/app/opendart_dispatch.py",
    "agent:calculate_score": "src/runtime/agent/app/main.py",
    "llm-gateway:_prompt_record": "src/runtime/llm_gateway/app/main.py",
    "llm-gateway:_bedrock_explanations": "src/runtime/llm_gateway/app/main.py",
}


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise SurfaceContractError(
            f"{label} keys differ: missing={sorted(expected - set(value))}, "
            f"unknown={sorted(set(value) - expected)}"
        )


def _safe_source_path(root: Path, relative: object) -> Path:
    if not isinstance(relative, str):
        raise SurfaceContractError("source path must be a string")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise SurfaceContractError(f"unsafe source path: {relative}")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    if resolved_root != resolved and resolved_root not in resolved.parents:
        raise SurfaceContractError(f"source path escaped root: {relative}")
    if not resolved.is_file():
        raise SurfaceContractError(f"source path is missing: {relative}")
    return resolved


def _validate_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise SurfaceContractError(f"{label} must be a lowercase SHA-256")
    return value


def _validate_effect_tags(
    value: object, targets: set[str], actions: set[str], label: str
) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SurfaceContractError(f"{label} effect_tags must be a string array")
    tags = list(value)
    if len(tags) != len(set(tags)):
        raise SurfaceContractError(f"{label} contains duplicate effect tags")
    for tag in tags:
        parts = tag.split(":")
        if len(parts) != 3:
            raise SurfaceContractError(f"{label} has malformed effect tag: {tag}")
        target, action, subject = parts
        if target not in targets or action not in actions or TAG_SUBJECT_PATTERN.fullmatch(subject) is None:
            raise SurfaceContractError(f"{label} has unknown effect tag: {tag}")
    return tags


def _function_source(path: Path, function_name: str) -> str:
    source = path.read_text(encoding="utf-8")
    functions = _function_map(path)
    node = functions.get(function_name)
    if node is None or node.end_lineno is None:
        raise SurfaceContractError(f"source function is missing: {path}:{function_name}")
    return "\n".join(source.splitlines()[node.lineno - 1 : node.end_lineno])


def _validate_ordered_markers(source: str, markers: object, path_ref: str) -> None:
    if (
        not isinstance(markers, list)
        or len(markers) < 2
        or any(not isinstance(marker, str) or not marker for marker in markers)
    ):
        raise SurfaceContractError(f"{path_ref} must have at least two non-empty markers")
    cursor = 0
    for marker in markers:
        index = source.find(marker, cursor)
        if index < 0:
            raise SurfaceContractError(
                f"ordered source marker missing or out of order for {path_ref}: {marker}"
            )
        cursor = index + len(marker)


def _has_prefix(tags: list[str], prefix: str) -> bool:
    return any(tag.startswith(prefix) for tag in tags)


def validate(root: Path) -> dict[str, int]:
    root = root.resolve()
    validate_api_surface(root)
    contract = load_contract(root / CONTRACT_PATH)
    _exact_keys(contract, TOP_LEVEL_KEYS, "API effects contract")
    if contract["schema_version"] != "1.0":
        raise SurfaceContractError("unsupported API effects schema_version")
    if contract["contract_id"] != "jcareer-asis-source-effects-v1":
        raise SurfaceContractError("unexpected API effects contract id")
    if contract["contract_status"] != "SOURCE_EFFECT_INVENTORY_NOT_EXECUTION_EVIDENCE":
        raise SurfaceContractError("API effects contract must not claim execution evidence")
    if not isinstance(contract["scope"], dict):
        raise SurfaceContractError("API effects scope must be an object")
    _exact_keys(contract["scope"], SCOPE_KEYS, "API effects scope")
    if contract["scope"] != EXPECTED_SCOPE:
        raise SurfaceContractError("API effects scope declaration changed")
    limitations = contract["limitations"]
    if (
        not isinstance(limitations, list)
        or len(limitations) < 6
        or any(not isinstance(item, str) or not item.strip() for item in limitations)
    ):
        raise SurfaceContractError("API effects limitations must contain at least six strings")

    registry = contract["effect_registry"]
    if not isinstance(registry, dict):
        raise SurfaceContractError("effect_registry must be an object")
    _exact_keys(registry, REGISTRY_KEYS, "effect_registry")
    for field in (
        "targets",
        "actions",
        "member_models",
        "company_models",
        "outcome_models",
    ):
        if not isinstance(registry[field], list) or any(
            not isinstance(item, str) for item in registry[field]
        ):
            raise SurfaceContractError(f"effect_registry {field} must be a string array")
    targets = set(registry["targets"])
    actions = set(registry["actions"])
    if targets != EXPECTED_TARGETS or actions != EXPECTED_ACTIONS:
        raise SurfaceContractError("effect target/action registry changed")
    if set(registry["member_models"]) != EXPECTED_MEMBER_MODELS:
        raise SurfaceContractError("member model registry changed")
    if set(registry["company_models"]) != EXPECTED_COMPANY_MODELS:
        raise SurfaceContractError("company model registry changed")
    if set(registry["outcome_models"]) != EXPECTED_OUTCOME_MODELS:
        raise SurfaceContractError("outcome model registry changed")

    helper_refs: set[str] = set()
    helpers = contract["helper_bindings"]
    if not isinstance(helpers, list) or not helpers:
        raise SurfaceContractError("helper_bindings must be a non-empty array")
    for helper in helpers:
        if not isinstance(helper, dict):
            raise SurfaceContractError("helper binding must be an object")
        _exact_keys(helper, HELPER_KEYS, "helper binding")
        helper_ref = helper["helper_ref"]
        if not isinstance(helper_ref, str) or helper_ref.count(":") != 1:
            raise SurfaceContractError("helper_ref must be service:function")
        if helper_ref in helper_refs:
            raise SurfaceContractError(f"duplicate helper binding: {helper_ref}")
        helper_refs.add(helper_ref)
        function_name = helper_ref.split(":", 1)[1]
        source_path = _safe_source_path(root, helper["source"])
        if EXPECTED_HELPER_SOURCES.get(helper_ref) != helper["source"]:
            raise SurfaceContractError(f"helper source declaration changed: {helper_ref}")
        functions = _function_map(source_path)
        if function_name not in functions:
            raise SurfaceContractError(f"helper function is missing: {helper_ref}")
        declared_hash = _validate_sha256(
            helper["source_function_sha256"], f"helper {helper_ref} fingerprint"
        )
        if declared_hash != _function_fingerprint(functions[function_name]):
            raise SurfaceContractError(f"helper source fingerprint drift: {helper_ref}")
        _validate_effect_tags(helper["effect_tags"], targets, actions, f"helper {helper_ref}")
    if helper_refs != set(EXPECTED_HELPER_SOURCES):
        raise SurfaceContractError("helper binding coverage changed")

    surface = load_contract(root / API_SURFACE_PATH)
    service_sources = {
        service: _safe_source_path(root, declaration["source"])
        for service, declaration in surface["services"].items()
    }
    source_functions = {
        service: _function_map(path) for service, path in service_sources.items()
    }
    expected_refs = [
        f"{item['service']}:{item['operation_id']}" for item in surface["operations"]
    ]
    surface_by_ref = {
        f"{item['service']}:{item['operation_id']}": item for item in surface["operations"]
    }

    operations = contract["operations"]
    if not isinstance(operations, list):
        raise SurfaceContractError("operations must be an array")
    declared_refs: list[str] = []
    operation_by_ref: dict[str, dict[str, Any]] = {}
    for operation in operations:
        if not isinstance(operation, dict):
            raise SurfaceContractError("operation effect entry must be an object")
        _exact_keys(operation, OPERATION_KEYS, "operation effect entry")
        operation_ref = operation["operation_ref"]
        if not isinstance(operation_ref, str) or operation_ref.count(":") != 1:
            raise SurfaceContractError("operation_ref must be service:function")
        if operation_ref in operation_by_ref:
            raise SurfaceContractError(f"duplicate operation effect entry: {operation_ref}")
        if operation_ref not in surface_by_ref:
            raise SurfaceContractError(f"unknown operation effect entry: {operation_ref}")
        declared_refs.append(operation_ref)
        operation_by_ref[operation_ref] = operation
        service, function_name = operation_ref.split(":", 1)
        declared_hash = _validate_sha256(
            operation["source_function_sha256"], f"operation {operation_ref} fingerprint"
        )
        if declared_hash != _function_fingerprint(source_functions[service][function_name]):
            raise SurfaceContractError(f"operation source fingerprint drift: {operation_ref}")
        tags = _validate_effect_tags(
            operation["effect_tags"], targets, actions, f"operation {operation_ref}"
        )
        branches = operation["branches"]
        if (
            not isinstance(branches, dict)
            or not branches
            or any(
                not isinstance(branch, str)
                or BRANCH_PATTERN.fullmatch(branch) is None
                or not isinstance(note, str)
                or not note.strip()
                for branch, note in branches.items()
            )
        ):
            raise SurfaceContractError(f"operation {operation_ref} branches are invalid")

        surface_operation = surface_by_ref[operation_ref]
        auth_mode = surface_operation["auth"]["mode"]
        if auth_mode == "manual_bearer_dependency" and "member_db:read:user_auth" not in tags:
            raise SurfaceContractError(f"authenticated operation omits auth read effect: {operation_ref}")
        checked_calls = set(surface_operation["required_calls"])
        call_tag_prefixes = {
            "audit": "audit:insert:",
            "get_cached": "redis:get:",
            "set_cached": "redis:setex:",
            "run_matcher": "agent:call:",
            "run_explanations": "llm_gateway:call:",
            "ai_service_operations_snapshot": "process:compute:",
            "require_core_consent": "member_db:read:latest_privacy_core_consent",
            "candidate_historical_observation": "outcome_db:read:",
            "outcome_observation_revision": "outcome_db:read:",
            "unavailable_historical_observation": "process:compute:",
        }
        for call, prefix in call_tag_prefixes.items():
            if call in checked_calls and not _has_prefix(tags, prefix):
                raise SurfaceContractError(
                    f"operation effect omits selected call tag for {operation_ref}: {call}"
                )
        function_source = _function_source(service_sources[service], function_name)
        if "db.commit()" in function_source and not _has_prefix(tags, "transaction:commit:"):
            raise SurfaceContractError(f"operation commit effect omitted: {operation_ref}")
        if "db.rollback()" in function_source and not _has_prefix(tags, "transaction:rollback:"):
            raise SurfaceContractError(f"operation rollback effect omitted: {operation_ref}")

    if declared_refs != expected_refs:
        raise SurfaceContractError("operation effect coverage/order differs from API surface")
    if len(declared_refs) != 35:
        raise SurfaceContractError("expected exactly 35 operation effect entries")

    ordered_paths = contract["ordered_paths"]
    if not isinstance(ordered_paths, list):
        raise SurfaceContractError("ordered_paths must be an array")
    path_refs: set[str] = set()
    for path in ordered_paths:
        if not isinstance(path, dict):
            raise SurfaceContractError("ordered path must be an object")
        _exact_keys(path, ORDERED_PATH_KEYS, "ordered path")
        path_ref = path["path_ref"]
        if not isinstance(path_ref, str) or path_ref.count(":") != 2:
            raise SurfaceContractError("path_ref must be service:operation:branch")
        if path_ref in path_refs:
            raise SurfaceContractError(f"duplicate ordered path: {path_ref}")
        path_refs.add(path_ref)
        service, function_name, branch = path_ref.split(":", 2)
        operation_ref = f"{service}:{function_name}"
        operation = operation_by_ref.get(operation_ref)
        if operation is None or branch not in operation["branches"]:
            raise SurfaceContractError(f"ordered path references unknown branch: {path_ref}")
        source = _function_source(service_sources[service], function_name)
        _validate_ordered_markers(source, path["ordered_source_markers"], path_ref)
    if path_refs != EXPECTED_ORDERED_PATHS:
        raise SurfaceContractError("critical ordered path coverage changed")

    return {
        "operations": len(operations),
        "helpers": len(helpers),
        "ordered_paths": len(ordered_paths),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root",
    )
    args = parser.parse_args()
    try:
        result = validate(args.root)
    except (OSError, UnicodeError, json.JSONDecodeError, SyntaxError, SurfaceContractError) as exc:
        print(f"::error::{exc}")
        return 1
    print(
        "API source effects: PASS "
        f"({result['operations']} operations, {result['helpers']} helpers, "
        f"{result['ordered_paths']} selected paths; runtime not current)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
