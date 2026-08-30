#!/usr/bin/env python3
"""Validate endpoint image definitions without building an image or calling AWS."""

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
        "aws_imagebuilder_component": 2,
        "aws_iam_role": 2,
        "aws_iam_role_policy_attachment": 3,
        "aws_iam_instance_profile": 1,
        "aws_imagebuilder_image_recipe": 1,
        "aws_imagebuilder_infrastructure_configuration": 1,
        "aws_imagebuilder_distribution_configuration": 1,
        "aws_imagebuilder_image_pipeline": 1,
    }
)
DEFINITION_ADDRESSES = frozenset(
    {
        "aws_iam_instance_profile.builder[0]",
        "aws_iam_role.builder[0]",
        "aws_iam_role.lifecycle[0]",
        "aws_iam_role_policy_attachment.image_builder[0]",
        "aws_iam_role_policy_attachment.ssm[0]",
        "aws_iam_role_policy_attachment.lifecycle[0]",
        "aws_imagebuilder_component.build[0]",
        "aws_imagebuilder_component.test[0]",
        "aws_imagebuilder_distribution_configuration.windows[0]",
        "aws_imagebuilder_image_pipeline.windows[0]",
        "aws_imagebuilder_image_recipe.windows[0]",
        "aws_imagebuilder_infrastructure_configuration.windows[0]",
    }
)
EXPECTED_PLAN_ADDRESSES = {
    "disabled": frozenset(),
    "definition": DEFINITION_ADDRESSES,
}


def load_sources(root: Path) -> dict[str, str]:
    module = root / "terraform/workplace-images"
    supporting = {
        "contract": root / "fleet/images/endpoint_image_contract.yaml",
        "windows_build": root / "fleet/images/windows/build-component.yaml",
        "windows_test": root / "fleet/images/windows/test-component.yaml",
        "windows_session": root / "fleet/images/windows/Configure-JCareerSession.ps1",
        "windows_session_cleanup": root / "fleet/images/windows/Remove-JCareerSession.ps1",
        "mac_prepare": root / "fleet/images/macos/prepare-consultant.sh",
        "mac_session": root / "fleet/images/macos/configure-jcareer-session.sh",
        "mac_session_cleanup": root / "fleet/images/macos/remove-jcareer-session.sh",
        "mac_validate": root / "fleet/images/macos/validate-consultant.sh",
        "approval": module / "approval.example.json",
        "build_approval": module / "build-approval.example.json",
        "cleanup_approval": module / "cleanup-approval.example.json",
        "recovery_approval": module / "cleanup-recovery-approval.example.json",
        "image_build_operator": root / "scripts/Invoke-ApprovedWindowsImageBuild.ps1",
        "image_cleanup_operator": root / "scripts/Invoke-ApprovedWindowsImageCleanup.ps1",
        "endpoint_disposition_operator": root / "scripts/New-WindowsEndpointDispositionObservation.ps1",
        "deleted_recovery_operator": root / "scripts/New-WindowsImageDeletedRecoveryObservation.ps1",
        "protected_snapshot_module": root / "scripts/JCareer-ProtectedInputSnapshot.psm1",
    }
    missing = [name for name in SOURCE_FILES if not (module / name).is_file()]
    missing.extend(str(path.relative_to(root)) for path in supporting.values() if not path.is_file())
    if missing:
        raise FileNotFoundError("missing workplace image source: " + ", ".join(missing))
    tf_paths = sorted(module.glob("*.tf"))
    return {
        **{name.removesuffix(".tf"): (module / name).read_text(encoding="utf-8") for name in SOURCE_FILES},
        **{key: path.read_text(encoding="utf-8") for key, path in supporting.items()},
        "terraform_file_names": "\n".join(path.name for path in tf_paths),
        "terraform_all": "\n".join(path.read_text(encoding="utf-8") for path in tf_paths),
    }


