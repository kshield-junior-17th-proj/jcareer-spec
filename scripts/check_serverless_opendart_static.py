#!/usr/bin/env python3
"""Validate the AWS-free OpenDART serverless source and saved-plan boundary."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable


SOURCE_FILES = ("main.tf", "outputs.tf", "variables.tf", "versions.tf")
EXPECTED_RESOURCES = Counter(
    {
        "aws_ecr_repository": 1,
        "aws_ecr_lifecycle_policy": 1,
        "aws_sqs_queue": 2,
        "aws_dynamodb_table": 1,
        "aws_cloudwatch_log_group": 1,
        "aws_iam_role": 1,
        "aws_iam_role_policy": 2,
        "aws_lambda_function": 1,
        "aws_lambda_event_source_mapping": 1,
    }
)
BOOTSTRAP_PLAN_ADDRESSES = frozenset(
    {
        "aws_cloudwatch_log_group.worker[0]",
        "aws_dynamodb_table.results[0]",
        "aws_ecr_lifecycle_policy.worker[0]",
        "aws_ecr_repository.worker[0]",
        "aws_iam_role.worker[0]",
        "aws_iam_role_policy.worker[0]",
        "aws_sqs_queue.dead_letter[0]",
        "aws_sqs_queue.refresh[0]",
    }
)
EXPECTED_PLAN_ADDRESSES = {
    "disabled": frozenset(),
    "bootstrap": BOOTSTRAP_PLAN_ADDRESSES,
    "runtime": BOOTSTRAP_PLAN_ADDRESSES
    | {
        "aws_iam_role_policy.api[0]",
        "aws_lambda_event_source_mapping.refresh[0]",
        "aws_lambda_function.worker[0]",
    },
}


def load_sources(root: Path) -> dict[str, str]:
    module = root / "terraform" / "serverless-opendart"
    supporting = {
        "worker": root / "src/runtime/opendart_worker/handler.py",
        "worker_dockerfile": root / "src/runtime/opendart_worker/Dockerfile",
        "dispatch": root / "src/runtime/api/app/opendart_dispatch.py",
        "results": root / "src/runtime/api/app/opendart_results.py",
        "api": root / "src/runtime/api/app/main.py",
        "broker": root / "src/runtime/aws_broker/app/main.py",
        "broker_client": root / "src/runtime/api/app/aws_broker_client.py",
        "broker_compose": root / "terraform/lab/provisioning/opendart-broker.compose.override.yaml",
        "approval": module / "approval.example.json",
        "readme": module / "README.md",
    }
    missing = [name for name in SOURCE_FILES if not (module / name).is_file()]
    missing.extend(
        str(path.relative_to(root)) for path in supporting.values() if not path.is_file()
    )
    if missing:
        raise FileNotFoundError("missing OpenDART source: " + ", ".join(missing))
    terraform_paths = sorted(module.glob("*.tf"))
    return {
        **{name.removesuffix(".tf"): (module / name).read_text(encoding="utf-8") for name in SOURCE_FILES},
        **{key: path.read_text(encoding="utf-8") for key, path in supporting.items()},
        "terraform_file_names": "\n".join(path.name for path in terraform_paths),
        "terraform_all": "\n".join(path.read_text(encoding="utf-8") for path in terraform_paths),
    }


def audit_sources(sources: dict[str, str]) -> list[str]:
    errors: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    def forbid(condition: bool, message: str) -> None:
        if condition:
            errors.append(message)

    terraform_all = sources["terraform_all"]
    main = sources["main"]
    variables = sources["variables"]
    outputs = sources["outputs"]
    worker = sources["worker"]
    results = sources["results"]
    api = sources["api"]
    approval = json.loads(sources["approval"])

    require(
        set(sources["terraform_file_names"].splitlines()) == set(SOURCE_FILES),
        "OpenDART root contains an unexpected or missing top-level .tf file",
    )
    observed = Counter(re.findall(r'resource\s+"([^"]+)"\s+"', terraform_all))
    require(observed == EXPECTED_RESOURCES, "OpenDART resource block inventory drifted")
    require(not re.findall(r'data\s+"([^"]+)"\s+"', terraform_all), "Terraform data sources are forbidden")
    require('required_version = "= 1.15.9"' in sources["versions"], "Terraform version must remain pinned")
    require('version = "= 6.59.0"' in sources["versions"], "AWS provider version must remain pinned")
    require('backend "s3"' in sources["versions"] and "use_lockfile = true" in sources["versions"], "encrypted locking remote state backend is missing")
    require('default     = "disabled"' in variables, "deployment must default to disabled")
    require(
        'var.activation_acknowledgement == "JCAREER_OPENDART_SERVERLESS_APPROVED"' in main,
        "explicit OpenDART human acknowledgement is missing",
    )
    require(
        'can(regex("^APPROVAL-[A-Z0-9_-]{8,64}$", var.approval_ref))' in main,
        "pseudonymous approval reference gate is missing",
    )
    require(
        'image_tag_mutability = "IMMUTABLE"' in main
        and "scan_on_push = true" in main
        and "force_delete         = true" in main,
        "ECR immutability, scan, or approved-teardown cleanup is missing",
    )
    require(
        'startswith(var.lambda_image_uri, "${aws_ecr_repository.worker[0].repository_url}@sha256:")' in main
        and 'can(regex("@sha256:[0-9a-f]{64}$", var.lambda_image_uri))' in main,
        "Lambda image must be digest-pinned to this root's repository",
    )
    require(main.count("fifo_queue") == 2, "request and DLQ must both remain FIFO")
    require(main.count("sqs_managed_sse_enabled") == 2, "both queues require SQS managed encryption")
    require("redrive_policy" in main and "maxReceiveCount" in main, "bounded DLQ redrive is missing")
    require('function_response_types            = ["ReportBatchItemFailures"]' in main, "partial batch reporting is missing")
    require('billing_mode = "PAY_PER_REQUEST"' in main, "DynamoDB must remain on-demand")
    require('attribute_name = "expires_at"' in main and "enabled        = true" in main, "DynamoDB TTL is missing")
    require("reserved_concurrent_executions = 1" in main and "timeout       = 30" in main, "Lambda cost bounds drifted")
    require("ssm:GetParameter" in main and "var.opendart_api_key_parameter_arn" in main, "exact SSM read boundary is missing")
    require(
        "opendart_api_key_kms_key_arn" in variables
        and 'Action   = ["kms:Decrypt"]' in main
        and '"kms:ViaService"' in main
        and '"kms:EncryptionContext:PARAMETER_ARN"' in main,
        "optional customer-managed SecureString KMS boundary is missing",
    )
    require("sqs:SendMessage" in main and "dynamodb:GetItem" in main and "dynamodb:DeleteItem" in main, "API dispatch/collect IAM is incomplete")
    require(
        "sqs:GetQueueUrl" in main
        and "OPENDART_REFRESH_QUEUE_NAME" in outputs
        and "OPENDART_RESULT_TABLE_NAME" in outputs
        and "OPENDART_REFRESH_QUEUE_URL" not in outputs,
        "OpenDART broker lookup permission or account-free runtime output drifted",
    )
    require(
        "SO_PEERCRED" in sources["broker"]
        and "/v1/opendart/refresh" in sources["broker"]
        and "/run/jcareer-opendart/broker.sock" in sources["broker_client"]
        and "network_mode: host" in sources["broker_compose"]
        and "ports:" not in sources["broker_compose"],
        "OpenDART API must use its fixed Unix-socket capability broker",
    )
    require("company_database_access     = false" in outputs and 'score_effect                = "NONE"' in outputs, "non-DB and no-score contract is missing")
    require("expected_company_name" in sources["dispatch"], "request must bind the public company name")
    require("attribute_not_exists(request_id)" in results and "ConsistentRead=True" in results, "create-only consistent result store is missing")
    require(
        '"#expires_at": "expires_at"' in results
        and "OpenDartResultExpired" in results
        and "expires_at <= int(observed_at" in results
        and "except OpenDartResultExpired:" in api
        and '"error_category": "RESULT_EXPIRED"' in api,
        "application-enforced result expiry and pending-state recovery are incomplete",
    )
    require("RESULT_MAX_BYTES = 220_000" in results and "compare_digest" in results, "bounded hashed result contract is missing")
    require("process_refresh_to_durable_result" in worker and "FIFO ordering" in worker, "worker durable-result/FIFO handling is missing")
    require(
        "OPENDART_RESULT_TABLE" in results
        and "PostgresCompanySnapshotRepository" not in worker
        and "DATABASE_URL" not in worker
        and "psycopg" not in worker,
        "worker source must not contain a company-DB connection path",
    )
    require("get_refresh_result(request_id)" in api and "delete_refresh_result(request_id, company.id)" in api, "API result collector is missing")
    require("company.opendart_pending_corp_code" in api and "company_names_match(company.name, dart_name)" in api, "collector binding checks are incomplete")
    require(
        "Company.opendart_pending_request_id.is_(None)" in api
        and api.count("Company.opendart_pending_request_id == request_id") >= 3
        and '"ALREADY_PENDING"' in api
        and '"RESULT_TIMEOUT"' in api,
        "OpenDART pending CAS, idempotency, or bounded timeout is missing",
    )
    require("COPY api/app" in sources["worker_dockerfile"] and 'CMD ["handler.lambda_handler"]' in sources["worker_dockerfile"], "worker image package is incomplete")
    require(approval.get("decision") == "PENDING_HUMAN_DECISION", "example approval must remain pending")
    require(not approval.get("approval_ref") and not approval.get("saved_plan_sha256"), "example approval must not authorize a plan")

    folded = terraform_all.casefold()
    forbidden = {
        "aws_nat_gateway": "NAT Gateway is outside the serverless design",
        "vpc_config": "Lambda must stay outside the VPC",
        "company_database_url": "database URLs must not enter Terraform",
        "aws_db_instance": "OpenDART must not create a database",
        "aws_ssm_parameter\"": "the API key value must not be managed by this root",
        "aws_secretsmanager_secret": "the API key store is externally managed",
        "aws_instance": "EC2 belongs to separate roots",
    }
    for term, message in forbidden.items():
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
    outputs = ((plan.get("planned_values") or {}).get("outputs") or {})
    deployment = outputs.get("deployment_stage") if isinstance(outputs, dict) else None
    if isinstance(deployment, dict) and isinstance(deployment.get("value"), str):
        return str(deployment["value"])
    changes = plan.get("output_changes") or {}
    deployment = changes.get("deployment_stage") if isinstance(changes, dict) else None
    if isinstance(deployment, dict) and isinstance(deployment.get("after"), str):
        return str(deployment["after"])
    return None


def audit_plan_document(plan: dict[str, object]) -> list[str]:
    errors: list[str] = []
    root_module = ((plan.get("planned_values") or {}).get("root_module") or {})
    resources = list(_walk_module(root_module)) if isinstance(root_module, dict) else []
    addresses = {str(row.get("address")) for row in resources if isinstance(row.get("address"), str)}
    stage = _planned_stage(plan)
    expected = EXPECTED_PLAN_ADDRESSES.get(stage or "")
    if expected is None:
        errors.append("OpenDART plan lacks a recognized deployment_stage")
    elif addresses != expected:
        errors.append(
            f"OpenDART {stage} plan address mismatch: expected={len(expected)} observed={len(addresses)}"
        )
    allowed_types = set(EXPECTED_RESOURCES)
    for resource in resources:
        if resource.get("type") not in allowed_types:
            errors.append(f"unapproved OpenDART resource type: {resource.get('type')}")
    for change in plan.get("resource_changes", []) or []:
        actions = ((change.get("change") or {}).get("actions") or []) if isinstance(change, dict) else []
        if "delete" in actions:
            errors.append("OpenDART saved plan contains delete or replacement")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--plan")
    args = parser.parse_args()
    try:
        sources = load_sources(Path(args.root).resolve())
        errors = audit_sources(sources)
        stage = "not-checked"
        count = "not-checked"
        if args.plan:
            plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
            errors.extend(audit_plan_document(plan))
            stage = _planned_stage(plan) or "unknown"
            module = ((plan.get("planned_values") or {}).get("root_module") or {})
            count = str(len(list(_walk_module(module))) if isinstance(module, dict) else 0)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        print(f"::error::{type(exc).__name__}: {exc}")
        return 1
    print(f"serverless OpenDART source inventory: resource_blocks=11 plan_stage={stage} plan_resources={count}")
    for error in errors:
        print(f"::error::{error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
