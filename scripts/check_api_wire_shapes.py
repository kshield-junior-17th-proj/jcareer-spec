#!/usr/bin/env python3
"""Validate source-only handler return and direct HTTPException shape declarations."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from check_api_effects_contract import (
    CONTRACT_PATH as API_EFFECTS_PATH,
    validate as validate_api_effects,
)
from check_api_surface_contract import (
    CONTRACT_PATH as API_SURFACE_PATH,
    ContractError as SurfaceContractError,
    _function_fingerprint,
    _function_map,
    load_contract,
)


CONTRACT_PATH = Path("src/runtime/contracts/api_wire_shapes.json")
TOP_LEVEL_KEYS = {
    "schema_version",
    "contract_id",
    "contract_status",
    "scope",
    "limitations",
    "upstream_contracts",
    "operations",
}
SCOPE_KEYS = {
    "operation_coverage",
    "route_entry_coverage",
    "return_semantics",
    "error_semantics",
    "nested_schema",
    "dependency_helper_framework_errors",
    "response_model_enforcement",
    "runtime_verification",
    "aws_or_bedrock_execution",
    "compliance_or_risk_decision",
}
EXPECTED_SCOPE = {
    "operation_coverage": "ALL_35_HANDLER_OPERATION_GROUPS",
    "route_entry_coverage": "INHERITED_40_ROUTE_ENTRIES_NOT_RECOUNTED",
    "return_semantics": "DIRECT_HANDLER_RETURN_EXPRESSIONS_ONLY",
    "error_semantics": "DIRECT_HANDLER_LITERAL_HTTPEXCEPTION_CALLS_ONLY",
    "nested_schema": "ADMIN_AI_OPERATIONS_STRICT_PYDANTIC_RESPONSE_MODELS",
    "dependency_helper_framework_errors": "NOT_ENUMERATED",
    "response_model_enforcement": "PRESENT_ON_PUBLIC_RUNTIME_AND_ADMIN_AI_OPERATIONS",
    "runtime_verification": "NOT_CURRENT",
    "aws_or_bedrock_execution": "NOT_CLAIMED",
    "compliance_or_risk_decision": "HUMAN_ONLY",
}
UPSTREAM_KEYS = {"path", "contract_id", "sha256"}
EXPECTED_UPSTREAM = (
    (API_SURFACE_PATH, "jcareer-asis-api-surface-v1"),
    (API_EFFECTS_PATH, "jcareer-asis-source-effects-v1"),
)
EXPECTED_RESPONSE_MODELS = {
    "api:runtime_info": "PublicRuntimeResponse",
    "api:admin_ai_operations": "AiServiceOperationsResponse",
    "api:collect_recruiter_company_opendart": "None",
}
OPERATION_KEYS = {
    "operation_ref",
    "source_function_sha256",
    "route_success_statuses",
    "direct_return_variants",
    "direct_http_exceptions",
}
RETURN_VARIANT_KEYS = {
    "expression_kind",
    "reference",
    "top_level_literal_keys",
    "mapping_unpack_references",
    "list_item_expression_kind",
    "list_item_reference",
    "list_item_top_level_literal_keys",
    "shape_state",
}
EXCEPTION_KEYS = {
    "status",
    "detail_kind",
    "detail_literal",
    "detail_expression",
    "occurrences",
}
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise SurfaceContractError(
            f"{label} keys differ: missing={sorted(expected - set(value))}, "
            f"unknown={sorted(set(value) - expected)}"
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _expression_reference(node: ast.AST) -> str:
    if isinstance(node, ast.Call):
        return ast.unparse(node.func)
    return ast.unparse(node)


def _dict_literal_parts(node: ast.Dict) -> tuple[list[str], list[str]]:
    keys: list[str] = []
    unpack_references: list[str] = []
    for key, value in zip(node.keys, node.values, strict=True):
        if key is None:
            unpack_references.append(_expression_reference(value))
            continue
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
            raise SurfaceContractError(
                "direct response dict has a non-literal string top-level key"
            )
        keys.append(key.value)
    return keys, unpack_references


def _return_variant(value: ast.AST | None) -> dict[str, Any]:
    variant: dict[str, Any] = {
        "expression_kind": "NONE",
        "reference": None,
        "top_level_literal_keys": [],
        "mapping_unpack_references": [],
        "list_item_expression_kind": None,
        "list_item_reference": None,
        "list_item_top_level_literal_keys": [],
        "shape_state": "NO_EXPLICIT_BODY_SOURCE_ONLY",
    }
    if value is None:
        return variant
    if isinstance(value, ast.Dict):
        keys, unpack_references = _dict_literal_parts(value)
        variant.update(
            expression_kind="DICT_LITERAL",
            top_level_literal_keys=keys,
            mapping_unpack_references=unpack_references,
            shape_state=(
                "EMITTED_LITERAL_KEYS_PLUS_UNEXPANDED_MAPPING"
                if unpack_references
                else "EMITTED_TOP_LEVEL_KEYS_SOURCE_ONLY"
            ),
        )
        return variant
    if isinstance(value, ast.ListComp):
        item = value.elt
        variant.update(
            expression_kind="LIST_COMPREHENSION",
            shape_state="LIST_ITEM_EXPRESSION_SOURCE_ONLY",
        )
        if isinstance(item, ast.Dict):
            keys, unpack_references = _dict_literal_parts(item)
            if unpack_references:
                raise SurfaceContractError(
                    "direct response list item has an unexpanded mapping"
                )
            variant.update(
                list_item_expression_kind="DICT_LITERAL",
                list_item_top_level_literal_keys=keys,
                shape_state="LIST_ITEM_LITERAL_KEYS_SOURCE_ONLY",
            )
        elif isinstance(item, ast.Call):
            variant.update(
                list_item_expression_kind="CALL",
                list_item_reference=_expression_reference(item),
                shape_state="LIST_ITEM_HELPER_RETURN_NOT_EXPANDED",
            )
        else:
            variant.update(
                list_item_expression_kind=type(item).__name__.upper(),
                list_item_reference=ast.unparse(item),
            )
        return variant
    if isinstance(value, ast.Call):
        variant.update(
            expression_kind="CALL",
            reference=_expression_reference(value),
            shape_state="HELPER_RETURN_NOT_EXPANDED",
        )
        return variant
    if isinstance(value, ast.Name):
        variant.update(
            expression_kind="NAME_REFERENCE",
            reference=value.id,
            shape_state=(
                "CACHED_OBJECT_VALIDATED_SUBSET"
                if value.id == "cached"
                else "LOCAL_NAME_REFERENCE_NOT_EXPANDED"
            ),
        )
        return variant
    variant.update(
        expression_kind=type(value).__name__.upper(),
        reference=ast.unparse(value),
        shape_state="EXPRESSION_NOT_EXPANDED",
    )
    return variant


def _literal_integer(node: ast.AST | None, label: str) -> int:
    if node is None:
        raise SurfaceContractError(f"{label} is missing")
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError) as exc:
        raise SurfaceContractError(f"{label} must be a literal integer") from exc
    if not isinstance(value, int):
        raise SurfaceContractError(f"{label} must be a literal integer")
    return value


def _http_exception(call: ast.Call) -> tuple[int, str, str | None, str | None]:
    keywords = {keyword.arg: keyword.value for keyword in call.keywords if keyword.arg}
    status = _literal_integer(keywords.get("status_code"), "HTTPException status_code")
    detail = keywords.get("detail")
    if isinstance(detail, ast.Constant) and isinstance(detail.value, str):
        return status, "STRING_LITERAL", detail.value, None
    if detail is None:
        return status, "OMITTED", None, None
    return status, "EXPRESSION", None, ast.unparse(detail)


class _HandlerVisitor(ast.NodeVisitor):
    """Walk one handler body while excluding any nested function or class bodies."""

    def __init__(self, root: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.root = root
        self.returns: list[ast.Return] = []
        self.http_exceptions: list[tuple[int, str, str | None, str | None]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        if node is self.root:
            for statement in node.body:
                self.visit(statement)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        if node is self.root:
            for statement in node.body:
                self.visit(statement)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:  # noqa: N802
        return

    def visit_Return(self, node: ast.Return) -> None:  # noqa: N802
        self.returns.append(node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if isinstance(node.func, ast.Name) and node.func.id == "HTTPException":
            self.http_exceptions.append(_http_exception(node))
        self.generic_visit(node)


def _direct_shapes(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    visitor = _HandlerVisitor(function)
    visitor.visit(function)
    returns = [_return_variant(node.value) for node in visitor.returns]
    errors: list[dict[str, Any]] = []
    positions: dict[tuple[int, str, str | None, str | None], int] = {}
    for error in visitor.http_exceptions:
        if error in positions:
            errors[positions[error]]["occurrences"] += 1
            continue
        positions[error] = len(errors)
        status, detail_kind, detail_literal, detail_expression = error
        errors.append(
            {
                "status": status,
                "detail_kind": detail_kind,
                "detail_literal": detail_literal,
                "detail_expression": detail_expression,
                "occurrences": 1,
            }
        )
    return returns, errors


def _response_model(function: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    for decorator in function.decorator_list:
        if not (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr.lower() in HTTP_METHODS
        ):
            continue
        for keyword in decorator.keywords:
            if keyword.arg == "response_model":
                return ast.unparse(keyword.value)
    return None


def derive_operations(root: Path) -> tuple[list[dict[str, Any]], int]:
    """Derive the bounded source view used for contract comparison and maintenance."""

    surface = load_contract(root / API_SURFACE_PATH)
    effects = load_contract(root / API_EFFECTS_PATH)
    effects_by_ref = {
        item["operation_ref"]: item for item in effects["operations"]
    }
    functions_by_service: dict[
        str, dict[str, ast.FunctionDef | ast.AsyncFunctionDef]
    ] = {}
    for service, declaration in surface["services"].items():
        source_path = (root / declaration["source"]).resolve()
        functions_by_service[service] = _function_map(source_path)

    rows: list[dict[str, Any]] = []
    route_entries = 0
    for surface_operation in surface["operations"]:
        service = surface_operation["service"]
        function_name = surface_operation["operation_id"]
        operation_ref = f"{service}:{function_name}"
        function = functions_by_service[service].get(function_name)
        if function is None:
            raise SurfaceContractError(f"source function is missing: {operation_ref}")
        observed_response_model = _response_model(function)
        if observed_response_model != EXPECTED_RESPONSE_MODELS.get(operation_ref):
            raise SurfaceContractError(
                f"response_model declaration drift: {operation_ref}"
            )
        effect = effects_by_ref.get(operation_ref)
        if effect is None:
            raise SurfaceContractError(f"effect operation is missing: {operation_ref}")
        fingerprint = _function_fingerprint(function)
        if effect["source_function_sha256"] != fingerprint:
            raise SurfaceContractError(f"effect/source fingerprint differs: {operation_ref}")
        returns, errors = _direct_shapes(function)
        if not returns:
            raise SurfaceContractError(f"handler has no direct return expression: {operation_ref}")
        statuses: list[int] = []
        for route in surface_operation["routes"]:
            route_entries += 1
            status = route["success_status"]
            if status not in statuses:
                statuses.append(status)
        direct_statuses = sorted({item["status"] for item in errors})
        if direct_statuses != sorted(surface_operation["direct_error_statuses"]):
            raise SurfaceContractError(
                f"surface/direct HTTPException statuses differ: {operation_ref}"
            )
        rows.append(
            {
                "operation_ref": operation_ref,
                "source_function_sha256": fingerprint,
                "route_success_statuses": statuses,
                "direct_return_variants": returns,
                "direct_http_exceptions": errors,
            }
        )
    return rows, route_entries


def validate(root: Path) -> dict[str, int]:
    root = root.resolve()
    validate_api_effects(root)
    contract = load_contract(root / CONTRACT_PATH)
    _exact_keys(contract, TOP_LEVEL_KEYS, "API wire-shape contract")
    if contract["schema_version"] != "1.0":
        raise SurfaceContractError("unsupported API wire-shape schema_version")
    if contract["contract_id"] != "jcareer-asis-api-wire-shapes-v1":
        raise SurfaceContractError("unexpected API wire-shape contract id")
    if (
        contract["contract_status"]
        != "SOURCE_RETURN_AND_DIRECT_EXCEPTION_CATALOG_NOT_RUNTIME_EVIDENCE"
    ):
        raise SurfaceContractError("API wire-shape contract must not claim runtime evidence")
    if not isinstance(contract["scope"], dict):
        raise SurfaceContractError("API wire-shape scope must be an object")
    _exact_keys(contract["scope"], SCOPE_KEYS, "API wire-shape scope")
    if contract["scope"] != EXPECTED_SCOPE:
        raise SurfaceContractError("API wire-shape scope declaration changed")
    limitations = contract["limitations"]
    if (
        not isinstance(limitations, list)
        or len(limitations) < 8
        or any(not isinstance(item, str) or not item.strip() for item in limitations)
    ):
        raise SurfaceContractError(
            "API wire-shape limitations must contain at least eight strings"
        )

    upstream = contract["upstream_contracts"]
    if not isinstance(upstream, list) or len(upstream) != len(EXPECTED_UPSTREAM):
        raise SurfaceContractError("upstream contract coverage changed")
    for row, (relative, expected_id) in zip(upstream, EXPECTED_UPSTREAM, strict=True):
        if not isinstance(row, dict):
            raise SurfaceContractError("upstream contract entry must be an object")
        _exact_keys(row, UPSTREAM_KEYS, "upstream contract entry")
        if row["path"] != relative.as_posix() or row["contract_id"] != expected_id:
            raise SurfaceContractError("upstream contract identity/order changed")
        if row["sha256"] != _sha256(root / relative):
            raise SurfaceContractError(f"upstream contract hash drift: {relative.as_posix()}")

    derived, route_entries = derive_operations(root)
    operations = contract["operations"]
    if not isinstance(operations, list):
        raise SurfaceContractError("operations must be an array")
    seen: set[str] = set()
    for operation in operations:
        if not isinstance(operation, dict):
            raise SurfaceContractError("wire-shape operation must be an object")
        _exact_keys(operation, OPERATION_KEYS, "wire-shape operation")
        operation_ref = operation["operation_ref"]
        if not isinstance(operation_ref, str):
            raise SurfaceContractError("operation_ref must be a string")
        if operation_ref in seen:
            raise SurfaceContractError(f"duplicate wire-shape operation: {operation_ref}")
        seen.add(operation_ref)
        variants = operation["direct_return_variants"]
        if not isinstance(variants, list) or not variants:
            raise SurfaceContractError("direct_return_variants must be a non-empty array")
        for variant in variants:
            if not isinstance(variant, dict):
                raise SurfaceContractError("direct return variant must be an object")
            _exact_keys(variant, RETURN_VARIANT_KEYS, "direct return variant")
        errors = operation["direct_http_exceptions"]
        if not isinstance(errors, list):
            raise SurfaceContractError("direct_http_exceptions must be an array")
        for error in errors:
            if not isinstance(error, dict):
                raise SurfaceContractError("direct HTTPException entry must be an object")
            _exact_keys(error, EXCEPTION_KEYS, "direct HTTPException entry")
    if operations != derived:
        declared_refs = [item.get("operation_ref") for item in operations]
        derived_refs = [item["operation_ref"] for item in derived]
        if declared_refs != derived_refs:
            raise SurfaceContractError("wire-shape operation coverage/order differs")
        for declared, expected in zip(operations, derived, strict=True):
            if declared != expected:
                raise SurfaceContractError(
                    f"wire-shape source declaration drift: {expected['operation_ref']}"
                )
    if len(operations) != 35 or route_entries != 40:
        raise SurfaceContractError("expected exactly 35 handlers and 40 route entries")
    return {"operations": len(operations), "route_entries": route_entries}


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
        "API source wire-shape catalog: PASS "
        f"({result['operations']} handlers, {result['route_entries']} routes; "
        "runtime not current)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
