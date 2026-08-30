#!/usr/bin/env python3
"""Read local synthetic-demo prerequisites without invoking external tooling.

The checker deliberately reports only structural local readiness.  It does not
call AWS, Docker, Terraform, Git, a network service, or any executable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    import yaml
except ImportError:
    print("PyYAML is required for the readiness contract.", file=sys.stderr)
    raise SystemExit(2)


CONTRACT_PATH = Path("fleet/readiness/demo_readiness_contract.yaml")
MAX_RECORD_BYTES = 1_048_576
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SERVICE_IDS = ("web", "api", "agent", "llm-gateway")
ENDPOINT_REFS = ("WIN-01", "WIN-02", "WIN-03")
TOOL_IDS = ("aws_cli_v2", "terraform", "python", "session_manager_plugin", "rdp_client")
MAC_DECLARATIONS = (
    "physical_mac_available",
    "mdm_distribution_ready",
    "operator_identity_and_remote_access_defined",
)
LIMITATIONS = (
    "supplied_record_shape_and_hash_only",
    "no_approval_or_human_decision_determination",
    "no_live_cloud_or_endpoint_observation",
    "no_macos_device_or_mdm_observation",
    "no_tool_version_or_execution_validation",
)


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _unique_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict[object, object]:
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark, "duplicate mapping key", key_node.start_mark
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def _unique_json_mapping(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _load_json_unique(text: str) -> object:
    return json.loads(text, object_pairs_hook=_unique_json_mapping)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65_536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _exact_keys(value: object, expected: set[str], label: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{label}: mapping_required")
        return False
    actual = set(value)
    if actual != expected:
        errors.append(f"{label}: unexpected_or_missing_fields")
        return False
    return True


def load_contract(path: Path) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    try:
        document = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    except (OSError, TypeError, yaml.YAMLError):
        return {}, ["contract: unreadable_or_invalid_yaml"]
    if not isinstance(document, dict):
        return {}, ["contract: mapping_required"]
    expected = {
        "schema_version", "data_classification", "decision_authority", "execution_mode",
        "allowed_result_states", "forbidden_operations", "application", "windows", "macos", "result_limitations",
    }
    if not _exact_keys(document, expected, "contract", errors):
        return document, errors
    fixed = {
        "schema_version": "jcareer-demo-readiness-contract-v1",
        "data_classification": "SYNTHETIC_DEMONSTRATION_ONLY",
        "decision_authority": "HUMAN",
        "execution_mode": "LOCAL_FILESYSTEM_READ_ONLY",
        "allowed_result_states": ["NOT_READY", "READY_FOR_HUMAN_RUN"],
        "forbidden_operations": [
            "aws_cli_invocation", "docker_invocation", "terraform_invocation", "git_invocation",
            "network_call", "cloud_mutation", "local_mutation",
        ],
        "result_limitations": list(LIMITATIONS),
    }
    for key, expected_value in fixed.items():
        if document.get(key) != expected_value:
            errors.append(f"contract.{key}: fixed_value_mismatch")
    application = document.get("application")
    if _exact_keys(application, {"required_service_ids", "preview_url_rules"}, "contract.application", errors):
        if application["required_service_ids"] != list(SERVICE_IDS):
            errors.append("contract.application.required_service_ids: fixed_value_mismatch")
        if application["preview_url_rules"] != {
            "scheme": "https", "userinfo": "forbidden", "query": "forbidden", "fragment": "forbidden", "digest_algorithm": "sha256",
        }:
            errors.append("contract.application.preview_url_rules: fixed_value_mismatch")
    windows = document.get("windows")
    if _exact_keys(windows, {"required_endpoint_refs", "required_record_schemas", "required_local_tool_ids"}, "contract.windows", errors):
        if windows["required_endpoint_refs"] != list(ENDPOINT_REFS):
            errors.append("contract.windows.required_endpoint_refs: fixed_value_mismatch")
        if windows["required_local_tool_ids"] != list(TOOL_IDS):
            errors.append("contract.windows.required_local_tool_ids: fixed_value_mismatch")
        if windows["required_record_schemas"] != {
            "image_receipt": "jcareer-windows-image-receipt-v2",
            "build_observation": "jcareer-windows-image-build-observation-v1",
            "endpoint_apply_receipt": "jcareer-redacted-terraform-apply-receipt-v1",
            "session_record": "jcareer-windows-endpoint-session-approval-v1",
        }:
            errors.append("contract.windows.required_record_schemas: fixed_value_mismatch")
    macos = document.get("macos")
    if _exact_keys(macos, {"required_declarations"}, "contract.macos", errors):
        if macos["required_declarations"] != list(MAC_DECLARATIONS):
            errors.append("contract.macos.required_declarations: fixed_value_mismatch")
    return document, errors


def _unsafe_path(path: Path) -> bool:
    try:
        absolute = path.absolute()
        for candidate in (absolute, *absolute.parents):
            if candidate.is_symlink():
                return True
    except OSError:
        return True
    return False


def _load_record(reference: object, expected_schema: str, label: str, missing: list[str]) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(reference, dict) or set(reference) != {"path", "sha256"}:
        missing.append(f"{label}: record_reference_missing_or_invalid")
        return None, None
    raw_path, expected_hash = reference.get("path"), reference.get("sha256")
    if not isinstance(raw_path, str) or not raw_path or not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(expected_hash):
        missing.append(f"{label}: record_reference_missing_or_invalid")
        return None, None
    path = Path(raw_path)
    if not path.is_absolute() or _unsafe_path(path):
        missing.append(f"{label}: record_path_unsafe")
        return None, None
    try:
        stat = path.stat()
        if not path.is_file() or stat.st_size > MAX_RECORD_BYTES:
            missing.append(f"{label}: record_not_regular_or_too_large")
            return None, None
        actual_hash = _sha256_file(path)
        if actual_hash != expected_hash:
            missing.append(f"{label}: record_hash_mismatch")
            return None, None
        content = _load_json_unique(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        missing.append(f"{label}: record_unreadable_or_invalid_json")
        return None, None
    if not isinstance(content, dict) or content.get("schema_version") != expected_schema:
        missing.append(f"{label}: unexpected_record_schema")
        return None, None
    if content.get("synthetic_data_only") is not True:
        missing.append(f"{label}: synthetic_only_not_declared")
        return None, None
    return content, actual_hash


def _valid_clean_https_url(value: object, declared_hash: object) -> bool:
    if not isinstance(value, str) or not isinstance(declared_hash, str) or not SHA256_RE.fullmatch(declared_hash):
        return False
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        return False
    return hashlib.sha256(value.encode("utf-8")).hexdigest() == declared_hash


def _safe_tool_path(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = Path(value)
    try:
        return path.is_absolute() and not _unsafe_path(path) and path.is_file()
    except OSError:
        return False


def _result(missing: list[str], ready: list[str]) -> dict[str, Any]:
    return {
        "schema_version": "jcareer-demo-readiness-result-v1",
        "state": "READY_FOR_HUMAN_RUN" if not missing else "NOT_READY",
        "synthetic_only": True,
        "execution_mode": "LOCAL_FILESYSTEM_READ_ONLY",
        "ready_items": ready,
        "missing_or_invalid_items": missing,
        "not_determined": list(LIMITATIONS),
    }


def evaluate(contract: dict[str, Any], observation: object | None) -> dict[str, Any]:
    """Evaluate only supplied local files and declared local facts; never execute a tool."""
    missing: list[str] = []
    ready: list[str] = []
    if not isinstance(observation, dict):
        return _result(["operator_observation: missing_or_invalid"], ready)
    expected = {"schema_version", "synthetic_only", "preview", "windows", "macos"}
    if not _exact_keys(observation, expected, "operator_observation", missing):
        return _result(missing, ready)
    if observation.get("schema_version") != "jcareer-demo-readiness-observation-v1":
        missing.append("operator_observation: unexpected_schema")
    if observation.get("synthetic_only") is not True:
        missing.append("operator_observation: synthetic_only_not_declared")

    preview = observation.get("preview")
    if _exact_keys(preview, {"url", "url_sha256", "artifact_digests"}, "preview", missing):
        artifacts = preview.get("artifact_digests")
        if not _valid_clean_https_url(preview.get("url"), preview.get("url_sha256")):
            missing.append("preview: credential_free_https_url_or_hash_invalid")
        elif not isinstance(artifacts, dict) or set(artifacts) != set(SERVICE_IDS) or any(
            not isinstance(artifacts.get(service), str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", artifacts[service])
            for service in SERVICE_IDS
        ):
            missing.append("preview: application_artifact_digests_missing_or_invalid")
        else:
            ready.append("preview_and_four_artifact_digests_declared")

    windows = observation.get("windows")
    expected_windows = {"image_receipt", "build_observation", "endpoint_apply_receipt", "session_record", "local_tool_paths"}
    if _exact_keys(windows, expected_windows, "windows", missing):
        image, image_hash = _load_record(windows.get("image_receipt"), "jcareer-windows-image-receipt-v2", "windows.image_receipt", missing)
        build, build_hash = _load_record(windows.get("build_observation"), "jcareer-windows-image-build-observation-v1", "windows.build_observation", missing)
        endpoint, endpoint_hash = _load_record(windows.get("endpoint_apply_receipt"), "jcareer-redacted-terraform-apply-receipt-v1", "windows.endpoint_apply_receipt", missing)
        session, _ = _load_record(windows.get("session_record"), "jcareer-windows-endpoint-session-approval-v1", "windows.session_record", missing)
        if image and build and image_hash and build_hash:
            if image.get("build_observation_sha256") != build_hash or image.get("ami_id") != build.get("ami_id"):
                missing.append("windows: image_receipt_build_observation_link_mismatch")
            else:
                ready.append("windows_image_receipt_and_build_observation_hash_linked")
        if endpoint and build_hash:
            if (
                endpoint.get("scope") != "workplace-windows-endpoints"
                or endpoint.get("build_observation_sha256") != build_hash
                or endpoint.get("result") != "APPLY_COMMAND_COMPLETED"
                or endpoint.get("resource_identifiers_included") is not False
                or endpoint.get("local_snapshot_cleanup_observed") is not True
            ):
                missing.append("windows: endpoint_apply_receipt_link_mismatch")
            else:
                ready.append("windows_endpoint_apply_receipt_hash_linked")
        if session and endpoint_hash and image_hash and build_hash:
            sessions = session.get("sessions")
            refs = [entry.get("endpoint_ref") for entry in sessions] if isinstance(sessions, list) and all(isinstance(entry, dict) for entry in sessions) else []
            if (
                session.get("scope") != "workplace-windows-consultant-session"
                or session.get("endpoint_apply_receipt_sha256") != endpoint_hash
                or session.get("image_receipt_sha256") != image_hash
                or session.get("build_observation_sha256") != build_hash
                or session.get("max_sessions") != 3
                or sorted(refs) != list(ENDPOINT_REFS)
            ):
                missing.append("windows: exactly_three_endpoint_session_record_not_linked")
            else:
                ready.append("windows_three_endpoint_refs_structurally_linked")
        tools = windows.get("local_tool_paths")
        if not isinstance(tools, dict) or set(tools) != set(TOOL_IDS):
            missing.append("windows: local_tool_paths_missing_or_invalid")
        else:
            absent = [tool for tool in TOOL_IDS if not _safe_tool_path(tools.get(tool))]
            if absent:
                missing.append("windows: local_tools_not_present")
            else:
                ready.append("windows_local_tool_paths_present_not_executed")

    macos = observation.get("macos")
    if _exact_keys(macos, set(MAC_DECLARATIONS), "macos", missing):
        if any(macos.get(item) is not True for item in MAC_DECLARATIONS):
            missing.append("macos: physical_mdm_or_operator_prerequisite_not_declared")
        else:
            ready.append("macos_prerequisites_declared_not_observed")
    return _result(missing, ready)


def load_observation(path: Path | None) -> object | None:
    if path is None:
        return None
    try:
        if not path.is_absolute() or _unsafe_path(path) or not path.is_file() or path.stat().st_size > MAX_RECORD_BYTES:
            return None
        return _load_json_unique(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."), help="repository root (read-only)")
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH, help="contract path relative to root")
    parser.add_argument("--observation", type=Path, help="operator-private JSON observation; no value is printed")
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    contract_path = arguments.contract if arguments.contract.is_absolute() else root / arguments.contract
    contract, errors = load_contract(contract_path)
    if errors:
        print(json.dumps(_result([f"contract: {item}" for item in errors], []), ensure_ascii=False, sort_keys=True))
        return 2
    result = evaluate(contract, load_observation(arguments.observation))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