def audit_sources(sources: dict[str, str]) -> list[str]:
    errors: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    def forbid(condition: bool, message: str) -> None:
        if condition:
            errors.append(message)

    all_tf = sources["terraform_all"]
    main = sources["main"]
    variables = sources["variables"]
    outputs = sources["outputs"]
    contract = sources["contract"]
    approval = json.loads(sources["approval"])
    build_approval = json.loads(sources["build_approval"])
    cleanup_approval = json.loads(sources["cleanup_approval"])
    recovery_approval = json.loads(sources["recovery_approval"])
    build_operator = sources["image_build_operator"]
    cleanup_operator = sources["image_cleanup_operator"]
    disposition_operator = sources["endpoint_disposition_operator"]
    recovery_operator = sources["deleted_recovery_operator"]
    snapshot_module = sources["protected_snapshot_module"]

    require(set(sources["terraform_file_names"].splitlines()) == set(SOURCE_FILES), "workplace root top-level .tf inventory drifted")
    observed = Counter(re.findall(r'resource\s+"([^"]+)"\s+"', all_tf))
    require(observed == EXPECTED_RESOURCES, "workplace image resource block inventory drifted")
    require(not re.findall(r'data\s+"([^"]+)"\s+"', all_tf), "workplace image root must not use data sources")
    require('required_version = "= 1.15.9"' in sources["versions"] and 'version = "= 6.59.0"' in sources["versions"], "Terraform/provider versions must remain pinned")
    require('backend "s3"' in sources["versions"] and "use_lockfile = true" in sources["versions"], "encrypted locking remote state backend is missing")
    require('default     = "disabled"' in variables, "workplace image root must default to disabled")
    require('var.activation_acknowledgement == "JCAREER_WINDOWS_IMAGE_DEFINITION_APPROVED"' in main, "human acknowledgement gate is missing")
    require('can(regex("^APPROVAL-[A-Z0-9_-]{8,64}$", var.approval_ref))' in main, "approval reference gate is missing")
    require('can(regex("^IMAGE-[A-Z0-9_-]{8,64}$", var.image_build_ref))' in main and "jk_image_build_ref" in main, "image build lineage reference is missing")
    require('instance_types                = ["t3.small"]' in main, "Image Builder instance must remain t3.small")
    require("terminate_instance_on_failure = true" in main, "failed build instances must terminate")
    require("resource_tags                 = local.common_tags" in main, "temporary build instances must carry the image lineage tags")
    require("EC2ImageBuilderLifecycleExecutionPolicy" in main and "imagebuilder.amazonaws.com" in main, "approved AMI and snapshot cleanup role is missing")
    require('http_tokens                 = "required"' in main and "http_put_response_hop_limit = 1" in main, "Image Builder must require IMDSv2")
    require("startswith(var.windows_parent_image, \"ssm:\")" not in variables and "[0-9]+\\\\.[0-9]+\\\\.[0-9]+$" in variables, "Windows parent image must be version-pinned")
    require("encrypted             = true" in main and 'volume_type           = "gp3"' in main, "encrypted gp3 recipe volume is required")
    require("image_tests_enabled = true" in main and "timeout_minutes     = 60" in main, "bounded image tests are required")
    require("schedule" not in main.casefold(), "automatic Image Builder schedule is forbidden")
    require(
        re.search(r"consultant_endpoint_count\s*=\s*0", outputs) is not None
        and re.search(r"macos_resources\s*=\s*0", outputs) is not None,
        "non-deployment and macOS zero-resource outputs are missing",
    )
    require(
        re.search(r"windows_11_claimed\s*=\s*false", outputs) is not None,
        "source must not claim Windows 11",
    )
    require("credentials_baked = $false" in sources["windows_build"] and "preview_url_baked = $false" in sources["windows_build"], "Windows image must bake no identity or preview token")
    require(
        "templatefile(" in main
        and "configure_session_script_b64" in main
        and "remove_session_script_b64" in main
        and "InstallSessionLifecycleScripts" in sources["windows_build"],
        "Windows session lifecycle scripts must be embedded in the reviewed image component",
    )
    require("AmazonSSMAgent" in sources["windows_test"] and "TermService" in sources["windows_test"], "Windows SSM/RDP image tests are missing")
    require(
        "fDenyTSConnections" in sources["windows_test"]
        and "Get-NetTCPConnection -State Listen -LocalPort 3389" in sources["windows_test"]
        and "Get-NetFirewallPortFilter -PolicyStore ActiveStore" in sources["windows_test"]
        and "Remote Desktop firewall rule is unavailable" in sources["windows_test"],
        "Windows RDP policy/listener/firewall image tests are missing",
    )
    require(
        "VerifyInteractiveBrowser" in sources["windows_build"]
        and "Microsoft Edge signature validation failed" in sources["windows_build"]
        and "Microsoft Edge signature validation failed" in sources["windows_test"]
        and "O=Microsoft Corporation" in sources["windows_test"],
        "Microsoft Edge presence and Microsoft publisher tests are missing",
    )
    require("Microsoft Defender PowerShell interface is unavailable" in sources["windows_build"] and "Microsoft Defender status interface is unavailable" in sources["windows_test"], "Defender absence must fail the image build")
    require(
        "ValidatePattern('^https://" in sources["windows_session"]
        and "$parsedPreview.Query" in sources["windows_session"]
        and "$parsedPreview.Fragment" in sources["windows_session"]
        and "ApprovedPreviewUrlSha256" in sources["windows_session"]
        and "JCareerSessionExpiry-" in sources["windows_session"]
        and "credentials_recorded = $false" in sources["windows_session"]
        and "J-Career approved preview.lnk" in sources["windows_session"]
        and "New-ScheduledTaskSettingsSet -StartWhenAvailable" in sources["windows_session"]
        and "JCAREER_SESSION_REMOVED=PASS" in sources["windows_session_cleanup"],
        "session setup must bind credential-free HTTPS, expiry cleanup, and no credential storage",
    )
    require("aws_resources_defined: false" in contract and "deployment_state: BLOCKED_BY_CURRENT_LAB_POLICY" in contract, "macOS policy block is missing")
    require('"credentials_baked": false' in sources["mac_prepare"] and '"posture_decision":"HUMAN"' in sources["mac_validate"] and "APPLE_SAFARI_REQUIRED_AT_PREPARATION" in sources["mac_prepare"], "macOS component boundaries are incomplete")
    require(
        "credential-free HTTPS" in sources["mac_session"]
        and "approved_url_sha256" in sources["mac_session"]
        and "MAC-0[1-3]" in sources["mac_session"]
        and "28800" in sources["mac_session"]
        and '"credentials_recorded": false' in sources["mac_session"]
        and "StartInterval" in sources["mac_session"]
        and "JCAREER_MACOS_SESSION_ARTIFACTS_REMOVED=PASS" in sources["mac_session_cleanup"]
        and "JCAREER_MACOS_COOKIE_CLEANUP=HUMAN_MDM_REQUIRED" in sources["mac_session_cleanup"]
        and "pkill -x Safari" in sources["mac_session_cleanup"]
        and "pkill -x Slack" in sources["mac_session_cleanup"]
        and "app.slack.com/client" in sources["mac_prepare"],
        "macOS consultant session hash, expiry cleanup, or SaaS shortcut boundary is incomplete",
    )
    require(approval.get("decision") == "PENDING_HUMAN_DECISION" and not approval.get("approval_ref"), "workplace approval example must remain pending")
    require(build_approval.get("decision") == "PENDING_HUMAN_DECISION" and not build_approval.get("approval_ref"), "image build approval example must remain pending")
    require(cleanup_approval.get("decision") == "PENDING_HUMAN_DECISION" and not cleanup_approval.get("approval_ref"), "image cleanup approval example must remain pending")
    require(
        recovery_approval.get("decision") == "PENDING_HUMAN_DECISION"
        and not recovery_approval.get("approval_ref")
        and recovery_approval.get("mutation_authorized") is False
        and recovery_approval.get("lifecycle_success_assertion_authorized") is False,
        "deleted-state recovery approval example must remain pending and read-only",
    )
    for label, operator in {
        "build": build_operator,
        "cleanup": cleanup_operator,
        "endpoint disposition": disposition_operator,
        "deleted-state recovery": recovery_operator,
    }.items():
        protected_temp = operator.find("New-ProtectedEmptyFile -Path $temporaryPath")
        content_write = re.search(r"\[IO\.File\]::WriteAllText\s*\(\s*\$temporaryPath", operator)
        require(
            protected_temp >= 0
            and "SetAccessRuleProtection($true, $false)" in operator
            and "[IO.File]::Replace($temporaryPath, $fullPath, $null)" in operator
            and "New-ProtectedEmptyFile -Path $stderrPath" in operator
            and content_write is not None
            and protected_temp < content_write.start(),
            f"{label} operator must protect temporary JSON and stderr before content is written",
        )
        require(
            "Get-Command 'aws.exe' -CommandType Application" in operator
            and "Get-Command 'terraform.exe' -CommandType Application" in operator
            and "Get-Command 'python.exe' -CommandType Application" in operator
            and "$script:awsExecutable" in operator
            and "$script:terraformExecutable" in operator
            and "$script:pythonExecutable" in operator
            and "[REDACTED_S3_LOCATION]" in operator
            and "[REDACTED_VALUE]" in operator
            and "[REDACTED_IP]" in operator
            and "[REDACTED_IPV6]" in operator,
            f"{label} operator must bind CLI calls to absolute application paths",
        )
        forbid(
            re.search(
                r"(?mi)^\s*(?:&\s*)?(?:aws|terraform|python)(?:\.exe)?\b",
                operator,
            )
            is not None,
            f"{label} operator contains a bare shadowable CLI invocation",
        )
        require(
            "JCareer-ProtectedInputSnapshot.psm1" in operator
            and "New-JCareerProtectedSnapshotSet" in operator
            and "Add-JCareerProtectedSnapshotFile" in operator
            and "Remove-JCareerProtectedSnapshotSet" in operator
            and "-E -s -S -B" in operator,
            f"{label} operator must use immutable protected inputs and isolated Python",
        )
        require(
            "-lockfile=readonly" in operator,
            f"{label} operator must not rewrite the reviewed provider lock file",
        )
    require(
        snapshot_module.count("[IO.FileShare]::Read") >= 3
        and "[IO.FileShare]::ReadWrite" not in snapshot_module
        and "$sourcePreHash" in snapshot_module
        and "$sourcePostHash" in snapshot_module
        and "$snapshotLockedHash" in snapshot_module
        and "Protected snapshot source changed during capture" in snapshot_module
        and "Protected snapshot destination contains an invalid path segment" in snapshot_module
        and "[IO.Directory]::CreateDirectory($destinationDirectory)" in snapshot_module,
        "protected input module must lock byte-exact flat and nested snapshots",
    )
    require(
        "$script:activeSnapshotSets" in snapshot_module
        and "Test-JCareerSnapshotSetMatchesActiveRecord" in snapshot_module
        and "Test-JCareerDirectSnapshotPath" in snapshot_module
        and "Test-JCareerProtectedSnapshotDirectoryAcl" in snapshot_module
        and "Test-JCareerSnapshotTreeHasNoReparsePoints" in snapshot_module
        and "JCAREER_STALE_SNAPSHOT_RECOVERY_APPROVED" in snapshot_module
        and "lease remains held for retry" in snapshot_module,
        "protected input cleanup must bind active objects and require explicit safe stale recovery",
    )
    for relative_source in (
        "fleet/images/endpoint_image_contract.yaml",
        "fleet/images/windows/build-component.yaml",
        "fleet/images/windows/test-component.yaml",
        "fleet/images/windows/Configure-JCareerSession.ps1",
        "fleet/images/windows/Remove-JCareerSession.ps1",
    ):
        require(
            relative_source in build_operator,
            f"image-build protected source bundle omitted {relative_source}",
        )
    require(
        "check_windows_image_operation_approval.py" in build_operator
        and "check_windows_image_receipt.py" in build_operator
        and "--root $protectedSourceRoot" in build_operator
        and "$script:inputSnapshotSet.Count -ne 11" in build_operator
        and "$definitionReceiptDocument.protected_input_snapshot_count -ne 7" in build_operator
        and "$definitionReceiptDocument.local_snapshot_cleanup_observed -ne $true" in build_operator,
        "image build must bind approval, definition receipt, checker imports, and source bundle snapshots",
    )
    require(
        "check_windows_image_operation_approval.py" in cleanup_operator
        and "check_windows_image_receipt.py" in cleanup_operator
        and "if ($resolvedEndpointReceipt) { 10 } else { 9 }" in cleanup_operator,
        "image cleanup must bind its complete optional input set to protected snapshots",
    )
    require(
        build_operator.count("-lockfile=readonly") == 1
        and cleanup_operator.count("-lockfile=readonly") == 2
        and disposition_operator.count("-lockfile=readonly") == 1
        and recovery_operator.count("-lockfile=readonly") == 2,
        "every image and endpoint Terraform initialization must use the reviewed lock file read-only",
    )
    require(
        "if ($snapshotTeardown) { 5 } else { 4 }" in disposition_operator
        and "$teardown.protected_input_snapshot_count -ne 10" in disposition_operator
        and "$teardown.local_snapshot_cleanup_observed -ne $true" in disposition_operator,
        "endpoint disposition must protect its inputs and reject incomplete teardown receipts",
    )
    require(
        "check_windows_image_operation_approval.py" in recovery_operator
        and "check_windows_image_receipt.py" in recovery_operator
        and "if ($snapshotEndpointTeardown) { 10 } else { 9 }" in recovery_operator,
        "deleted-state recovery must bind its complete optional input set to protected snapshots",
    )
    require(
        cleanup_operator.find("$preMutationImage = Invoke-AwsJson")
        < cleanup_operator.find('Name=image-id,Values=$([string]$artifact.ami_id)')
        < cleanup_operator.find("'imagebuilder', 'start-resource-state-update'"),
        "image cleanup must make scoped active-instance inspection its last AWS read before mutation",
    )
    require(
        "function Test-AnyRecoveryRecord" in cleanup_operator
        and "image-deleted-recovery" in cleanup_operator
        and "[IO.Directory]::EnumerateFiles(" in cleanup_operator
        and cleanup_operator.count("Test-AnyRecoveryRecord") >= 3,
        "normal cleanup must reject current or legacy recovery records",
    )
    for label, operator in {
        "normal cleanup": cleanup_operator,
        "deleted-state recovery": recovery_operator,
    }.items():
        require(
            "Global\\JCareerImageArtifactOperation-" in operator
            and "--print-canonical-sha256" in operator
            and "[Threading.Mutex]::new(" in operator
            and ".WaitOne(0)" in operator
            and ".ReleaseMutex()" in operator
            and "[Threading.AbandonedMutexException]" in operator
            and "Another local image cleanup or recovery operation" in operator,
            f"{label} must hold the common canonical-backend global host mutex",
        )
    residual_snapshot_block = cleanup_operator[
        cleanup_operator.find("$residualSnapshotCount = 0"):
        cleanup_operator.find("if ($residualAmiCount -ne 0")
    ]
    require(
        "$snapshotDocument = Invoke-AwsJson" in residual_snapshot_block
        and "InvalidAMIID\\.NotFound" in cleanup_operator
        and "InvalidSnapshot\\.NotFound" in cleanup_operator
        and "2>&1" not in residual_snapshot_block,
        "post-delete snapshot observation must keep AWS stderr out of JSON stdout",
    )
    require(
        "JCAREER_WINDOWS_IMAGE_DELETED_RECOVERY_OBSERVATION_APPROVED" in recovery_operator
        and "check_windows_image_operation_approval.py" in recovery_operator
        and "'recovery'" in recovery_operator
        and recovery_operator.count("Get-RecoverySnapshot -BuildArn") == 2
        and recovery_operator.count("Get-EndpointStateCount") >= 3
        and "READ_ONLY_POST_DELETION_RECOVERY" in recovery_operator
        and "READ_ONLY_DELETED_STATE_AND_SCOPED_RESIDUAL_ZERO_RECORDED" in recovery_operator
        and "lifecycle_execution_success_asserted = $false" in recovery_operator
        and "cleanup_operation_success_asserted = $false" in recovery_operator
        and "terraform_resource_mutation_attempted = $false" in recovery_operator
        and "terraform_initialization_performed = $true" in recovery_operator
        and "endpoint_terraform_state_read_performed = $true" in recovery_operator
        and "OBSERVATION_ONLY_NOT_COMPLETION" in recovery_operator
        and "completion_receipt_required = $true" in recovery_operator
        and "COMPLETE_READ_ONLY_RECOVERY_RECORD" in recovery_operator
        and "aws_or_terraform_resource_mutation_performed = $false" in recovery_operator
        and "local_evidence_records_written = $true" in recovery_operator
        and "outside the approval window or in the future" in recovery_operator
        and "out of order, outside approval, or in the future" in recovery_operator
        and "exists without its bound observation" in recovery_operator
        and "$recoveryRunDirectory = Join-Path $recoveryRecordRoot $approvalHash" in recovery_operator
        and "Join-Path $recoveryRunDirectory 'observation.json'" in recovery_operator
        and "Join-Path $recoveryRunDirectory 'receipt.json'" in recovery_operator
        and "legacy fixed-path recovery record requires human disposition" in recovery_operator
        and "whole_account_zero_claimed = $false" in recovery_operator
        and "New-ProtectedEmptyFile -Path $temporaryPath" in recovery_operator
        and "New-ProtectedEmptyFile -Path $stderrPath" in recovery_operator,
        "read-only deleted-state recovery observation contract is incomplete",
    )
    recovery_folded = recovery_operator.casefold()
    for forbidden in (
        "start-resource-state-update",
        "deregister-image",
        "delete-image",
        "delete-snapshot",
        "terraform apply",
        "terraform destroy",
        "& aws ",
    ):
        forbid(
            forbidden in recovery_folded,
            f"deleted-state recovery operator contains a prohibited mutation or shadowable call: {forbidden}",
        )

    folded = (all_tf + sources["windows_build"] + sources["windows_session"]).casefold()
    forbidden = {
        "aws_ec2_host": "EC2 Mac Dedicated Hosts are forbidden in the current lab",
        "mac1.metal": "Mac instance types are forbidden in the current lab",
        "mac2.metal": "Mac instance types are forbidden in the current lab",
        'resource "aws_instance"': "consultant endpoint instances are a separate approved deployment",
        "aws_workspaces_": "WorkSpaces is not approved for this image definition",
        "password =": "passwords must not be baked into the image",
        "api_key =": "API keys must not be baked into the image",
        "preview_token": "preview tokens must not be baked into the image",
    }
    for term, message in forbidden.items():
        forbid(term in folded, message)
    return errors


