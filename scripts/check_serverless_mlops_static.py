#!/usr/bin/env python3
"""Validate the isolated synthetic serverless MLOps Terraform boundary.

This checker is source/plan validation only. It does not call AWS and it does
not assess model quality, fairness, compliance, or release readiness.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable


SOURCE_FILES = (
    "main.tf",
    "outputs.tf",
    "variables.tf",
    "versions.tf",
)
EXPECTED_RESOURCES = Counter(
    {
        "aws_ecr_repository": 1,
        "aws_ecr_lifecycle_policy": 1,
        "aws_s3_bucket": 1,
        "aws_s3_bucket_public_access_block": 1,
        "aws_s3_bucket_policy": 1,
        "aws_s3_bucket_ownership_controls": 1,
        "aws_s3_bucket_server_side_encryption_configuration": 1,
        "aws_s3_bucket_versioning": 1,
        "aws_s3_bucket_lifecycle_configuration": 1,
        "aws_dynamodb_table": 1,
        "aws_cloudwatch_log_group": 1,
        "aws_iam_role": 1,
        "aws_iam_role_policy": 1,
        "aws_lambda_function": 1,
    }
)
ALLOWED_PLAN_RESOURCE_TYPES = set(EXPECTED_RESOURCES)
BOOTSTRAP_PLAN_ADDRESSES = frozenset(
    {
        "aws_cloudwatch_log_group.mlops[0]",
        "aws_dynamodb_table.runs[0]",
        "aws_ecr_lifecycle_policy.mlops[0]",
        "aws_ecr_repository.mlops[0]",
        "aws_iam_role.lambda[0]",
        "aws_iam_role_policy.lambda[0]",
        "aws_s3_bucket.artifacts[0]",
        "aws_s3_bucket_lifecycle_configuration.artifacts[0]",
        "aws_s3_bucket_ownership_controls.artifacts[0]",
        "aws_s3_bucket_policy.artifacts[0]",
        "aws_s3_bucket_public_access_block.artifacts[0]",
        "aws_s3_bucket_server_side_encryption_configuration.artifacts[0]",
        "aws_s3_bucket_versioning.artifacts[0]",
    }
)
EXPECTED_PLAN_ADDRESSES = {
    "disabled": frozenset(),
    "bootstrap": BOOTSTRAP_PLAN_ADDRESSES,
    "runtime": BOOTSTRAP_PLAN_ADDRESSES | {"aws_lambda_function.trainer[0]"},
}


def load_sources(root: Path) -> dict[str, str]:
    module = root / "terraform" / "serverless-mlops"
    missing = [name for name in SOURCE_FILES if not (module / name).is_file()]
    supporting = {
        "operator": module / "provisioning" / "invoke-synthetic-demo.ps1",
        "exporter_dockerfile": root / "src" / "mlops" / "Dockerfile.exporter",
        "lambda_dockerfile": root / "src" / "mlops" / "Dockerfile.lambda",
        "lambda_handler": root / "src" / "mlops" / "lambda_handler.py",
        "exporter_source": root / "src" / "mlops" / "export_runtime_training.py",
        "review_source": root / "src" / "mlops" / "review_challenger.py",
        "mlops_readme": root / "src" / "mlops" / "README.md",
    }
    missing.extend(
        str(path.relative_to(root)) for path in supporting.values() if not path.is_file()
    )
    if missing:
        raise FileNotFoundError("missing serverless MLOps source: " + ", ".join(missing))
    paths = sorted(module.glob("*.tf"))
    return {
        "main": (module / "main.tf").read_text(encoding="utf-8"),
        "variables": (module / "variables.tf").read_text(encoding="utf-8"),
        "outputs": (module / "outputs.tf").read_text(encoding="utf-8"),
        "versions": (module / "versions.tf").read_text(encoding="utf-8"),
        **{key: path.read_text(encoding="utf-8") for key, path in supporting.items()},
        "terraform_file_names": "\n".join(path.name for path in paths),
        "terraform_all": "\n".join(path.read_text(encoding="utf-8") for path in paths),
    }


def audit_sources(sources: dict[str, str]) -> list[str]:
    errors: list[str] = []
    main = sources["main"]
    variables = sources["variables"]
    outputs = sources["outputs"]
    versions = sources["versions"]
    operator = sources["operator"]
    exporter_dockerfile = sources["exporter_dockerfile"]
    lambda_dockerfile = sources["lambda_dockerfile"]
    lambda_handler = sources["lambda_handler"]
    exporter_source = sources["exporter_source"]
    review_source = sources["review_source"]
    mlops_readme = sources["mlops_readme"]
    terraform_all = sources["terraform_all"]

    def require(observed: bool, message: str) -> None:
        if not observed:
            errors.append(message)

    def forbid(observed: bool, message: str) -> None:
        if observed:
            errors.append(message)

    require(
        set(sources["terraform_file_names"].splitlines()) == set(SOURCE_FILES),
        "serverless MLOps root contains an unexpected or missing top-level .tf file",
    )
    observed_resources = Counter(re.findall(r'resource\s+"([^"]+)"\s+"', terraform_all))
    require(
        observed_resources == EXPECTED_RESOURCES,
        "serverless MLOps resource blocks differ from the reviewed exact source inventory",
    )
    require(
        re.findall(r'data\s+"([^"]+)"\s+"', terraform_all) == [],
        "serverless MLOps root must not contain Terraform data sources",
    )
    require('required_version = "= 1.15.9"' in versions, "Terraform version must remain pinned")
    require('version = "= 6.59.0"' in versions, "AWS provider version must remain pinned")

    require('default     = "disabled"' in variables, "deployment must default to disabled")
    require(
        'var.activation_acknowledgement == "JCAREER_SYNTHETIC_SERVERLESS_MLOPS_APPROVED"'
        in main,
        "explicit synthetic serverless acknowledgement is missing",
    )
    require(
        'image_tag_mutability = "IMMUTABLE"' in main
        and "scan_on_push = true" in main,
        "ECR immutability and scan-on-push are required",
    )
    require(
        '"${aws_ecr_repository.mlops[0].repository_url}@sha256:"' in main
        and 'can(regex("@sha256:[0-9a-f]{64}$", var.lambda_image_uri))' in main,
        "Lambda image must be digest-pinned to the repository managed by this root",
    )
    require("block_public_acls       = true" in main, "S3 public ACL blocking is missing")
    require("block_public_policy     = true" in main, "S3 public policy blocking is missing")
    require("restrict_public_buckets = true" in main, "S3 public bucket restriction is missing")
    require(
        'Sid       = "DenyInsecureTransport"' in main
        and '"aws:SecureTransport" = "false"' in main,
        "S3 TLS-only bucket policy is missing",
    )
    require(
        'sse_algorithm = "AES256"' in main,
        "artifact bucket must retain the currently wired SSE-S3 encryption",
    )
    forbid(
        "bucket_key_enabled" in main,
        "SSE-S3 must not declare the SSE-KMS-only S3 Bucket Key option",
    )
    require('billing_mode = "PAY_PER_REQUEST"' in main, "DynamoDB must remain on-demand")
    require("reserved_concurrent_executions = 1" in main, "Lambda concurrency must remain one")
    require("timeout       = 300" in main, "Lambda timeout must remain bounded at 300 seconds")
    require(
        "var.lambda_memory_mb >= 512 && var.lambda_memory_mb <= 2048" in variables,
        "Lambda memory range must remain 512..2048 MiB",
    )
    require(
        re.search(r'MLOPS_SOURCE_MODE\s*=\s*"feature_snapshot"', main) is not None,
        "Lambda must remain on the feature-snapshot source mode",
    )
    require(
        "MLOPS_FEATURE_SNAPSHOT_BUCKET" in main
        and "MLOPS_FEATURE_SNAPSHOT_ROOT" in main,
        "feature snapshot bucket and bounded root environment are missing",
    )
    require(
        'source_prefix = "mlops/sources/"' in main
        and 'result_prefix = "mlops/runs/"' in main,
        "bounded source and result prefixes are missing",
    )
    require(
        'automatic_model_activation = false' in outputs,
        "automatic model activation must remain false",
    )
    require('schedule_enabled           = false' in outputs, "scheduled training must remain disabled")
    require(
        "COPY run_snapshot_pipeline.py" in lambda_dockerfile,
        "Lambda image is missing the feature-snapshot pipeline module",
    )
    require(
        "COPY review_challenger.py" in lambda_dockerfile,
        "Lambda image is missing the bounded human-review module",
    )
    require(
        "record_human_review" in lambda_handler
        and "ConditionExpression" in lambda_handler
        and "attribute_not_exists(review_receipt_sha256)" in lambda_handler
        and 'ReturnValues="ALL_NEW"' in lambda_handler,
        "human review must use and validate the conditional single-record transition",
    )
    require(
        '"IfNoneMatch": "*"' in lambda_handler
        and 'response.get("VersionId")' in lambda_handler
        and "artifact_bindings_json=canonical_json(artifact_bindings)" in lambda_handler,
        "six result artifacts must be create-only and version-bound",
    )
    require(
        '"ServerSideEncryption": "AES256"' in lambda_handler,
        "Lambda result uploads must use the currently wired SSE-S3 encryption",
    )
    forbid(
        "MLOPS_ARTIFACT_KMS_KEY_ID" in lambda_handler
        or '"aws:kms"' in lambda_handler
        or "SSEKMSKeyId" in lambda_handler,
        "Lambda source must not expose an unwired SSE-KMS configuration path",
    )
    require(
        "synthetic_only = :synthetic_true" in lambda_handler
        and "artifact_count = :artifact_count" in lambda_handler
        and "model_state = :model_state" in lambda_handler
        and "runtime_ranking_wired = :false" in lambda_handler
        and "automatic_model_activation = :false" in lambda_handler
        and "release_authorized = :false" in lambda_handler,
        "human review condition must bind every synthetic non-activation invariant",
    )
    require(
        "def _transition_run_to_pending(" in lambda_handler
        and "#state = :running_state AND human_input_state = :not_recorded" in lambda_handler
        and "AND source_mode = :source_mode" in lambda_handler
        and "attribute_not_exists(artifact_bindings)" in lambda_handler
        and 'ReturnValues="ALL_NEW"' in lambda_handler,
        "training completion must conditionally transition the unchanged RUNNING state",
    )
    require(
        "for member in members.values():" in exporter_source
        and "_assert_synthetic_member(member)" in exporter_source
        and "_assert_synthetic_company_job_source(raw_jobs)" in exporter_source
        and "EXPECTED_SEED_COMPANY_PROFILE_VERSION" in exporter_source
        and "if any(dangling_reference_counts.values()):" in exporter_source
        and "rejected an unresolved consent subject" in exporter_source
        and exporter_source.index("for member in members.values():")
        < exporter_source.index('source_material = {'),
        "the complete member/reference read set must pass synthetic checks before lineage persistence",
    )
    require(
        "_recorded_review_response" in lambda_handler
        and "human review retry conflicts" in lambda_handler
        and "RECORDED_REVIEW_STATE" in lambda_handler,
        "identical human-review retries must be idempotent and conflicts rejected",
    )
    require(
        "EXPECTED_ARTIFACT_FILES" in review_source
        and "human_input_record_only" in review_source
        and 'REVIEW_DECISIONS = frozenset({"APPROVED", "REJECTED"})' in review_source
        and 'RECORDED_REVIEW_STATE = "HUMAN_INPUT_RECORDED"' in review_source
        and '"decision_scope": DECISION_SCOPE' in review_source
        and '"release_authorized": False' in review_source,
        "human review must remain version-bound input recording without release authorization",
    )
    require(
        "부분 객체" in mlops_readme
        and "DynamoDB 상태만" in mlops_readme,
        "documentation must forbid treating partial S3 objects as run success",
    )
    forbid(
        '"automatic_model_activation": True' in lambda_handler
        or '"runtime_ranking_wired": True' in lambda_handler
        or '"automatic_model_activation": True' in review_source
        or '"runtime_ranking_wired": True' in review_source,
        "human review source must not activate a model or connect runtime ranking",
    )
    forbid(
        "approval_state = :decision" in lambda_handler,
        "APPROVED or REJECTED must not be stored as a release-like approval state",
    )
    require(
        "ENTRYPOINT" in exporter_dockerfile
        and "export_runtime_training.py" in exporter_dockerfile,
        "ephemeral exporter image contract is missing",
    )
    require(
        "$Invoke -and -not $Apply" in operator
        and "Plan-only is the default" in operator,
        "operator workflow must require Apply plus Invoke for a demonstration",
    )
    require(
        "Assert-NonDestructivePlan" in operator
        and "Contains('delete')" in operator,
        "operator workflow must reject delete and replacement plans",
    )
    require(
        "jcareer-asis-runtime_default" in operator
        and '"mlops/sources/$RunId/"' in operator,
        "operator workflow must use the internal Compose network and bounded source prefix",
    )
    require(
        "image-scan-complete" in operator
        and "CRITICAL" in operator
        and "HIGH" in operator
        and '"$repositoryUrl@$digest"' in operator,
        "operator workflow must scan and digest-pin the Lambda image",
    )
    require(
        "TRAINED_PENDING_HUMAN_REVIEW" in operator
        and "automatic_model_activation" in operator
        and "$resultFiles" in operator,
        "operator workflow must verify the six-artifact non-activation contract",
    )
    require(
        "[REDACTED_ACCOUNT]" in operator
        and "[REDACTED_ARN]" in operator
        and "[REDACTED_RESOURCE_ID]" in operator
        and "[REDACTED_SECRET]" in operator,
        "operator diagnostics must redact identifiers and credentials",
    )
    require(
        "[string]$ProviderAccountSha256" in operator
        and "Get-ObservedProviderAccountSha256" in operator
        and "Assert-ProviderAccountBinding" in operator
        and "provider_account_sha256" in operator
        and "--query', 'Account'" in operator
        and "Get-StringSha256 -Value $account" in operator
        and "Provider account binding changed before" in operator,
        "operator approval must bind a fail-closed provider account SHA-256 without logging the raw account ID",
    )
    require(
        "Resolve-RequiredExecutable" in operator
        and "CommandType -ne 'Application'" in operator
        and "[IO.Path]::IsPathRooted($path)" in operator
        and "$script:ToolPaths.aws" in operator
        and "$script:ToolPaths.docker" in operator
        and "$script:ToolPaths.python" in operator
        and "$script:ToolPaths.terraform" in operator
        and "$script:ToolPaths.tar" in operator,
        "operator tools must be resolved once to direct absolute executables and reject command shadowing",
    )
    require(
        "New-JCareerProtectedSnapshotSet" in operator
        and operator.count("Add-JCareerProtectedSnapshotFile") >= 3
        and "Get-ExactFileSha256" in operator
        and "Assert-SavedPlanExecutionContext" in operator
        and "$bootstrapContext.PlanPath" in operator
        and "$runtimeContext.PlanPath" in operator
        and "Remove-JCareerProtectedSnapshotSet" in operator
        and "plan.redacted.json" in operator
        and "Protect-PlanJson ($planOutput" in operator,
        "saved plans, redacted plan JSON, and approval context must stay read-locked and hash-bound through apply",
    )
    forbid(
        re.search(r"(?m)&\s+(?:aws|docker|python|terraform|tar\.exe)\b", operator)
        is not None,
        "operator must not invoke a shadowable tool name directly",
    )
    forbid(
        re.search(r"(?i)\b(?:stop|terminate)-instances\b|terraform\s+destroy", operator)
        is not None,
        "operator workflow must never stop, terminate, or destroy the lab",
    )

    forbidden_terms = {
        "aws_sagemaker_": "SageMaker resources are outside the serverless MLOps demo boundary",
        "member_database_url": "database URLs must not enter Terraform state or Lambda environment",
        "company_database_url": "database URLs must not enter Terraform state or Lambda environment",
        "vpc_config": "feature-snapshot Lambda must not join the lab VPC",
        "aws_cloudwatch_event": "scheduled training is not enabled in this demo root",
        "aws_vpc_endpoint": "VPC endpoints are unnecessary in feature-snapshot mode",
        "aws_security_group": "security groups are unnecessary in feature-snapshot mode",
        "aws_instance": "EC2 belongs to the separate lab root",
        "aws_db_instance": "RDS is outside the serverless MLOps demo boundary",
        "aws_nat_gateway": "NAT Gateway is outside the serverless MLOps demo boundary",
        "aws_apigateway": "API Gateway is outside the one-shot operator demo boundary",
    }
    folded = terraform_all.casefold()
    for term, message in forbidden_terms.items():
        forbid(term in folded, message)
    return errors


def _walk_module(module: dict[str, object]) -> Iterable[dict[str, object]]:
    for resource in module.get("resources", []) or []:
        if isinstance(resource, dict):
            yield resource
    for child in module.get("child_modules", []) or []:
        if isinstance(child, dict):
            yield from _walk_module(child)


def _planned_stage(plan: dict[str, object]) -> str | None:
    planned_values = plan.get("planned_values")
    if isinstance(planned_values, dict):
        outputs = planned_values.get("outputs")
        if isinstance(outputs, dict):
            deployment = outputs.get("deployment_stage")
            if isinstance(deployment, dict) and isinstance(deployment.get("value"), str):
                return str(deployment["value"])
    output_changes = plan.get("output_changes")
    if isinstance(output_changes, dict):
        deployment = output_changes.get("deployment_stage")
        if isinstance(deployment, dict):
            after = deployment.get("after")
            if isinstance(after, str):
                return after
    return None


def audit_plan_document(plan: dict[str, object]) -> list[str]:
    errors: list[str] = []
    root_module = ((plan.get("planned_values") or {}).get("root_module") or {})
    resources = list(_walk_module(root_module)) if isinstance(root_module, dict) else []
    observed_types = Counter(str(resource.get("type")) for resource in resources)
    observed_addresses = {
        str(resource.get("address"))
        for resource in resources
        if isinstance(resource.get("address"), str)
    }
    stage = _planned_stage(plan)
    expected_addresses = EXPECTED_PLAN_ADDRESSES.get(stage or "")
    if expected_addresses is None:
        errors.append("serverless MLOps plan is missing a recognized deployment_stage output")
    elif observed_addresses != expected_addresses:
        missing = len(expected_addresses - observed_addresses)
        unexpected = len(observed_addresses - expected_addresses)
        errors.append(
            f"serverless MLOps {stage} plan address set mismatch: "
            f"expected={len(expected_addresses)} observed={len(observed_addresses)} "
            f"missing={missing} unexpected={unexpected}"
        )
    for resource_type, count in observed_types.items():
        if resource_type not in ALLOWED_PLAN_RESOURCE_TYPES:
            errors.append(f"unapproved serverless MLOps resource type: {resource_type}")
        if count > EXPECTED_RESOURCES.get(resource_type, 0):
            errors.append(f"too many planned resources of type {resource_type}: {count}")
    if len(resources) > sum(EXPECTED_RESOURCES.values()):
        errors.append("serverless MLOps plan exceeds the reviewed resource ceiling")

    for change in plan.get("resource_changes", []) or []:
        if not isinstance(change, dict):
            continue
        actions = ((change.get("change") or {}).get("actions") or [])
        if "delete" in actions:
            errors.append("serverless MLOps saved plan contains a delete or replacement action")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--plan")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    try:
        sources = load_sources(root)
        errors = audit_sources(sources)
        plan_resource_count = None
        plan_stage = None
        if args.plan:
            plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
            errors.extend(audit_plan_document(plan))
            plan_stage = _planned_stage(plan)
            module = ((plan.get("planned_values") or {}).get("root_module") or {})
            plan_resource_count = len(list(_walk_module(module))) if isinstance(module, dict) else 0
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        print(f"::error::{type(exc).__name__}: {exc}")
        return 1

    print(
        "serverless MLOps source inventory: "
        f"resource_blocks={sum(EXPECTED_RESOURCES.values())} "
        f"plan_stage={plan_stage if plan_stage is not None else 'not-checked'} "
        f"plan_resources={plan_resource_count if plan_resource_count is not None else 'not-checked'}"
    )
    for error in errors:
        print(f"::error::{error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
