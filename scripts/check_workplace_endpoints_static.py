#!/usr/bin/env python3
"""Validate the default-off three-Windows endpoint deployment source."""

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
        "aws_security_group": 1,
        "aws_vpc_security_group_egress_rule": 1,
        "aws_iam_role": 1,
        "aws_iam_role_policy_attachment": 1,
        "aws_iam_instance_profile": 1,
        "aws_instance": 1,
        "aws_budgets_budget": 1,
    }
)
WINDOWS_THREE_ADDRESSES = frozenset(
    {
        "aws_budgets_budget.endpoints[0]",
        "aws_iam_instance_profile.endpoint[0]",
        "aws_iam_role.endpoint[0]",
        "aws_iam_role_policy_attachment.ssm[0]",
        "aws_instance.windows[0]",
        "aws_instance.windows[1]",
        "aws_instance.windows[2]",
        "aws_security_group.endpoints[0]",
        "aws_vpc_security_group_egress_rule.https_and_ssm[0]",
    }
)
EXPECTED_PLAN_ADDRESSES = {
    "disabled": frozenset(),
    "windows_three": WINDOWS_THREE_ADDRESSES,
}


def load_sources(root: Path) -> dict[str, str]:
    module = root / "terraform/workplace-endpoints"
    missing = [name for name in SOURCE_FILES if not (module / name).is_file()]
    supporting = {
        "approval": module / "approval.example.json",
        "image_receipt": module / "image-receipt.example.json",
        "session_approval": module / "session-approval.example.json",
        "session": root / "fleet/images/windows/Configure-JCareerSession.ps1",
        "session_cleanup": root / "fleet/images/windows/Remove-JCareerSession.ps1",
        "session_operator": root / "scripts/Invoke-ApprovedWindowsEndpointSession.ps1",
        "session_checker": root / "scripts/check_windows_endpoint_session_approval.py",
        "contract": root / "fleet/images/endpoint_image_contract.yaml",
    }
    missing.extend(str(path.relative_to(root)) for path in supporting.values() if not path.is_file())
    if missing:
        raise FileNotFoundError("missing workplace endpoint source: " + ", ".join(missing))
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
    approval = json.loads(sources["approval"])
    image_receipt = json.loads(sources["image_receipt"])
    session_approval = json.loads(sources["session_approval"])
    observed = Counter(re.findall(r'resource\s+"([^"]+)"\s+"', all_tf))

    require(set(sources["terraform_file_names"].splitlines()) == set(SOURCE_FILES), "endpoint root top-level .tf inventory drifted")
    require(observed == EXPECTED_RESOURCES, "endpoint resource block inventory drifted")
    require(not re.findall(r'data\s+"([^"]+)"\s+"', all_tf), "endpoint root must not use data sources")
    require('default     = "disabled"' in variables, "endpoint root must default to disabled")
    require('backend "s3"' in sources["versions"] and "use_lockfile = true" in sources["versions"], "encrypted locking remote state backend is missing")
    require('var.activation_acknowledgement == "JCAREER_THREE_WINDOWS_ENDPOINTS_APPROVED"' in main, "endpoint human acknowledgement is missing")
    require('can(regex("^APPROVAL-[A-Z0-9_-]{8,64}$", var.approval_ref))' in main and 'can(regex("^IMAGE-[A-Z0-9_-]{8,64}$", var.image_build_ref))' in main, "plan and image receipt bindings are missing")
    require('count = local.enabled ? 3 : 0' in main and 'endpoint_refs = ["WIN-01", "WIN-02", "WIN-03"]' in main, "exact three-Windows inventory is missing")
    require('instance_type               = "t3.small"' in main, "endpoint instance type must remain t3.small")
    require("associate_public_ip_address = true" in main and "no inbound" in main.lower(), "SSM egress and no-inbound boundary is unclear")
    require("from_port         = 443" in main and "to_port           = 443" in main and 'cidr_ipv4         = "0.0.0.0/0"' in main, "endpoint egress must remain HTTPS-only")
    require("http_tokens                 = \"required\"" in main and "http_protocol_ipv6          = \"disabled\"" in main, "IMDSv2/IPv6 metadata boundary is missing")
    require("encrypted             = true" in main and 'volume_type           = "gp3"' in main, "encrypted gp3 endpoint roots are required")
    require("JCareerLabAutoStop" in main and "var.auto_stop_minutes <= 240" in variables, "bounded automatic shutdown is missing")
    require("<persist>true</persist>" in main, "automatic stop must be renewed on every Windows boot")
    require('policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"' in main, "SSM-only managed policy is missing")
    require("inbound_rules              = 0" in outputs and 'access                     = "SSM_TUNNELED_RDP_OR_FLEET_MANAGER"' in outputs, "no-inbound SSM access output is missing")
    require(
        re.search(
            r'output\s+"endpoint_security_group_id"\s*\{[^}]*sensitive\s*=\s*true',
            outputs,
            re.DOTALL,
        )
        is not None,
        "runtime SG verification requires a sensitive Terraform security-group output",
    )
    require("deployed_macos_count       = 0" in outputs, "macOS zero-resource boundary is missing")
    require(approval.get("decision") == "PENDING_HUMAN_DECISION" and not approval.get("approval_ref"), "endpoint approval example must remain pending")
    require(image_receipt.get("decision") == "PENDING_HUMAN_IMAGE_REVIEW" and not image_receipt.get("ami_id"), "endpoint image receipt example must remain pending")
    require(session_approval.get("decision") == "PENDING_HUMAN_DECISION" and not session_approval.get("sessions"), "endpoint session approval example must remain pending")
    require(
        session_approval.get("preview_bootstrap_token_sha256") == ""
        and session_approval.get("bootstrap_delivery_method") == "RDP_CLIPBOARD_ONE_TIME",
        "pending session approval must bind only a future bootstrap digest and one-time clipboard delivery",
    )
    require(
        "ValidatePattern('^https://" in sources["session"]
        and "$parsedPreview.Query" in sources["session"]
        and "$parsedPreview.Fragment" in sources["session"]
        and "ApprovedPreviewUrlSha256" in sources["session"]
        and "credentials_recorded = $false" in sources["session"]
        and "Microsoft Corporation" in sources["session"]
        and "J-Career approved preview.lnk" in sources["session"]
        and "CreateShortcut" in sources["session"]
        and "New-ScheduledTaskSettingsSet -StartWhenAvailable" in sources["session"]
        and "JCAREER_SESSION_REMOVED=PASS" in sources["session_cleanup"]
        and "Get-CimInstance Win32_Process" in sources["session_cleanup"]
        and "EdgeProfiles" in sources["session_cleanup"]
        and "shutdown.exe" in sources["session_cleanup"],
        "session setup must remain hash-bound, expiring, credential-free, and HTTPS-only",
    )
    operator = sources["session_operator"]
    remote_start = operator.find("$remoteCommands = @(")
    remote_end = operator.find("$remoteOutput =", remote_start)
    remote_block = operator[remote_start:remote_end] if remote_start >= 0 and remote_end > remote_start else operator
    snapshot_tail_start = operator.find("$backendSource = $null")
    snapshot_tail = operator[snapshot_tail_start:] if snapshot_tail_start >= 0 else operator
    require(
        "check_windows_endpoint_session_approval.py" in operator
        and "[Security.SecureString]$PreviewBootstrapToken" in operator
        and "--preview-bootstrap-token-sha256" in operator
        and "Set-OneTimePreviewBootstrapClipboard" in operator
        and "Clear-PreviewBootstrapClipboard" in operator
        and "BOOTSTRAP_PASTED" in operator
        and "CLOSE_AND_CLEANUP" in operator
        and "Stop-EndpointTunnels" in operator
        and "Invoke-ConfiguredEndpointCleanup" in operator
        and "AWS-StartPortForwardingSession" in operator
        and "portNumber=3389,localPortNumber=" in operator
        and "Get-HistoricalSsmSessions" in operator
        and "Get-SsmSessionHistoryById" in operator
        and "[string]$terminated.SessionId -ne $sessionId" in operator
        and "[string]$_.Status -eq 'Terminated'" in operator
        and "$null -ne $_.EndDate" in operator
        and "NetTCPIP\\Get-NetTCPConnection -State Listen -ErrorAction Stop" in operator
        and "Test-ProcessIdentityActive" in operator
        and "StartTimeUtcTicks" in operator
        and "BindingDeadline" in operator
        and "Get-ProcessDescendantIdentities" in operator
        and "ChildProcesses" in operator
        and "CreationDate" in operator
        and "ParentStartTimeUtcTicks" in operator
        and "CimCreationTimeUtcTicks" in operator
        and 'CimCmdlets\\Get-CimInstance Win32_Process -Filter "ProcessId = $childId"' in operator
        and "[TimeSpan]::FromMilliseconds(100).Ticks" in operator
        and "Stop-ExactProcessIdentity" in operator
        and "Stop-RecordedRootProcess" in operator
        and "$process.SafeHandle" in operator
        and "ProcessObject = $process" in operator
        and "Update-TrackedProcessDescendants" in operator
        and "DescendantTrackingEstablished" in operator
        and "Global\\JCareerConsultantSession-" in operator
        and "--print-canonical-sha256" in operator
        and "$script:approvalLeaseMutex = [Threading.Mutex]::new(" in operator
        and ".WaitOne(0)" in operator
        and ".ReleaseMutex()" in operator
        and "[Threading.AbandonedMutexException]" in operator
        and "Another local consultant-session operator holds the shared endpoint-backend lease" in operator
        and "LaunchReason" in operator
        and "$priorApprovalSessions" in operator
        and "$result = @(& $script:awsExecutable @Arguments" in operator
        and "Microsoft.PowerShell.Core\\Get-Command 'aws.exe' -CommandType Application" in operator
        and "Microsoft.PowerShell.Core\\Get-Command 'terraform.exe' -CommandType Application" in operator
        and "Microsoft.PowerShell.Core\\Get-Command 'python.exe' -CommandType Application" in operator
        and "Microsoft.PowerShell.Management\\Start-Process -FilePath $awsExecutable" in operator
        and "Microsoft.PowerShell.Management\\Start-Process -FilePath $script:mstscExecutable" in operator
        and "Microsoft.PowerShell.Management\\Get-Process" in operator
        and "Microsoft.PowerShell.Management\\Set-Clipboard" in operator
        and "[REDACTED_SESSION_ID]" in operator
        and "[REDACTED_UUID]" in operator
        and "[REDACTED_IP]" in operator
        and "[REDACTED_IPV6]" in operator
        and "[REDACTED_S3_LOCATION]" in operator
        and "[REDACTED_VALUE]" in operator
        and "$trustedPowerShellCommands" in operator
        and "A required PowerShell command is shadowed" in operator
        and "try {\n    New-Item -ItemType Directory -Path $taskTemporary" in operator
        and "'^aws-cli/2\\.'" in operator
        and "ConvertTo-SsmTimestampUtc" in operator
        and "Get-LocalPortListeners" in operator
        and "@('127.0.0.1', '::1')" in operator
        and "$lateCandidates = @(Get-RecordSsmSessions -Record $record -IncludeHistory)" in operator
        and "$script:tunnelRecords = @($remainingRecords)" in operator
        and "tunnel_closure_observations" in operator
        and "jcareer-windows-consultant-session-failure-observation-v1" in operator
        and "cleanup_retry_required" in operator
        and "operation_state = 'OPERATION_FAILED'" in operator
        and "cleanup_state = if (" in operator
        and "'NO_CLEANUP_REQUIRED'" in operator
        and "configuration_attempted_endpoint_count" in operator
        and "configuration_receipts_observed" in operator
        and "$script:tunnelCleanupObservations" in operator
        and "$listenersWithoutExactPluginIdentity" in operator
        and "Remove-TaskTemporaryDirectory" in operator
        and "New-ProtectedEmptyFile -Path $temporaryPath" in operator
        and "SetAccessRuleProtection($true, $false)" in operator
        and "microsoft_edge_signature_observed = $true" in operator
        and "gui_login_observed = $false" in operator
        and "raw_identifiers_included = $false" in operator
        and "APPROVED_FOR_THREE_WINDOWS_CONSULTANT_SESSIONS" in sources["session_checker"],
        "approved three-endpoint consultant session orchestration is incomplete",
    )
    require(
        operator.count("Copy-ProtectedStableFile -Source ") == 9
        and "protected-inputs" in operator
        and "[IO.FileShare]::Read" in operator
        and "$sourcePreHash" in operator
        and "$snapshotHash" in operator
        and "$sourcePostHash" in operator
        and "$snapshotLockedHash" in operator
        and "[IO.FileAccess]::Read, [IO.FileShare]::Read" in operator
        and operator.find("(New-CurrentUserFileAcl)")
        < operator.find("$sourceStream.CopyTo($destinationStream)")
        and "& $script:pythonExecutable $backendChecker" in operator
        and "& $script:pythonExecutable $approvalChecker" in operator
        and '"-backend-config=$resolvedBackend"' in operator
        and snapshot_tail_start >= 0
        and all(
            snapshot_tail.count(name) == 1
            for name in (
                "$backendSource",
                "$approvalSource",
                "$endpointReceiptSource",
                "$imageReceiptSource",
                "$buildObservationSource",
                "$configureScriptSource",
                "$removeScriptSource",
                "$backendCheckerSource",
                "$approvalCheckerSource",
            )
        )
        and "@($approval.sessions).Count -ne 3" in operator
        and "Assert-SessionApprovalActive -Approval $approval" in operator
        and "$script:protectedSnapshotCount -ne 9" in operator
        and "protected_input_snapshot_count = $script:protectedSnapshotCount" in operator
        and "local_snapshot_cleanup_observed" in operator
        and "local_snapshot_cleanup_retry_required" in operator
        and "local_task_temporary_cleanup_observed" in operator
        and "local_task_temporary_cleanup_retry_required" in operator,
        "endpoint runtime inputs are not held as one protected immutable snapshot set",
    )
    forbid(
        "'{\"portNumber\"" in operator
        or "Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue" in operator
        or "taskkill.exe" in operator
        or "/T /F" in operator
        or "$script:approvalLeaseStream" in operator
        or "$result = @(& aws @Arguments" in operator
        or re.search(r"(?mi)^\s*(?:Start-Process|Get-Process|Get-CimInstance|Get-NetTCPConnection|Set-Clipboard)\b", operator) is not None,
        "interactive tunnel arguments and port-close observations must remain fail-closed",
    )
    require(
        "endpoint_security_group_id" in operator
        and "describe-security-groups" in operator
        and "IpPermissions" in operator
        and "attachedSecurityGroups.Count -ne 1" in operator
        and "security_group_exact_match_observed = $true" in operator,
        "live zero-ingress and exact one-security-group verification is incomplete",
    )
    require(
        remote_start >= 0
        and remote_end > remote_start
        and "PreviewBootstrapToken" not in remote_block
        and "jcareer_preview=" not in remote_block,
        "preview bootstrap token must never enter the SSM remote-command payload",
    )

    folded = all_tf.casefold()
    for term, message in {
        "aws_vpc_security_group_ingress_rule": "endpoint public ingress is forbidden",
        "from_port         = 3389": "direct RDP ingress is forbidden",
        "aws_ec2_host": "EC2 Mac hosts are forbidden",
        "mac1.metal": "Mac instance types are forbidden",
        "mac2.metal": "Mac instance types are forbidden",
        "t3.medium": "endpoint instance size exceeds the current allowlist",
        "user_data = base64encode(\"password": "credentials must not enter user data",
    }.items():
        forbid(term in folded, message)
    return errors


