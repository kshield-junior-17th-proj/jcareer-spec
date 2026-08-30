#!/usr/bin/env python3
"""Static and record checks for the guarded OpenDART worker publisher.

This checker verifies bindings and shapes.  It deliberately does not decide
whether a vulnerability scan is acceptable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HEX64 = re.compile(r"^[0-9a-f]{64}$")
REVISION = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
APPROVAL_REF = re.compile(r"^APPROVAL-[A-Z0-9_-]{8,64}$")
OPERATION_REF = re.compile(r"^PUBLISH-[A-Z0-9_-]{8,64}$")
REVIEWER_REF = re.compile(r"^reviewer:[a-z0-9_-]{6,64}$")
TAG = re.compile(r"^[a-z0-9][a-z0-9._-]{15,127}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
FORBIDDEN_RAW = re.compile(
    r"(?:arn:aws:|AKIA[0-9A-Z]{16}|\b\d{12}\b|"
    r"\d{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com|"
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)

BOOTSTRAP_KEYS = {
    "schema_version", "scope", "approval_ref", "saved_plan_sha256",
    "backend_config_sha256", "artifact_sha256", "build_observation_sha256",
    "completed_at", "resource_identifiers_included", "runtime_smoke_completed",
    "protected_input_snapshot_count", "local_snapshot_cleanup_observed", "result",
}
PREPARATION_KEYS = {
    "schema_version", "scope", "operation_ref", "prepared_at", "source_revision",
    "source_tree_sha256", "source_archive_sha256", "dockerfile_sha256",
    "requirements_sha256", "build_context_file_count", "local_image_id_sha256",
    "scanner_executable_sha256", "scanner_version_sha256",
    "scan_severity_selection", "scan_policy_sha256", "scan_report_sha256",
    "scan_completed", "scan_decision_recorded", "publish_attempted",
    "raw_identifiers_included", "result",
}
APPROVAL_KEYS = {
    "schema_version", "scope", "decision", "approval_ref", "reviewer_ref",
    "approved_at", "expires_at", "operation_ref", "expected_region",
    "backend_config_sha256", "backend_file_sha256", "bootstrap_apply_receipt_sha256",
    "provider_account_sha256", "preparation_receipt_sha256", "source_revision",
    "source_tree_sha256", "source_archive_sha256", "dockerfile_sha256",
    "requirements_sha256", "local_image_id_sha256", "image_tag",
    "publisher_script_sha256", "approval_checker_sha256", "backend_checker_sha256",
    "python_executable_sha256", "aws_executable_sha256", "docker_executable_sha256",
    "terraform_executable_sha256",
    "scanner_executable_sha256", "scanner_version_sha256",
    "scan_severity_selection", "scan_policy_ref", "scan_policy_sha256",
    "scan_report_sha256", "scan_human_disposition",
    "ecr_repository_url_sha256", "ecr_repository_configuration_sha256",
    "synthetic_data_only", "notes",
}
PUBLISH_KEYS = {
    "schema_version", "scope", "approval_ref", "operation_ref", "completed_at",
    "approval_record_sha256", "backend_config_sha256", "backend_file_sha256",
    "bootstrap_apply_receipt_sha256",
    "provider_account_sha256", "preparation_receipt_sha256", "source_revision",
    "source_tree_sha256", "source_archive_sha256", "dockerfile_sha256",
    "requirements_sha256", "publisher_script_sha256", "approval_checker_sha256",
    "backend_checker_sha256", "python_executable_sha256", "aws_executable_sha256",
    "docker_executable_sha256", "terraform_executable_sha256", "scan_policy_sha256",
    "scan_report_sha256", "repository_url_sha256", "ecr_repository_configuration_sha256",
    "image_tag_sha256", "docker_push_reported_digest", "ecr_image_digest",
    "digest_pinned_uri_sha256", "private_uri_artifact_sha256",
    "private_uri_artifact_created", "resource_identifiers_included",
    "protected_input_snapshot_count", "docker_auth_cleanup_observed",
    "local_artifact_cleanup_claimed", "human_release_decision_created", "result",
}


class CheckError(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CheckError("duplicate JSON key")
        result[key] = value
    return result


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_object
        )
    except (OSError, json.JSONDecodeError, CheckError) as exc:
        raise CheckError(f"invalid JSON input: {path.name}") from exc
    if not isinstance(value, dict):
        raise CheckError(f"JSON object required: {path.name}")
    return value


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _exact(obj: dict[str, Any], expected: set[str], name: str) -> None:
    missing, extra = expected - obj.keys(), obj.keys() - expected
    if missing or extra:
        raise CheckError(f"{name} exact-key mismatch; missing={sorted(missing)} extra={sorted(extra)}")


def _hex(value: Any, name: str) -> None:
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        raise CheckError(f"{name} must be lowercase SHA-256")


def _timestamp(value: Any, name: str) -> datetime:
    if not isinstance(value, str):
        raise CheckError(f"{name} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CheckError(f"{name} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise CheckError(f"{name} must include timezone")
    return parsed


def _no_raw_identifiers(obj: dict[str, Any], name: str) -> None:
    material = json.dumps(obj, ensure_ascii=False, sort_keys=True)
    if FORBIDDEN_RAW.search(material):
        raise CheckError(f"{name} contains a forbidden raw identifier")


def check_bootstrap_receipt(obj: dict[str, Any], backend_sha: str) -> None:
    _exact(obj, BOOTSTRAP_KEYS, "bootstrap receipt")
    if obj["schema_version"] != "jcareer-redacted-terraform-apply-receipt-v1":
        raise CheckError("unexpected bootstrap receipt schema")
    if obj["scope"] != "serverless-opendart":
        raise CheckError("bootstrap receipt scope mismatch")
    if obj["result"] != "APPLY_COMMAND_COMPLETED":
        raise CheckError("bootstrap apply receipt is not completed")
    if obj["backend_config_sha256"] != backend_sha:
        raise CheckError("bootstrap receipt/backend binding mismatch")
    if obj["artifact_sha256"] is not None or obj["build_observation_sha256"] is not None:
        raise CheckError("bootstrap receipt must not bind a runtime image artifact")
    if obj["resource_identifiers_included"] is not False:
        raise CheckError("bootstrap receipt must be redacted")
    if obj["runtime_smoke_completed"] is not False:
        raise CheckError("bootstrap receipt cannot claim runtime smoke")
    if obj["protected_input_snapshot_count"] != 7:
        raise CheckError("unexpected bootstrap protected snapshot count")
    if obj["local_snapshot_cleanup_observed"] is not True:
        raise CheckError("bootstrap receipt does not record its own protected-input cleanup")
    _hex(obj["saved_plan_sha256"], "saved_plan_sha256")
    _timestamp(obj["completed_at"], "completed_at")
    _no_raw_identifiers(obj, "bootstrap receipt")


def check_preparation(obj: dict[str, Any]) -> None:
    _exact(obj, PREPARATION_KEYS, "preparation receipt")
    if obj["schema_version"] != "jcareer-opendart-worker-preparation-v1":
        raise CheckError("unexpected preparation schema")
    if obj["scope"] != "serverless-opendart-worker-publish":
        raise CheckError("preparation scope mismatch")
    if not isinstance(obj["operation_ref"], str) or not OPERATION_REF.fullmatch(obj["operation_ref"]):
        raise CheckError("invalid operation_ref")
    if not isinstance(obj["source_revision"], str) or not REVISION.fullmatch(obj["source_revision"]):
        raise CheckError("source_revision must be immutable hex")
    for key in (
        "source_tree_sha256", "source_archive_sha256", "dockerfile_sha256",
        "requirements_sha256", "local_image_id_sha256",
        "scanner_executable_sha256", "scanner_version_sha256",
        "scan_policy_sha256", "scan_report_sha256",
    ):
        _hex(obj[key], key)
    if not isinstance(obj["build_context_file_count"], int) or obj["build_context_file_count"] < 4:
        raise CheckError("invalid build_context_file_count")
    if not isinstance(obj["scan_severity_selection"], str) or not re.fullmatch(
        r"(?:UNKNOWN|LOW|MEDIUM|HIGH|CRITICAL)(?:,(?:UNKNOWN|LOW|MEDIUM|HIGH|CRITICAL))*",
        obj["scan_severity_selection"],
    ):
        raise CheckError("invalid scan severity selection")
    expected_flags = {
        "scan_completed": True, "scan_decision_recorded": False,
        "publish_attempted": False, "raw_identifiers_included": False,
        "result": "AWAITING_HUMAN_SCAN_DISPOSITION",
    }
    for key, expected in expected_flags.items():
        if obj[key] != expected:
            raise CheckError(f"unexpected preparation field: {key}")
    _timestamp(obj["prepared_at"], "prepared_at")
    _no_raw_identifiers(obj, "preparation receipt")


def check_approval(obj: dict[str, Any], expected: dict[str, str], require_approved: bool = True) -> None:
    _exact(obj, APPROVAL_KEYS, "publish approval")
    if obj["schema_version"] != "jcareer-opendart-worker-publish-approval-v1":
        raise CheckError("unexpected approval schema")
    if obj["scope"] != "serverless-opendart-worker-publish":
        raise CheckError("approval scope mismatch")
    if require_approved and obj["decision"] != "APPROVED_FOR_SINGLE_PUBLISH":
        raise CheckError("pending or non-approved record cannot authorize publication")
    if not isinstance(obj["approval_ref"], str) or not APPROVAL_REF.fullmatch(obj["approval_ref"]):
        raise CheckError("invalid approval_ref")
    if not isinstance(obj["reviewer_ref"], str) or not REVIEWER_REF.fullmatch(obj["reviewer_ref"]):
        raise CheckError("invalid reviewer_ref")
    if not isinstance(obj["operation_ref"], str) or not OPERATION_REF.fullmatch(obj["operation_ref"]):
        raise CheckError("invalid operation_ref")
    approved_at = _timestamp(obj["approved_at"], "approved_at")
    expires_at = _timestamp(obj["expires_at"], "expires_at")
    if expires_at <= approved_at or (expires_at - approved_at).total_seconds() > 24 * 3600:
        raise CheckError("approval validity must be positive and no longer than 24 hours")
    if require_approved:
        now = datetime.now(timezone.utc)
        if now < approved_at or now > expires_at:
            raise CheckError("approval is not currently valid")
    if obj["expected_region"] != "ap-northeast-2":
        raise CheckError("unexpected region")
    if require_approved:
        if obj["scan_human_disposition"] != "HUMAN_APPROVED_FOR_SINGLE_SYNTHETIC_PUBLISH":
            raise CheckError("scan lacks explicit human disposition")
    elif obj["scan_human_disposition"] not in {
        "PENDING_HUMAN_DECISION", "HUMAN_APPROVED_FOR_SINGLE_SYNTHETIC_PUBLISH"
    }:
        raise CheckError("invalid scan_human_disposition")
    if obj["synthetic_data_only"] is not True:
        raise CheckError("synthetic_data_only acknowledgement required")
    if not isinstance(obj["image_tag"], str) or not TAG.fullmatch(obj["image_tag"]):
        raise CheckError("invalid unique image_tag")
    if not isinstance(obj["source_revision"], str) or not REVISION.fullmatch(obj["source_revision"]):
        raise CheckError("source_revision must be immutable hex")
    if not isinstance(obj["scan_policy_ref"], str) or not re.fullmatch(r"policy:[a-z0-9_-]{6,64}", obj["scan_policy_ref"]):
        raise CheckError("invalid scan_policy_ref")
    for key in APPROVAL_KEYS & {k for k in obj if k.endswith("_sha256")}:
        _hex(obj[key], key)
    for key, value in expected.items():
        if obj.get(key) != value:
            raise CheckError(f"approval binding mismatch: {key}")
    _no_raw_identifiers(obj, "publish approval")


def check_publish_receipt(obj: dict[str, Any]) -> None:
    _exact(obj, PUBLISH_KEYS, "publish receipt")
    if obj["schema_version"] != "jcareer-redacted-opendart-worker-publish-receipt-v1":
        raise CheckError("unexpected publish receipt schema")
    if obj["scope"] != "serverless-opendart-worker-publish":
        raise CheckError("publish receipt scope mismatch")
    for key in PUBLISH_KEYS & {k for k in obj if k.endswith("_sha256")}:
        _hex(obj[key], key)
    if not DIGEST.fullmatch(str(obj["ecr_image_digest"])) or not DIGEST.fullmatch(
        str(obj["docker_push_reported_digest"])
    ):
        raise CheckError("invalid publication digest")
    if obj["ecr_image_digest"] != obj["docker_push_reported_digest"]:
        raise CheckError("Docker/ECR publication digest mismatch")
    expected = {
        "private_uri_artifact_created": True,
        "resource_identifiers_included": False,
        "protected_input_snapshot_count": 9,
        "docker_auth_cleanup_observed": True,
        "local_artifact_cleanup_claimed": False,
        "human_release_decision_created": False,
        "result": "PUBLISH_COMPLETED_PENDING_RUNTIME_PLAN",
    }
    for key, value in expected.items():
        if obj[key] != value:
            raise CheckError(f"unexpected publish receipt field: {key}")
    _timestamp(obj["completed_at"], "completed_at")
    _no_raw_identifiers(obj, "publish receipt")


def static_audit(root: Path) -> None:
    script = (root / "scripts" / "Invoke-ApprovedOpenDartWorkerPublish.ps1").read_text(encoding="utf-8")
    example = _load(root / "terraform" / "serverless-opendart" / "worker-publish-approval.example.json")
    check_approval(example, {}, require_approved=False)
    if example["decision"] != "PENDING_HUMAN_DECISION":
        raise CheckError("repository example must remain pending")
    required = [
        "jcareer-opendart-worker-source-v1", "docker build", "trivy image",
        "'--platform','linux/amd64'", "linux/amd64",
        "AWAITING_HUMAN_SCAN_DISPOSITION", "terraform output -raw ecr_repository_url",
        "BINDINGS_CAPTURED_PENDING_HUMAN_DECISION",
        "JCAREER_SYNTHETIC_OPENDART_PUBLISH_BINDINGS_REVIEW",
        "RAW_ACCOUNT_AND_REPOSITORY_IDENTIFIERS_NOT_EMITTED=true",
        "$script:TrustedRepositoryRoot", "publisher must execute from its fixed trusted repository path",
        "Assert-PublishApprovalInline $approval $bindings", "Copy-ProtectedInput", "Write-AtomicJournal",
        "get-caller-identity", "'ecr','describe-repositories'", "IMMUTABLE", "scanOnPush",
        "ecr batch-get-image", "docker push", "docker_auth_cleanup_observed",
        "ecr describe-images", "PUBLISH_COMPLETED_PENDING_RUNTIME_PLAN",
        "FAILED_REQUIRES_HUMAN_DISPOSITION", "local_artifact_cleanup_claimed",
        "New-CurrentUserFileAcl", "Assert-NoReparsePathChain",
        "[Security.AccessControl.FileSystemRights]::WriteData",
        "$script:JournalOwned = $false", "if ($script:JournalOwned -and $script:JournalPath",
        "operation reference and mode already have retained artifacts",
    ]
    lowered = script.lower()
    for token in required:
        if token.lower() not in lowered:
            raise CheckError(f"publisher source is missing required token: {token}")
    try:
        order = [lowered.index(x) for x in ("'ecr','batch-get-image'", "'push',$remotetag", "'ecr','describe-images'")]
    except ValueError as exc:
        raise CheckError("ECR uniqueness/push/digest invocation is incomplete") from exc
    if order != sorted(order):
        raise CheckError("ECR uniqueness/push/digest order is not explicit")
    if re.search(r"\bRemove-Item\b", script, flags=re.IGNORECASE):
        raise CheckError("publisher must not automatically remove protected artifacts")
    if re.search(r"\[string\]\s*\$RepositoryRoot", script, flags=re.IGNORECASE):
        raise CheckError("publisher repository root must not be caller-controlled")
    unsafe_log = re.compile(r"Write-(?:Host|Output|Information|Verbose|Warning).*\$(?:account|repositoryUrl|digestPinnedUri|loginPassword)", re.I)
    if unsafe_log.search(script):
        raise CheckError("publisher may log a sensitive raw value")
    if "decision='PENDING_HUMAN_DECISION'" not in script or "scan_human_disposition='PENDING_HUMAN_DECISION'" not in script:
        raise CheckError("review mode must create only a pending human-decision draft")
    try:
        inline = lowered.index("assert-publishapprovalinline $approval $bindings")
        external = lowered.index("human approval validation", inline)
        push = lowered.index("'push',$remotetag", external)
    except ValueError as exc:
        raise CheckError("approval checks or guarded push invocation are incomplete") from exc
    if not inline < external < push:
        raise CheckError("independent and external approval checks must precede push")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p_static = sub.add_parser("static")
    p_static.add_argument("--root", type=Path, required=True)
    p_bootstrap = sub.add_parser("bootstrap")
    p_bootstrap.add_argument("--receipt", type=Path, required=True)
    p_bootstrap.add_argument("--backend-config-sha256", required=True)
    p_prep = sub.add_parser("preparation")
    p_prep.add_argument("--receipt", type=Path, required=True)
    p_approval = sub.add_parser("approval")
    p_approval.add_argument("--approval", type=Path, required=True)
    p_approval.add_argument("--expected", action="append", default=[])
    p_receipt = sub.add_parser("publish-receipt")
    p_receipt.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "static":
            static_audit(args.root.resolve())
        elif args.command == "bootstrap":
            check_bootstrap_receipt(_load(args.receipt), args.backend_config_sha256)
        elif args.command == "preparation":
            check_preparation(_load(args.receipt))
        elif args.command == "approval":
            expected: dict[str, str] = {}
            for item in args.expected:
                if "=" not in item:
                    raise CheckError("--expected must be key=value")
                key, value = item.split("=", 1)
                if key not in APPROVAL_KEYS or not key:
                    raise CheckError("unknown expected binding key")
                expected[key] = value
            check_approval(_load(args.approval), expected, require_approved=True)
        else:
            check_publish_receipt(_load(args.receipt))
    except CheckError as exc:
        print(f"OPENDART_WORKER_PUBLISH_CHECK=FAIL:{exc}", file=sys.stderr)
        return 1
    print("OPENDART_WORKER_PUBLISH_CHECK=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