def _walk(module: dict[str, object]) -> Iterable[dict[str, object]]:
    for resource in module.get("resources", []) or []:
        if isinstance(resource, dict):
            yield resource
    for child in module.get("child_modules", []) or []:
        if isinstance(child, dict):
            yield from _walk(child)


def _stage(plan: dict[str, object]) -> str | None:
    outputs = ((plan.get("planned_values") or {}).get("outputs") or {})
    row = outputs.get("deployment_stage") if isinstance(outputs, dict) else None
    return str(row.get("value")) if isinstance(row, dict) and isinstance(row.get("value"), str) else None


def audit_plan_document(plan: dict[str, object]) -> list[str]:
    errors: list[str] = []
    module = ((plan.get("planned_values") or {}).get("root_module") or {})
    resources = list(_walk(module)) if isinstance(module, dict) else []
    addresses = {str(row.get("address")) for row in resources if isinstance(row.get("address"), str)}
    stage = _stage(plan)
    expected = EXPECTED_PLAN_ADDRESSES.get(stage or "")
    if expected is None:
        errors.append("workplace image plan lacks a recognized deployment_stage")
    elif addresses != expected:
        errors.append(f"workplace image {stage} plan address mismatch: expected={len(expected)} observed={len(addresses)}")
    for row in resources:
        if row.get("type") not in EXPECTED_RESOURCES:
            errors.append(f"unapproved workplace image resource type: {row.get('type')}")
    for change in plan.get("resource_changes", []) or []:
        actions = ((change.get("change") or {}).get("actions") or []) if isinstance(change, dict) else []
        if "delete" in actions:
            errors.append("workplace image saved plan contains delete or replacement")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--plan")
    args = parser.parse_args()
    try:
        sources = load_sources(Path(args.root).resolve())
        errors = audit_sources(sources)
        if args.plan:
            errors.extend(audit_plan_document(json.loads(Path(args.plan).read_text(encoding="utf-8"))))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"::error::{type(exc).__name__}: {exc}")
        return 1
    print("workplace image source inventory: definition_resources=12 macos_resources=0 AWS_not_accessed")
    for error in errors:
        print(f"::error::{error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