def _walk(module: dict[str, object]) -> Iterable[dict[str, object]]:
    for row in module.get("resources", []) or []:
        if isinstance(row, dict):
            yield row
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
        errors.append("endpoint plan lacks a recognized deployment_stage")
    elif addresses != expected:
        errors.append(f"endpoint {stage} plan address mismatch: expected={len(expected)} observed={len(addresses)}")
    for row in resources:
        if row.get("type") not in EXPECTED_RESOURCES:
            errors.append(f"unapproved endpoint resource type: {row.get('type')}")
    for change in plan.get("resource_changes", []) or []:
        actions = ((change.get("change") or {}).get("actions") or []) if isinstance(change, dict) else []
        if "delete" in actions:
            errors.append("endpoint saved plan contains delete or replacement")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--plan")
    args = parser.parse_args()
    try:
        errors = audit_sources(load_sources(Path(args.root).resolve()))
        if args.plan:
            errors.extend(
                audit_plan_document(
                    json.loads(Path(args.plan).read_text(encoding="utf-8-sig"))
                )
            )
    except (OSError, json.JSONDecodeError) as exc:
        print(f"::error::{type(exc).__name__}: {exc}")
        return 1
    print("workplace endpoints source inventory: disabled=0 windows_three=9 macos=0 AWS_not_accessed")
    for error in errors:
        print(f"::error::{error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
