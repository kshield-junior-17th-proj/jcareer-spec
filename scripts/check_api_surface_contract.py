#!/usr/bin/env python3
"""Check the source-declared J-Career AS-IS API surface without starting services."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any


CONTRACT_PATH = Path("src/runtime/contracts/api_surface.json")
AUTH_SOURCE_PATH = Path("src/runtime/api/app/security.py")
ORM_MODEL_SOURCE_PATH = Path("src/runtime/api/app/models.py")
WEB_APP_SOURCE_PATH = Path("src/runtime/web/src/App.jsx")
WEB_API_SOURCE_PATH = Path("src/runtime/web/src/api.js")
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
CHECKED_CALLS = {
    "ai_service_operations_snapshot",
    "audit",
    "build_recruiter_review_support",
    "candidate_historical_observation",
    "get_cached",
    "outcome_observation_revision",
    "recruiter_company",
    "recruiter_job",
    "require_core_consent",
    "require_failure_injection_enabled",
    "run_explanations",
    "run_matcher",
    "set_cached",
    "unavailable_historical_observation",
}
TOP_LEVEL_KEYS = {
    "schema_version",
    "contract_id",
    "contract_status",
    "scope",
    "limitations",
    "services",
    "model_signatures",
    "model_implementation_sha256",
    "model_extends",
    "validation_helper_sha256",
    "company_status_gate_absence_sha256",
    "recommendation_degradation",
    "two_sided_data_lifecycle",
    "operations",
}
SCOPE_KEYS = {
    "dataset",
    "runtime_verification",
    "aws_deployment",
    "openapi_security_scheme",
    "bearer_role_source",
    "wire_error_code",
    "response_schema_state",
    "behavioral_preconditions_state",
    "transitive_error_contract_state",
    "required_calls_field_semantics",
}
SERVICE_KEYS = {
    "source",
    "exposure",
    "route_exposure_default",
    "operation_groups",
    "route_entries",
}
OPERATION_KEYS = {
    "operation_id",
    "service",
    "routes",
    "request_body_model",
    "path_params",
    "query_params",
    "auth",
    "tenant_mode",
    "company_status_gate_enforced",
    "required_calls",
    "direct_error_statuses",
    "response_annotation",
    "verification_level",
}
AUTH_KEYS = {"mode", "roles"}
ROUTE_KEYS = {"method", "path", "success_status"}
ALLOWED_TENANT_MODES = {
    "none",
    "self",
    "identity_link_lookup",
    "split_write_new_company",
    "linked_company",
    "job_company_equality",
    "application_job_company_equality",
    "global_admin",
    "global_admin_filter",
    "caller_supplied_subjects",
}
EXPECTED_SCOPE = {
    "dataset": "SYNTHETIC_ONLY",
    "runtime_verification": "NOT_CURRENT",
    "aws_deployment": "NOT_CLAIMED",
    "openapi_security_scheme": "NOT_DECLARED",
    "bearer_role_source": "MEMBER_DB_CURRENT_USER",
    "wire_error_code": False,
    "response_schema_state": "MIXED_OPEN_OBJECT_AND_STRICT_RESPONSE_MODELS",
    "behavioral_preconditions_state": "SELECTED_SOURCE_CALLS_ONLY_NOT_FULLY_ENUMERATED",
    "transitive_error_contract_state": "NOT_ENUMERATED_V1",
    "required_calls_field_semantics": "LEGACY_FIELD_NAME_AST_SYMBOL_PRESENCE_NOT_BRANCH_EXECUTION",
}
EXPECTED_DEGRADATION = {
    "applies_to": ["api:candidate_recommendations", "api:recruiter_recommendations"],
    "matcher_unavailable_or_invalid": {
        "http_status": 503,
        "recommendation_list_returned": False,
    },
    "explanation_unavailable_or_invalid": {
        "http_status": 200,
        "recommendation_list_and_scores_retained": True,
        "explanation_status": "UNAVAILABLE_PROVIDER",
        "legacy_umbrella_causes": [
            "API_TO_GATEWAY_CONNECTION_OR_TIMEOUT",
            "GATEWAY_HTTP_ERROR",
            "RESPONSE_JSON_OR_CONTRACT_INVALID",
            "GATEWAY_OR_EXTERNAL_PROVIDER_PATH_UNAVAILABLE",
        ],
        "external_provider_failure_asserted": False,
    },
    "cache_read_unavailable_or_invalid": {
        "http_status": 200,
        "behavior": "COMPUTE_AS_CACHE_MISS",
    },
    "cache_write_unavailable": {
        "http_status": 200,
        "behavior": "RETURN_COMPUTED_RESPONSE_WITHOUT_CACHE_PERSISTENCE",
    },
    "verification_level": "SOURCE_BRANCH_STATIC_ONLY",
}
TWO_SIDED_DATA_LIFECYCLE_KEYS = {
    "verification_level",
    "logical_store_boundary",
    "candidate_account",
    "company_account",
    "application_material",
    "audit_reconstructability",
    "cache_payload_validation",
    "public_job_detail",
    "authorization_denial_audit",
    "session_identity",
    "cross_store_write_atomicity",
    "consent_explanation_matrix",
    "explanation_data_flow",
    "human_decisions_required",
    "source_function_sha256",
}
EXPECTED_TWO_SIDED_DATA_LIFECYCLE = {
    "verification_level": "SOURCE_STATE_AND_FUNCTION_FINGERPRINTS_ONLY",
    "logical_store_boundary": "CROSS_CHECKED_BY_RUNTIME_INFRA_CONTRACT",
    "candidate_account": {
        "signup_route": "SOURCE_PRESENT",
        "withdrawal_route": "SOURCE_PRESENT",
        "core_consent_revoke_route": "SOURCE_PRESENT",
        "enterprise_read_consent_gate": "NOT_PRESENT_IN_SOURCE",
        "cache_and_prompt_erasure_on_withdrawal": "NOT_PRESENT_IN_SOURCE",
    },
    "company_account": {
        "signup_route": "SOURCE_PRESENT",
        "identity_link_model": "RECRUITER_USER_TO_COMPANY_LOGICAL_REFERENCE",
        "signup_recruiter_creation": "ONE_RECRUITER_WITH_NEW_COMPANY",
        "company_recruiter_cardinality_constraint": "NOT_PRESENT_IN_SOURCE",
        "signup_initial_status": "MODEL_DEFAULT_APPROVED_WITHOUT_REVIEW_TRANSITION",
        "overview_boundary_declaration": "SOURCE_PRESENT",
        "organization_membership": "NOT_PRESENT_IN_SOURCE",
        "invite_role_lifecycle": "NOT_PRESENT_IN_SOURCE",
        "withdrawal_route": "NOT_PRESENT_IN_SOURCE",
        "ownership_transfer_route": "NOT_PRESENT_IN_SOURCE",
        "company_consent_route": "NOT_PRESENT_IN_SOURCE",
        "company_status_transition_route": "NOT_PRESENT_IN_SOURCE",
        "company_status_actor_model": "NOT_PRESENT_IN_SOURCE",
        "company_status_gate": "NOT_ENFORCED_IN_SOURCE",
    },
    "application_material": {
        "binding": "CURRENT_REFERENCES_NO_IMMUTABLE_APPLICATION_SNAPSHOT",
        "candidate_material": "CURRENT_RESUME_AT_READ_TIME",
        "job_material": "CURRENT_JOB_AT_READ_TIME",
        "company_material": "CURRENT_COMPANY_PROFILE_AT_READ_TIME",
        "missing_resume_pipeline_behavior": "ITEM_OMITTED_WITHOUT_DEGRADED_RECORD",
    },
    "audit_reconstructability": {
        "recommendation_correlation_response": "SOURCE_PRESENT_ON_CACHE_MISS",
        "gateway_prompt_record": "CONDITIONAL_ON_GATEWAY_HANDLER_ENTRY",
        "recommendation_execution_audit_event": "NOT_PRESENT_IN_SOURCE",
        "recommendation_cache_hit_audit_event": "NOT_PRESENT_IN_SOURCE",
        "durable_match_run_record": "NOT_PRESENT_IN_SOURCE",
        "application_submitted_target": "JOB_ID_ONLY",
        "application_status_change_detail": "APPLICATION_ID_AND_NEW_STATUS_ONLY",
    },
    "cache_payload_validation": {
        "top_level_object": True,
        "available_status": True,
        "items_array": True,
        "each_item_object": True,
        "provider_config_fingerprint": True,
        "explanation_attempt_object": True,
        "current_request_freshness_marker": True,
        "operation_specific_item_keys": False,
        "requested_subject_set_equality": False,
        "consent_policy_snapshot_bound": False,
        "tenant_or_customer_side_bound": False,
        "generated_at_bound": False,
        "system_prompt_revision_bound": False,
        "inference_config_bound": False,
        "provider_live_flag_bound": False,
        "content_integrity_mac_bound": False,
        "ttl_seconds": 86400,
    },
    "public_job_detail": {
        "closed_job_detail_route": "PUBLIC_SOURCE_PRESENT",
        "get_job_status_filter": "NOT_PRESENT_IN_SOURCE",
        "company_profile_embedded": True,
    },
    "authorization_denial_audit": {
        "actor_company_id_recorded": True,
        "target_object_ref_recorded": True,
        "target_company_snapshot": "NOT_PRESENT_IN_SOURCE",
        "admin_company_filter_semantics": "ACTOR_COMPANY_ONLY",
    },
    "session_identity": {
        "browser_credential_storage": "LOCAL_STORAGE_BEARER_TOKEN",
        "browser_display_identity_storage": "LOCAL_STORAGE_USER_JSON",
        "browser_startup_identity_source": "LOCAL_STORAGE_ONLY_AUTH_ME_NOT_CALLED",
        "browser_route_guard_role_source": "LOCAL_STORAGE_USER_ROLE",
        "browser_startup_role_schema_validation": False,
        "browser_protected_route_role_allowlist_check": True,
        "browser_cross_tab_storage_sync": "NOT_PRESENT_IN_SOURCE",
        "api_identity_source": "ACTIVE_MEMBER_DB_USER_BY_TOKEN_SUBJECT",
        "api_role_source": "MEMBER_DB_USER_ROLE_NOT_TOKEN_ROLE_CLAIM",
        "token_format": "CUSTOM_TWO_PART_HMAC_SHA256",
        "signing_key_source": "SESSION_SIGNING_KEY_ENV_WITH_FIXED_SYNTHETIC_FALLBACK",
        "default_ttl_seconds": 43200,
        "issued_claims": ["sub", "role", "exp"],
        "claims_explicitly_validated_before_user_lookup": ["exp"],
        "subject_schema_validation_before_lookup": "NOT_PRESENT_IN_SOURCE",
        "missing_subject_behavior": "KEY_ERROR_OUTSIDE_PARSE_TOKEN_GUARD",
        "issued_at_claim": False,
        "token_id_claim": False,
        "server_session_registry": False,
        "server_logout_or_revocation_route": False,
        "refresh_route": False,
        "client_logout_effect": "LOCAL_STORAGE_CLEAR_ONLY",
        "unauthorized_dirty_draft_behavior": "USER_CAN_CANCEL_LOCAL_SESSION_CLEAR",
        "client_401_signal_order": "BEFORE_RESPONSE_BODY_DECODE",
        "client_response_decode_failures": [
            "RESPONSE_BODY_READ_FAILED",
            "EMPTY_RESPONSE_BODY",
            "INVALID_JSON_RESPONSE",
        ],
        "client_decode_failure_raw_body_retained": False,
        "client_decode_verification": "PURE_RESPONSE_STUB_ONLY_NOT_RUNTIME",
    },
    "cross_store_write_atomicity": {
        "session_shape": "MULTI_BIND_ONE_SESSION",
        "two_phase_commit": "NOT_CONFIGURED_IN_SOURCE",
        "cross_database_atomic_commit": False,
        "partial_commit_observed": False,
        "fault_injection": "NOT_PRESENT",
        "operation_id": "NOT_PRESENT_IN_SOURCE",
        "idempotency_key": "NOT_PRESENT_IN_SOURCE",
        "compensation": "NOT_PRESENT_IN_SOURCE",
        "reconciliation": "NOT_PRESENT_IN_SOURCE",
        "outbox": "NOT_PRESENT_IN_SOURCE",
    },
    "consent_explanation_matrix": {
        "privacy_core_collected_items": [
            "name",
            "email",
            "phone",
            "birth_date",
            "address",
            "education",
            "career",
            "certificates",
        ],
        "privacy_core_purposes": [
            "member_management",
            "job_service",
            "ai_recommendation",
        ],
        "matcher_candidate_fields": [
            "desired_role",
            "skills",
            "years_experience",
        ],
        "gateway_candidate_context_fields": [
            "name",
            "phone",
            "email",
            "birthdate",
            "address",
            "school",
            "certificates",
            "projects",
            "self_intro",
        ],
        "exact_name_gaps_requiring_human_mapping": [
            "birthdate",
            "desired_role",
            "projects",
            "school",
            "self_intro",
            "skills",
            "years_experience",
        ],
        "candidate_alias_pairs_not_semantically_approved": [
            "birth_date<->birthdate",
            "career<->years_experience",
            "education<->school",
        ],
        "delete_privacy_core_revoke_shape": "REUSES_RECORD_CONSENT_CATALOG_AND_DEFAULT_POLICY_VERSION_2026_05",
        "account_withdrawal_revoke_shape": "POLICY_VERSION_2026_05_WITH_EMPTY_ITEMS_AND_PURPOSES",
        "consent_event_to_gateway_prompt_link": "NOT_PRESENT_IN_SOURCE",
        "consent_event_to_recommendation_audit_link": "NOT_PRESENT_IN_SOURCE",
    },
    "explanation_data_flow": {
        "candidate_fields_prepared": [
            "address",
            "birthdate",
            "certificates",
            "email",
            "name",
            "phone",
            "projects",
            "school",
            "self_intro",
        ],
        "classified_pii_fields": [
            "address",
            "birthdate",
            "email",
            "name",
            "phone",
            "school",
        ],
        "current_request_prepared_field_set": "EXACT_SOURCE_CONSTANTS",
        "cache_origin_prepared_field_set": "NOT_VERIFIED_EMPTY_DISCLOSURE",
        "empty_subject_prepared_field_set": "NOT_PREPARED",
        "provider_config_bound_to_cache_key": True,
        "outcome_dataset_version_bound_to_candidate_cache_key": True,
        "provider_config_fingerprint_validated": True,
        "warm_cache_provider_state_revalidated": False,
        "warm_cache_disclosure_state": "CACHE_HIT_PROVIDER_NOT_REVALIDATED",
        "gateway_terminal_outcome_record": "NOT_PRESENT_IN_SOURCE",
        "external_provider_receipt_state": "NOT_ASSERTED",
        "prompt_hash_scope": "ITEM_MATERIAL_EXCLUDES_SYSTEM_PROVIDER_MODEL_INFERENCE_AND_CORRELATION",
        "prompt_hash_validation": "FORMAT_ONLY_AT_API",
    },
    "human_decisions_required": [
        "company-recruiter-cardinality-membership-lifecycle-and-ownership",
        "enterprise-read-effect-of-candidate-consent",
        "application-time-immutable-snapshots",
        "recommendation-run-audit-persistence",
        "operation-specific-cache-schema",
        "closed-job-public-detail-retention",
        "authorization-denial-target-tenant-audit-shape",
        "cross-store-reconciliation-or-outbox",
        "cached-explanation-during-provider-outage",
        "terminal-provider-attempt-record-retention-and-access",
        "consent-catalog-field-alias-mapping-and-revoke-shape",
        "project-field-consent-catalog-and-provider-purpose-mapping",
        "browser-startup-current-identity-revalidation-and-cross-tab-session-policy",
        "server-session-revocation-refresh-and-signing-key-policy",
        "malformed-signed-token-error-normalization",
    ],
}
EXPECTED_SERVICES = {
    "api": {
        "source": "src/runtime/api/app/main.py",
        "exposure": "EXTERNAL_BUSINESS_API_SOURCE",
        "route_exposure_default": "source_route_only",
        "operation_groups": 30,
        "route_entries": 30,
    },
    "agent": {
        "source": "src/runtime/agent/app/main.py",
        "exposure": "INTERNAL_INTENT_WITH_UNAUTHENTICATED_ALIASES",
        "route_exposure_default": None,
        "operation_groups": 3,
        "route_entries": 6,
    },
    "llm-gateway": {
        "source": "src/runtime/llm_gateway/app/main.py",
        "exposure": "INTERNAL_INTENT_WITH_UNAUTHENTICATED_ALIASES",
        "route_exposure_default": None,
        "operation_groups": 2,
        "route_entries": 4,
    },
}
EXPECTED_TENANT_BOUNDARIES = {
    ("api", "health"): ("none", None),
    ("api", "runtime_info"): ("none", None),
    ("api", "signup"): ("none", None),
    ("api", "recruiter_signup"): ("split_write_new_company", False),
    ("api", "login"): ("identity_link_lookup", False),
    ("api", "me"): ("identity_link_lookup", False),
    ("api", "record_consent"): ("self", None),
    ("api", "list_consents"): ("self", None),
    ("api", "revoke_consent"): ("self", None),
    ("api", "get_resume"): ("self", None),
    ("api", "save_resume"): ("self", None),
    ("api", "list_jobs"): ("none", False),
    ("api", "get_job"): ("none", False),
    ("api", "apply_to_job"): ("self", False),
    ("api", "candidate_applications"): ("self", False),
    ("api", "candidate_recommendations"): ("self", False),
    ("api", "withdraw_candidate"): ("self", None),
    ("api", "recruiter_jobs"): ("linked_company", False),
    ("api", "recruiter_overview"): ("linked_company", False),
    ("api", "get_recruiter_company_profile"): ("linked_company", False),
    ("api", "update_recruiter_company_profile"): ("linked_company", False),
    ("api", "refresh_recruiter_company_opendart"): ("linked_company", False),
    ("api", "collect_recruiter_company_opendart"): ("linked_company", False),
    ("api", "create_recruiter_job"): ("linked_company", False),
    ("api", "update_recruiter_job"): ("job_company_equality", False),
    ("api", "recruiter_pipeline"): ("job_company_equality", False),
    ("api", "update_application_status"): ("application_job_company_equality", False),
    ("api", "recruiter_recommendations"): ("job_company_equality", False),
    ("api", "admin_ai_operations"): ("global_admin", None),
    ("api", "admin_audit"): ("global_admin_filter", None),
    ("agent", "health"): ("none", None),
    ("agent", "match_candidates"): ("caller_supplied_subjects", None),
    ("agent", "match_jobs"): ("caller_supplied_subjects", None),
    ("llm-gateway", "health"): ("none", None),
    ("llm-gateway", "explanations"): ("caller_supplied_subjects", None),
}
EXPECTED_TENANT_SOURCE_MARKERS = {
    ("api", "recruiter_signup"): (
        "company = Company(",
        "company_id=company.id",
    ),
    ("api", "login"): (
        "db.get(Company, user.company_id) if user.company_id else None",
    ),
    ("api", "me"): (
        "db.get(Company, user.company_id) if user.company_id else None",
    ),
    ("api", "record_consent"): ("ConsentEvent(user_id=user.id",),
    ("api", "list_consents"): ("ConsentEvent.user_id == user.id",),
    ("api", "revoke_consent"): ("record_consent(request, db, user)",),
    ("api", "get_resume"): ("Resume.user_id == user.id",),
    ("api", "save_resume"): ("Resume.user_id == user.id", "Resume(user_id=user.id)"),
    ("api", "apply_to_job"): (
        "Resume.user_id == user.id",
        "Application.candidate_id == user.id",
        "Application(job_id=job_id, candidate_id=user.id)",
    ),
    ("api", "candidate_applications"): ("Application.candidate_id == user.id",),
    ("api", "candidate_recommendations"): ("Resume.user_id == user.id",),
    ("api", "withdraw_candidate"): (
        "Application.candidate_id == user.id",
        "Resume.user_id == user.id",
        "user.active = False",
    ),
    ("api", "recruiter_jobs"): ("Job.company_id == user.company_id",),
    ("api", "recruiter_overview"): ("Job.company_id == user.company_id",),
    ("api", "create_recruiter_job"): ("Job(company_id=user.company_id",),
    ("api", "update_application_status"): (
        "db.get(Job, application.job_id)",
        "job.company_id != user.company_id",
    ),
    ("api", "admin_audit"): ("AuditEvent.company_id == company_id",),
}


class ContractError(ValueError):
    """Raised when the declaration and source no longer agree."""


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_contract(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicate_keys)
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read API contract: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError("API contract root must be an object")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], where: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ContractError(
            f"{where} keys differ: missing={sorted(expected - actual)}, "
            f"unknown={sorted(actual - expected)}"
        )


def _literal_status(decorator: ast.Call) -> int:
    for keyword in decorator.keywords:
        if keyword.arg == "status_code":
            try:
                value = ast.literal_eval(keyword.value)
            except (ValueError, TypeError) as exc:
                raise ContractError("route status_code must be a literal integer") from exc
            if not isinstance(value, int):
                raise ContractError("route status_code must be a literal integer")
            return value
    return 200


def _route_declarations(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    for decorator in function.decorator_list:
        if not (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and isinstance(decorator.func.value, ast.Name)
            and decorator.func.value.id == "app"
            and decorator.func.attr in HTTP_METHODS
        ):
            continue
        try:
            path = ast.literal_eval(decorator.args[0])
        except (IndexError, ValueError, TypeError) as exc:
            raise ContractError("route path must be a literal string") from exc
        if not isinstance(path, str):
            raise ContractError("route path must be a literal string")
        routes.append(
            {
                "method": decorator.func.attr.upper(),
                "path": path,
                "success_status": _literal_status(decorator),
            }
        )
    return routes


def _argument_defaults(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[tuple[ast.arg, ast.expr | None]]:
    arguments = function.args.args
    defaults: list[ast.expr | None] = [None] * (len(arguments) - len(function.args.defaults))
    defaults.extend(function.args.defaults)
    return list(zip(arguments, defaults))


def _request_body_model(function: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    models = []
    for argument, _ in _argument_defaults(function):
        annotation = ast.unparse(argument.annotation) if argument.annotation else ""
        if annotation.endswith("Request"):
            models.append(annotation)
    if len(models) > 1:
        raise ContractError(f"{function.name} has more than one request body model")
    return models[0] if models else None


def _path_params(routes: list[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    for route in routes:
        for name in re.findall(r"\{([^{}]+)\}", route["path"]):
            if name not in result:
                result.append(name)
    return result


def _query_params(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    result = []
    for argument, default in _argument_defaults(function):
        if not (
            isinstance(default, ast.Call)
            and isinstance(default.func, ast.Name)
            and default.func.id == "Query"
        ):
            continue
        annotation = ast.unparse(argument.annotation) if argument.annotation else ""
        result.append(f"{argument.arg}:{annotation}:{ast.unparse(default)}")
    return result


def _auth(function: ast.FunctionDef | ast.AsyncFunctionDef, service: str) -> dict[str, Any]:
    roles: list[str] = []
    authenticated = False
    for _, default in _argument_defaults(function):
        if not (
            isinstance(default, ast.Call)
            and isinstance(default.func, ast.Name)
            and default.func.id == "Depends"
            and default.args
        ):
            continue
        dependency = default.args[0]
        if isinstance(dependency, ast.Name) and dependency.id == "current_user":
            authenticated = True
            roles.append("authenticated")
        elif (
            isinstance(dependency, ast.Call)
            and isinstance(dependency.func, ast.Name)
            and dependency.func.id == "require_role"
            and dependency.args
        ):
            authenticated = True
            for role_node in dependency.args:
                try:
                    role = ast.literal_eval(role_node)
                except (ValueError, TypeError) as exc:
                    raise ContractError(f"{function.name} role must be a literal") from exc
                if not isinstance(role, str):
                    raise ContractError(f"{function.name} role must be a string")
                if role in roles:
                    raise ContractError(f"{function.name} role must not be duplicated")
                roles.append(role)
    if authenticated:
        return {"mode": "manual_bearer_dependency", "roles": roles}
    if service == "api":
        return {"mode": "public", "roles": []}
    return {"mode": "none_internal_intent", "roles": []}


def _called_symbols(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    calls: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        else:
            continue
        if name in CHECKED_CALLS:
            calls.add(name)
    return sorted(calls)


def _direct_error_statuses(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[int]:
    statuses: set[int] = set()
    for node in ast.walk(function):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "HTTPException"
        ):
            continue
        for keyword in node.keywords:
            if keyword.arg != "status_code":
                continue
            try:
                status = ast.literal_eval(keyword.value)
            except (ValueError, TypeError) as exc:
                raise ContractError(f"{function.name} HTTPException status must be literal") from exc
            if not isinstance(status, int):
                raise ContractError(f"{function.name} HTTPException status must be integer")
            statuses.add(status)
    return sorted(statuses)


def extract_operations(service: str, source_path: Path) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    except (OSError, SyntaxError) as exc:
        raise ContractError(f"cannot parse {source_path}: {exc}") from exc
    result: list[dict[str, Any]] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        routes = _route_declarations(node)
        if not routes:
            continue
        result.append(
            {
                "operation_id": node.name,
                "service": service,
                "routes": routes,
                "request_body_model": _request_body_model(node),
                "path_params": _path_params(routes),
                "query_params": _query_params(node),
                "auth": _auth(node, service),
                "required_calls": _called_symbols(node),
                "direct_error_statuses": _direct_error_statuses(node),
                "response_annotation": ast.unparse(node.returns) if node.returns else None,
            }
        )
    return result


def _pydantic_model_nodes(source_path: Path) -> list[ast.ClassDef]:
    try:
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    except (OSError, SyntaxError) as exc:
        raise ContractError(f"cannot parse {source_path}: {exc}") from exc
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    model_names: set[str] = set()
    changed = True
    while changed:
        changed = False
        for node in classes:
            bases = {ast.unparse(base) for base in node.bases}
            if "BaseModel" in bases or bases & model_names:
                if node.name not in model_names:
                    model_names.add(node.name)
                    changed = True
    return [node for node in classes if node.name in model_names]


def extract_model_signatures(service: str, source_path: Path) -> dict[str, str]:
    signatures: dict[str, str] = {}
    for node in _pydantic_model_nodes(source_path):
        fields: list[str] = []
        for member in node.body:
            if not isinstance(member, ast.AnnAssign) or not isinstance(member.target, ast.Name):
                continue
            annotation = ast.unparse(member.annotation)
            default = ast.unparse(member.value) if member.value is not None else "<required>"
            fields.append(f"{member.target.id}:{annotation}={default}")
        key = f"{service}:{node.name}"
        if key in signatures:
            raise ContractError(f"duplicate Pydantic model: {key}")
        signatures[key] = "; ".join(fields)
    return signatures


def extract_model_fingerprints(service: str, source_path: Path) -> dict[str, str]:
    return {
        f"{service}:{node.name}": hashlib.sha256(
            ast.dump(node, include_attributes=False).encode("utf-8")
        ).hexdigest()
        for node in _pydantic_model_nodes(source_path)
    }


def extract_model_extends(service: str, source_path: Path) -> dict[str, list[str]]:
    nodes = _pydantic_model_nodes(source_path)
    names = {node.name for node in nodes}
    result: dict[str, list[str]] = {}
    for node in nodes:
        inherited = [
            f"{service}:{base_name}"
            for base_name in (ast.unparse(base) for base in node.bases)
            if base_name in names
        ]
        if inherited:
            result[f"{service}:{node.name}"] = inherited
    return result


def _function_fingerprint(function: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    return hashlib.sha256(ast.dump(function, include_attributes=False).encode("utf-8")).hexdigest()


def _company_model_contract(root: Path) -> tuple[ast.ClassDef, str]:
    source_path = root / ORM_MODEL_SOURCE_PATH
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    company = next(
        (node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Company"),
        None,
    )
    if company is None:
        raise ContractError("Company ORM model missing")
    status_assignment = next(
        (
            node
            for node in company.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "status"
        ),
        None,
    )
    if status_assignment is None or not isinstance(status_assignment.value, ast.Call):
        raise ContractError("Company.status ORM assignment missing")
    default_keyword = next(
        (keyword.value for keyword in status_assignment.value.keywords if keyword.arg == "default"),
        None,
    )
    if not isinstance(default_keyword, ast.Constant) or default_keyword.value != "approved":
        raise ContractError("Company.status signup default changed from approved")
    fingerprint = hashlib.sha256(
        ast.dump(company, include_attributes=False).encode("utf-8")
    ).hexdigest()
    return company, fingerprint


def _validate_auth_source(root: Path) -> None:
    auth_path = root / AUTH_SOURCE_PATH
    try:
        auth_source = auth_path.read_text(encoding="utf-8")
        functions = _function_map(auth_path)
    except (OSError, SyntaxError) as exc:
        raise ContractError(f"cannot parse auth source: {exc}") from exc
    required_functions = {"issue_token", "parse_token", "current_user", "require_role"}
    if not required_functions <= set(functions):
        raise ContractError("auth dependency functions missing")
    issue_source = ast.unparse(functions["issue_token"])
    parse_source = ast.unparse(functions["parse_token"])
    current_source = ast.unparse(functions["current_user"])
    role_source = ast.unparse(functions["require_role"])
    module_markers = (
        'TOKEN_SECRET = os.getenv("SESSION_SIGNING_KEY", "synthetic-local-session-key-change-me")',
        'TOKEN_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "43200"))',
    )
    issue_markers = (
        "'sub': user.id",
        "'role': user.role",
        "'exp': int(time.time()) + TOKEN_TTL_SECONDS",
        "hmac.new(TOKEN_SECRET.encode(), body.encode(), hashlib.sha256)",
    )
    parse_markers = (
        "body, supplied_signature = token.split('.', 1)",
        "hmac.compare_digest(expected, supplied_signature)",
        "int(payload['exp']) < int(time.time())",
        "return payload",
    )
    current_markers = (
        "payload = parse_token",
        "db.get(User, str(payload['sub']))",
        "not user.active",
        "return user",
    )
    role_markers = (
        "Depends(current_user)",
        "user.role not in roles",
        "status_code=403",
    )
    if any(marker not in auth_source for marker in module_markers):
        raise ContractError("auth session key or TTL source marker drift")
    if any(marker not in issue_source for marker in issue_markers):
        raise ContractError("issued token source marker drift")
    if any(marker not in parse_source for marker in parse_markers):
        raise ContractError("parsed token source marker drift")
    if any(claim in issue_source for claim in ("'iat'", "'jti'")):
        raise ContractError("issued token claim set changed")
    if "payload['sub']" in parse_source:
        raise ContractError("token subject validation source state changed")
    if any(marker not in current_source for marker in current_markers):
        raise ContractError("current_user no longer resolves active member DB user from token subject")
    if any(marker not in role_source for marker in role_markers):
        raise ContractError("require_role no longer compares the member DB user role")


def _validate_web_session_source(root: Path) -> None:
    try:
        app_source = (root / WEB_APP_SOURCE_PATH).read_text(encoding="utf-8")
        api_source = (root / WEB_API_SOURCE_PATH).read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractError(f"cannot read web session source: {exc}") from exc
    app_markers = (
        'localStorage.getItem("jcareer_token")',
        'localStorage.getItem("jcareer_user")',
        'localStorage.removeItem("jcareer_token")',
        'localStorage.removeItem("jcareer_user")',
        "useState(readStoredSession)",
        "roles.includes(user.role)",
        'window.addEventListener("jcareer:unauthorized", clearExpiredSession)',
        ') return;\n      unsaved?.allowNextNavigation("/login")',
    )
    api_markers = (
        'localStorage.getItem("jcareer_token")',
        'headers.set("Authorization", `Bearer ${token}`)',
        "response.status === 401",
        "&& token",
        "&& readStoredToken() === token",
        'window.dispatchEvent(new Event("jcareer:unauthorized"))',
        "export async function decodeResponsePayload(response)",
        '"RESPONSE_BODY_READ_FAILED"',
        '"EMPTY_RESPONSE_BODY"',
        '"INVALID_JSON_RESPONSE"',
        "responseFailureMetadata(response, \"INVALID_JSON_RESPONSE\")",
        "DEFAULT_REQUEST_TIMEOUT_MS",
        'error_code: "REQUEST_TIMEOUT"',
        'error_code: "REQUEST_ABORTED"',
        'error_code: "NETWORK_UNAVAILABLE"',
    )
    if any(marker not in app_source for marker in app_markers):
        raise ContractError("web local session source marker drift")
    if any(marker not in api_source for marker in api_markers):
        raise ContractError("web bearer request source marker drift")
    token_check_index = api_source.find("readStoredToken() === token")
    signal_index = api_source.find(
        'window.dispatchEvent(new Event("jcareer:unauthorized"))',
        token_check_index + 1,
    )
    decode_index = api_source.find("decodeResponsePayload(response)", signal_index + 1)
    if not (0 <= token_check_index < signal_index < decode_index):
        raise ContractError(
            "web current-token 401 signal must precede response body decoding"
        )
    if "await response.json()" in api_source:
        raise ContractError("web response decoder must not bypass bounded text-first parsing")
    combined_source = f"{app_source}\n{api_source}"
    forbidden_markers = (
        'api("/api/v1/auth/me")',
        "api('/api/v1/auth/me')",
        'addEventListener("storage"',
        "addEventListener('storage'",
    )
    if any(marker in combined_source for marker in forbidden_markers):
        raise ContractError("web startup identity source state changed")


def _function_map(source_path: Path) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _contains_company_status_gate(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(function):
        if not isinstance(node, ast.If):
            continue
        for part in ast.walk(node.test):
            if not isinstance(part, ast.Attribute) or part.attr != "status":
                continue
            owner = part.value
            if isinstance(owner, ast.Name) and "company" in owner.id.lower():
                return True
            if isinstance(owner, ast.Attribute) and owner.attr == "company":
                return True
    return False


def _validate_tenant_source_markers(
    key: tuple[str, str],
    operation: dict[str, Any],
    source_function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> None:
    tenant_mode, company_gate = EXPECTED_TENANT_BOUNDARIES[key]
    if (operation["tenant_mode"], operation["company_status_gate_enforced"]) != (
        tenant_mode,
        company_gate,
    ):
        raise ContractError(f"tenant boundary declaration drift for {key}")
    calls = set(_called_symbols(source_function))
    roles = operation["auth"]["roles"]
    source = ast.unparse(source_function)
    missing_markers = [
        marker
        for marker in EXPECTED_TENANT_SOURCE_MARKERS.get(key, ())
        if marker not in source
    ]
    if missing_markers:
        raise ContractError(f"tenant source marker drift for {key}: {missing_markers}")
    if tenant_mode == "self" and roles != ["candidate"]:
        raise ContractError(f"self boundary must use candidate role for {key}")
    if tenant_mode == "linked_company" and not ({"recruiter_company"} <= calls and roles == ["recruiter"]):
        raise ContractError(f"linked company source marker drift for {key}")
    if tenant_mode == "job_company_equality" and not ({"recruiter_job"} <= calls and roles == ["recruiter"]):
        raise ContractError(f"job/company equality source marker drift for {key}")
    if tenant_mode == "application_job_company_equality":
        if not (
            roles == ["recruiter"]
            and "recruiter_company" in calls
            and "job.company_id != user.company_id" in source
        ):
            raise ContractError(f"application/job/company equality source marker drift for {key}")
    if tenant_mode in {"global_admin", "global_admin_filter"} and roles != ["admin"]:
        raise ContractError(f"global admin boundary source marker drift for {key}")
    if tenant_mode == "caller_supplied_subjects" and not (
        operation["auth"] == {"mode": "none_internal_intent", "roles": []}
        and operation["request_body_model"] is not None
    ):
        raise ContractError(f"internal caller-supplied boundary source marker drift for {key}")
    if company_gate is False and _contains_company_status_gate(source_function):
        raise ContractError(f"company status gate appeared in source for {key}")


def _validate_route_exposure(service: str, route: dict[str, Any]) -> None:
    expected_keys = ROUTE_KEYS if service == "api" else ROUTE_KEYS | {"exposure"}
    _exact_keys(route, expected_keys, f"{service} route")
    if service == "api":
        return
    expected = "prefixed_alias" if route["path"].startswith(("/agent/", "/llm/")) else "internal_canonical"
    if route["exposure"] != expected:
        raise ContractError(
            f"{service} {route['path']} exposure must be {expected}, got {route['exposure']}"
        )


def _source_degradation_checks(api_source: str) -> None:
    required_fragments = [
        'raise HTTPException(status_code=503, detail="추천 점수 계산 서비스를 사용할 수 없습니다")',
        'return "UNAVAILABLE_PROVIDER", {}',
        "except (TimeoutError, redis.RedisError, json.JSONDecodeError):\n        return None",
        "except (TimeoutError, redis.RedisError):\n        pass",
        'cached["cache"] = "hit"',
        '"cache": "miss"',
    ]
    missing = [fragment for fragment in required_fragments if fragment not in api_source]
    if missing:
        raise ContractError(f"recommendation degradation source drift: missing {missing}")


def validate(root: Path) -> dict[str, int]:
    contract = load_contract(root / CONTRACT_PATH)
    _exact_keys(contract, TOP_LEVEL_KEYS, "contract")
    if contract["schema_version"] != "1.0":
        raise ContractError("unsupported API contract schema_version")
    if contract["contract_id"] != "jcareer-asis-api-surface-v1":
        raise ContractError("unexpected API contract id")
    if contract["contract_status"] != "SOURCE_DECLARATION_NOT_EXECUTION_EVIDENCE":
        raise ContractError("contract status must not claim execution evidence")
    if not isinstance(contract["scope"], dict):
        raise ContractError("scope must be an object")
    _exact_keys(contract["scope"], SCOPE_KEYS, "scope")
    if contract["scope"] != EXPECTED_SCOPE:
        raise ContractError("API scope declaration changed")
    if not isinstance(contract["limitations"], list) or len(contract["limitations"]) < 6:
        raise ContractError("at least six explicit API limitations are required")
    if any(not isinstance(item, str) or not item.strip() for item in contract["limitations"]):
        raise ContractError("API limitations must be non-empty strings")
    if contract["recommendation_degradation"] != EXPECTED_DEGRADATION:
        raise ContractError("recommendation degradation declaration changed")
    data_lifecycle = contract["two_sided_data_lifecycle"]
    if not isinstance(data_lifecycle, dict):
        raise ContractError("two-sided data lifecycle must be an object")
    _exact_keys(data_lifecycle, TWO_SIDED_DATA_LIFECYCLE_KEYS, "two-sided data lifecycle")
    lifecycle_state = {
        key: value
        for key, value in data_lifecycle.items()
        if key != "source_function_sha256"
    }
    if lifecycle_state != EXPECTED_TWO_SIDED_DATA_LIFECYCLE:
        raise ContractError("two-sided data lifecycle source-state declaration changed")

    services = contract["services"]
    if not isinstance(services, dict) or set(services) != {"api", "agent", "llm-gateway"}:
        raise ContractError("services must be exactly api, agent, and llm-gateway")
    if services != EXPECTED_SERVICES:
        raise ContractError("service source/exposure metadata changed")
    extracted: dict[tuple[str, str], dict[str, Any]] = {}
    source_functions: dict[tuple[str, str], ast.FunctionDef | ast.AsyncFunctionDef] = {}
    extracted_models: dict[str, str] = {}
    extracted_model_fingerprints: dict[str, str] = {}
    extracted_model_extends: dict[str, list[str]] = {}
    source_route_keys: set[tuple[str, str, str]] = set()
    total_routes = 0
    for service, declaration in services.items():
        if not isinstance(declaration, dict):
            raise ContractError(f"{service} declaration must be an object")
        _exact_keys(declaration, SERVICE_KEYS, f"service {service}")
        source_rel = declaration["source"]
        if not isinstance(source_rel, str) or Path(source_rel).is_absolute() or ".." in Path(source_rel).parts:
            raise ContractError(f"unsafe source path for {service}")
        operations = extract_operations(service, root / source_rel)
        functions = _function_map(root / source_rel)
        extracted_models.update(extract_model_signatures(service, root / source_rel))
        extracted_model_fingerprints.update(extract_model_fingerprints(service, root / source_rel))
        extracted_model_extends.update(extract_model_extends(service, root / source_rel))
        if len(operations) != declaration["operation_groups"]:
            raise ContractError(f"{service} operation group count drift")
        route_count = sum(len(item["routes"]) for item in operations)
        if route_count != declaration["route_entries"]:
            raise ContractError(f"{service} route entry count drift")
        if service == "api":
            if declaration["route_exposure_default"] != "source_route_only":
                raise ContractError("api route exposure default drift")
        elif declaration["route_exposure_default"] is not None:
            raise ContractError(f"{service} aliases require explicit route exposure")
        for operation in operations:
            key = (service, operation["operation_id"])
            if key in extracted:
                raise ContractError(f"duplicate source operation: {key}")
            extracted[key] = operation
            source_functions[key] = functions[operation["operation_id"]]
            for route in operation["routes"]:
                route_key = (service, route["method"], route["path"])
                if route_key in source_route_keys:
                    raise ContractError(f"duplicate source route: {route_key}")
                source_route_keys.add(route_key)
        total_routes += route_count

    operations = contract["operations"]
    if not isinstance(operations, list):
        raise ContractError("operations must be an array")
    declared_keys: set[tuple[str, str]] = set()
    for operation in operations:
        if not isinstance(operation, dict):
            raise ContractError("operation entries must be objects")
        _exact_keys(operation, OPERATION_KEYS, "operation")
        service = operation["service"]
        operation_id = operation["operation_id"]
        key = (service, operation_id)
        if key in declared_keys:
            raise ContractError(f"duplicate declared operation: {key}")
        declared_keys.add(key)
        if service not in services:
            raise ContractError(f"unknown operation service: {service}")
        if operation["tenant_mode"] not in ALLOWED_TENANT_MODES:
            raise ContractError(f"unknown tenant mode for {key}")
        if operation["company_status_gate_enforced"] not in {True, False, None}:
            raise ContractError(f"company status gate must be boolean or null for {key}")
        if operation["verification_level"] != "AST_PARTIAL":
            raise ContractError(f"operation {key} must remain AST_PARTIAL")
        if not isinstance(operation["auth"], dict):
            raise ContractError(f"auth must be an object for {key}")
        _exact_keys(operation["auth"], AUTH_KEYS, f"auth {key}")
        if not isinstance(operation["routes"], list) or not operation["routes"]:
            raise ContractError(f"routes required for {key}")
        for route in operation["routes"]:
            if not isinstance(route, dict):
                raise ContractError(f"route must be object for {key}")
            _validate_route_exposure(service, route)
        expected = extracted.get(key)
        if expected is None:
            raise ContractError(f"declared operation not found in source: {key}")
        comparable = {
            field: operation[field]
            for field in (
                "operation_id",
                "service",
                "request_body_model",
                "path_params",
                "query_params",
                "auth",
                "required_calls",
                "direct_error_statuses",
                "response_annotation",
            )
        }
        comparable["routes"] = [
            {field: route[field] for field in ROUTE_KEYS} for route in operation["routes"]
        ]
        if comparable != expected:
            changed = [name for name in comparable if comparable[name] != expected[name]]
            raise ContractError(f"source contract drift for {key}: {changed}")
        _validate_tenant_source_markers(key, operation, source_functions[key])

    if declared_keys != set(extracted):
        raise ContractError(
            f"operation inventory drift: missing={sorted(set(extracted) - declared_keys)}, "
            f"unknown={sorted(declared_keys - set(extracted))}"
        )
    if len(operations) != 35 or total_routes != 40:
        raise ContractError("expected exactly 35 operation groups and 40 route entries")
    if contract["model_signatures"] != extracted_models:
        missing = sorted(set(extracted_models) - set(contract["model_signatures"]))
        unknown = sorted(set(contract["model_signatures"]) - set(extracted_models))
        changed = sorted(
            key
            for key in set(extracted_models) & set(contract["model_signatures"])
            if extracted_models[key] != contract["model_signatures"][key]
        )
        raise ContractError(
            f"Pydantic model signature drift: missing={missing}, unknown={unknown}, changed={changed}"
        )
    if contract["model_implementation_sha256"] != extracted_model_fingerprints:
        raise ContractError("Pydantic model implementation fingerprint drift")
    if contract["model_extends"] != extracted_model_extends:
        raise ContractError("Pydantic model inheritance drift")

    _validate_auth_source(root)
    _validate_web_session_source(root)
    api_functions = _function_map(root / services["api"]["source"])
    gateway_functions = _function_map(root / services["llm-gateway"]["source"])
    security_functions = _function_map(root / AUTH_SOURCE_PATH)
    lifecycle_function_specs = (
        ("api", "audit"),
        ("api", "get_cached"),
        ("api", "set_cached"),
        ("api", "record_consent"),
        ("api", "revoke_consent"),
        ("api", "require_core_consent"),
        ("api", "recruiter_signup"),
        ("api", "recruiter_overview"),
        ("api", "apply_to_job"),
        ("api", "get_job"),
        ("api", "candidate_recommendations"),
        ("api", "withdraw_candidate"),
        ("api", "recruiter_job"),
        ("api", "recruiter_pipeline"),
        ("api", "update_application_status"),
        ("api", "recruiter_recommendations"),
        ("api", "run_explanations"),
        ("api", "explanation_provider_config"),
        ("api", "explanation_attempt_metadata"),
        ("llm-gateway", "_provider_config_metadata"),
        ("llm-gateway", "_prompt_record"),
        ("llm-gateway", "_bedrock_explanations"),
        ("llm-gateway", "explanations"),
        ("api-security", "issue_token"),
        ("api-security", "parse_token"),
        ("api-security", "current_user"),
        ("api-security", "require_role"),
    )
    lifecycle_sources = {
        "api": api_functions,
        "llm-gateway": gateway_functions,
        "api-security": security_functions,
    }
    lifecycle_fingerprints = {
        f"{service}:{name}": _function_fingerprint(lifecycle_sources[service][name])
        for service, name in lifecycle_function_specs
    }
    _, lifecycle_fingerprints["api-model:Company"] = _company_model_contract(root)
    if data_lifecycle["source_function_sha256"] != lifecycle_fingerprints:
        raise ContractError("two-sided data lifecycle source fingerprint drift")
    expected_validation_helpers = {
        "api:normalise_skill_values": _function_fingerprint(
            api_functions["normalise_skill_values"]
        )
    }
    if contract["validation_helper_sha256"] != expected_validation_helpers:
        raise ContractError("request validation helper fingerprint drift")
    company_gate_functions = (
        "recruiter_company",
        "recruiter_job",
        "recruiter_signup",
        "login",
        "me",
        "list_jobs",
        "get_job",
        "apply_to_job",
        "candidate_applications",
        "candidate_recommendations",
        "recruiter_jobs",
        "recruiter_overview",
        "get_recruiter_company_profile",
        "update_recruiter_company_profile",
        "refresh_recruiter_company_opendart",
        "collect_recruiter_company_opendart",
        "create_recruiter_job",
        "update_recruiter_job",
        "recruiter_pipeline",
        "update_application_status",
        "recruiter_recommendations",
    )
    helper_markers = {
        "recruiter_company": (
            "if not user.company_id",
            "db.get(Company, user.company_id)",
            "if not company",
            "return company",
        ),
        "recruiter_job": (
            "recruiter_company(db, user)",
            "Job.id == job_id",
            "job.company_id != user.company_id",
            "status_code=403",
        ),
    }
    for helper_name in ("recruiter_company", "recruiter_job"):
        helper_source = ast.unparse(api_functions[helper_name])
        missing = [marker for marker in helper_markers[helper_name] if marker not in helper_source]
        if missing:
            raise ContractError(f"tenant helper source marker drift in {helper_name}: {missing}")
        if _contains_company_status_gate(api_functions[helper_name]):
            raise ContractError(f"company status gate appeared in {helper_name}")
    observed_gate_absence_fingerprints = {
        f"api:{name}": _function_fingerprint(api_functions[name])
        for name in company_gate_functions
    }
    if contract["company_status_gate_absence_sha256"] != observed_gate_absence_fingerprints:
        raise ContractError("company status gate source fingerprint drift")

    api_source = (root / services["api"]["source"]).read_text(encoding="utf-8")
    _source_degradation_checks(api_source)
    return {"operation_groups": len(operations), "route_entries": total_routes}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    try:
        result = validate(args.root.resolve())
    except ContractError as exc:
        print(f"API surface contract: FAIL: {exc}")
        return 1
    print(
        "API surface contract: PASS "
        f"({result['operation_groups']} operation groups, {result['route_entries']} route entries; "
        "source declaration only, runtime not current)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
