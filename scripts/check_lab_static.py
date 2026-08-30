#!/usr/bin/env python3
"""AWS 호출 없이 terraform/lab의 소스 수준 실행 경계를 검사한다.

이 검사는 HCL validate/plan, 실제 AWS 구성, 비용 또는 통제 판정을 대신하지 않는다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path


SOURCE_PATHS = {
    "main": Path("terraform/lab/main.tf"),
    "variables": Path("terraform/lab/variables.tf"),
    "outputs": Path("terraform/lab/outputs.tf"),
    "user_data": Path("terraform/lab/user_data.sh.tftpl"),
    "deploy": Path("terraform/lab/provisioning/deploy-runtime.ps1"),
    "deploy_lab": Path("terraform/lab/provisioning/deploy-lab.ps1"),
    "lab_compose": Path("terraform/lab/provisioning/lab.compose.override.yaml"),
    "nginx": Path("terraform/lab/provisioning/nginx.lab.conf"),
    "compose": Path("src/runtime/compose.yaml"),
    "readme": Path("terraform/lab/README.md"),
}


def load_sources(root: Path) -> dict[str, str]:
    sources: dict[str, str] = {}
    missing: list[str] = []
    for key, relative in SOURCE_PATHS.items():
        path = root / relative
        if not path.is_file():
            missing.append(relative.as_posix())
            continue
        sources[key] = path.read_text(encoding="utf-8")
    if missing:
        raise FileNotFoundError("missing lab source: " + ", ".join(missing))
    terraform_paths = sorted((root / "terraform" / "lab").glob("*.tf"))
    sources["terraform_file_names"] = "\n".join(path.name for path in terraform_paths)
    sources["terraform_all"] = "\n".join(
        f"# file: {path.name}\n{path.read_text(encoding='utf-8')}"
        for path in terraform_paths
    )
    return sources


def audit_sources(sources: dict[str, str]) -> list[str]:
    errors: list[str] = []
    main = sources["main"]
    terraform_all = sources["terraform_all"]
    variables = sources["variables"]
    outputs = sources["outputs"]
    user_data = sources["user_data"]
    deploy = sources["deploy"]
    deploy_lab = sources["deploy_lab"]
    lab_compose = sources["lab_compose"]
    nginx = sources["nginx"]
    compose = sources["compose"]
    readme = sources["readme"]

    def require(observed: bool, message: str) -> None:
        if not observed:
            errors.append(message)

    def forbid(observed: bool, message: str) -> None:
        if observed:
            errors.append(message)

    require(
        set(sources["terraform_file_names"].splitlines())
        == {"main.tf", "outputs.tf", "variables.tf", "versions.tf"},
        "terraform/lab contains an unexpected or missing top-level .tf file",
    )
    require(
        len(re.findall(r'resource\s+"aws_instance"\s+"', terraform_all)) == 1,
        "aws_instance resource must appear exactly once",
    )
    expected_resource_blocks = Counter(
        {
            "aws_vpc": 1,
            "aws_subnet": 1,
            "aws_internet_gateway": 1,
            "aws_route_table": 1,
            "aws_route": 1,
            "aws_route_table_association": 1,
            "aws_security_group": 1,
            "aws_vpc_security_group_egress_rule": 1,
            "aws_iam_role": 1,
            "aws_iam_role_policy_attachment": 1,
            "aws_iam_role_policy": 1,
            "aws_iam_instance_profile": 1,
            "aws_instance": 1,
            "aws_budgets_budget": 1,
        }
    )
    observed_resource_blocks = Counter(
        re.findall(r'resource\s+"([^"]+)"\s+"', terraform_all)
    )
    require(
        observed_resource_blocks == expected_resource_blocks,
        "terraform/lab resource blocks differ from the reviewed exact source inventory",
    )
    require(
        Counter(re.findall(r'data\s+"([^"]+)"\s+"', terraform_all))
        == Counter({"aws_ssm_parameter": 1, "aws_iam_policy_document": 2}),
        "terraform/lab data sources differ from the reviewed exact source inventory",
    )
    require(
        'var.instance_type == "t3.small"' in variables,
        "six-container lab must remain restricted to t3.small",
    )
    require('default     = "t3.small"' in variables, "default instance must remain t3.small")
    require(
        "var.root_volume_gib >= 20 && var.root_volume_gib <= 30" in variables,
        "root volume range must remain 20-30 GiB",
    )
    require(
        "var.auto_stop_minutes >= 60 && var.auto_stop_minutes <= 480" in variables,
        "auto-stop range must remain 60-480 minutes",
    )

    require('default     = "disabled"' in variables, "lab activation must default to disabled")
    require(
        'var.activation_acknowledgement == "JCAREER_SYNTHETIC_LAB_APPROVED"' in main,
        "Terraform activation precondition is missing",
    )
    require(
        re.search(r'variable\s+"enable_bedrock_live"[\s\S]*?default\s*=\s*false', variables)
        is not None,
        "Bedrock plan flag must default to false",
    )
    require(
        "count = var.enable_bedrock_live ? 1 : 0" in main,
        "Bedrock IAM policy must be conditional",
    )
    require(
        'policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"' in main,
        "reviewed AmazonSSMManagedInstanceCore attachment is missing",
    )
    require(
        "condition     = var.enable_bedrock_live == false" in variables
        and "condition     = var.enable_bedrock_live == false" in main,
        "Bedrock live must remain blocked pending a container credential boundary",
    )

    forbid(
        'resource "aws_vpc_security_group_ingress_rule"' in terraform_all,
        "public/VPC ingress rule is present",
    )
    forbid(re.search(r"\bingress\s*\{", terraform_all) is not None, "inline security-group ingress is present")
    forbid(re.search(r"\b(from_port|to_port)\s*=\s*22\b", terraform_all) is not None, "SSH port is present")
    forbid(re.search(r"\bkey_name\s*=", terraform_all) is not None, "EC2 key pair attachment is present")
    for forbidden_type in ("aws_key_pair", "tls_private_key", "local_file", "null_resource"):
        forbid(
            re.search(rf'resource\s+"{forbidden_type}"\s+"', terraform_all) is not None,
            f"forbidden lab resource type is present: {forbidden_type}",
        )

    require('http_tokens                 = "required"' in main, "IMDSv2 token requirement is missing")
    require("http_put_response_hop_limit = 1" in main, "IMDS hop limit must remain 1")
    require('http_protocol_ipv6          = "disabled"' in main, "IMDS IPv6 endpoint must remain disabled")
    require('instance_metadata_tags      = "disabled"' in main, "instance metadata tags must remain disabled")
    require("delete_on_termination = true" in main, "root volume deletion flag is missing")
    require("encrypted             = true" in main, "root volume encryption flag is missing")
    require('volume_type           = "gp3"' in main, "root volume must remain gp3")
    require("iops                  = 3000" in main, "root volume IOPS must remain 3000")
    require('cpu_credits = "standard"' in main, "T3 CPU credits must remain standard")
    require("monitoring                  = false" in main, "detailed monitoring must remain disabled")

    require(
        "jcareer-lab-auto-stop.timer" in user_data and "ExecStart=/sbin/shutdown -h now" in user_data,
        "OS auto-stop timer is missing",
    )
    trap_index = user_data.find("trap fail_safe_stop ERR")
    first_unit_write_index = user_data.find(
        "cat >/etc/systemd/system/jcareer-lab-auto-stop.service"
    )
    timer_enable_index = user_data.find(
        "systemctl enable --now jcareer-lab-auto-stop.timer"
    )
    package_install_index = user_data.find("dnf install -y")
    require(
        0 <= trap_index < first_unit_write_index < timer_enable_index < package_install_index,
        "bootstrap failure trap must be armed before timer installation and package/network operations",
    )
    require(
        0 <= timer_enable_index < package_install_index,
        "auto-stop must be installed before package or network operations",
    )
    require(
        "trap fail_safe_stop ERR" in user_data
        and "systemctl start --no-block jcareer-lab-auto-stop.service || /sbin/shutdown -h now"
        in user_data,
        "bootstrap failure must request an immediate stop",
    )
    readiness_index = user_data.find("touch /var/lib/jcareer-lab/bootstrap-ready")
    trap_clear_index = user_data.rfind("trap - ERR")
    require(
        0 <= readiness_index < trap_clear_index,
        "bootstrap failure trap must remain armed until the readiness marker is written",
    )
    require("compose_sha256=" in user_data and "sha256sum --check --strict" in user_data, "Compose binary checksum verification is missing")
    require(
        'buildx_version="v0.36.1"' in user_data
        and 'buildx_sha256="48af8a397ebd60178778bf63611dbcebe5f5e7a9be90eb9147b24b9587455778"'
        in user_data
        and "github.com/docker/buildx/releases/download" in user_data
        and 'docker buildx version | grep -F "$${buildx_version#v}"' in user_data,
        "bootstrap must install the checksum-pinned Docker Buildx plugin",
    )

    for tag in ("Project", "jk_layer", "jk_purpose"):
        require(f"{tag}" in deploy, f"deployment target validation is missing tag {tag}")
    require("Get-ValidatedLabInstance" in deploy, "deployment target preflight is missing")
    require(
        "function Protect-Diagnostic" in deploy
        and "[REDACTED_ACCOUNT]" in deploy
        and "[REDACTED_ARN]" in deploy
        and "[REDACTED_RESOURCE_ID]" in deploy
        and "$diagnostic = Protect-Diagnostic" in deploy
        and "$stopDiagnostic = Protect-Diagnostic" in deploy,
        "deployment diagnostics must redact AWS account and resource identifiers",
    )
    require("InstanceType -ne 't3.small'" in deploy, "deployment must reject unverified instance sizes")
    require("IamInstanceProfile.Arn" in deploy, "deployment instance-profile check is missing")
    require(
        "$profileName -ne $instanceName" in deploy
        and "instance profile does not match the reviewed runtime Name tag" in deploy,
        "deployment must bind the target instance to its reviewed runtime profile name",
    )
    require(
        "JCAREER_SYNTHETIC_BEDROCK_APPROVED" in deploy,
        "separate Bedrock acknowledgement is missing",
    )
    require(
        "Bedrock live is blocked until a container-scoped credential boundary" in deploy,
        "deployment must fail closed on the unresolved Bedrock credential boundary",
    )
    require(
        "$provider = if ($EnableBedrockLive) { 'bedrock' } else { 'local-synthetic-stub' }" in deploy,
        "deployment provider must default to the local stub",
    )
    require("WEB_BIND_ADDRESS=127.0.0.1" in deploy, "remote web binding must remain loopback")
    forbid("WEB_BIND_ADDRESS=0.0.0.0" in deploy, "remote web binding exposes all interfaces")
    require("Get-FileHash" in deploy and "sha256sum --check --strict" in deploy, "runtime archive integrity check is missing")
    require(
        "$script:validatedTarget" in deploy and "'ec2', 'stop-instances'" in deploy,
        "deployment failure must stop only a preflight-validated target",
    )
    require(
        "python3 tests/database_boundary.py" in deploy
        and "J-Career member/company database boundary: PASS" in deploy,
        "remote member/company database boundary verification is missing",
    )
    require(
        "memory_kib" in deploy and "disk_kib" in deploy and "jcareer-lab.swap" in deploy,
        "remote host capacity preflight is missing",
    )
    require(
        "$buildxVersion = 'v0.36.1'" in deploy
        and "$buildxSha256 = '48af8a397ebd60178778bf63611dbcebe5f5e7a9be90eb9147b24b9587455778'"
        in deploy
        and "Install checksum-pinned Docker Buildx" in deploy
        and "github.com/docker/buildx/releases/download" in deploy
        and "sha256sum --check --strict" in deploy
        and 'docker buildx version | grep -F "${buildx_version#v}"' in deploy,
        "deployment must repair and verify the checksum-pinned Docker Buildx plugin",
    )
    forbid(re.search(r"\bgit\s+clone\b", deploy, flags=re.IGNORECASE) is not None, "deployment clones a repository")

    one_command_steps = [
        deploy_lab.find("scripts/check_lab_static.py"),
        deploy_lab.find("tests.test_lab_static"),
        deploy_lab.find("'plan', '-input=false'"),
        deploy_lab.find("scripts/check_lab_budget.py"),
        deploy_lab.find("'apply', '-input=false'"),
        deploy_lab.find("deploy-runtime.ps1"),
    ]
    require(
        all(index >= 0 for index in one_command_steps)
        and one_command_steps == sorted(one_command_steps),
        "one-command deployment must preserve static-test-plan-budget-apply-runtime order",
    )
    require(
        "[switch]$Apply" in deploy_lab
        and "JCAREER_SYNTHETIC_LAB_APPROVED" in deploy_lab,
        "one-command deployment must require the apply switch and activation acknowledgement",
    )
    require(
        ".terraform/tfplan-one-command" in deploy_lab
        and '"-out=$planRelativePath"' in deploy_lab
        and "'apply', '-input=false', '-no-color', $planRelativePath" in deploy_lab,
        "one-command deployment must apply only its checked saved plan",
    )
    require(
        "$destructiveChanges" in deploy_lab
        and ".Contains('delete')" in deploy_lab
        and "one-command apply is blocked" in deploy_lab,
        "one-command deployment must block deletes and replacements",
    )
    require(
        "get-caller-identity" in deploy_lab
        and "Protect-Diagnostic" in deploy_lab
        and "TF_VAR_enable_bedrock_live', 'false'" in deploy_lab,
        "one-command deployment must preflight credentials, redact diagnostics, and block Bedrock live",
    )
    forbid("-auto-approve" in deploy_lab, "one-command deployment uses forbidden auto-approve")
    forbid(
        re.search(r"(?:^|[\s'\"])\-target(?:=|[\s'\"])", deploy_lab) is not None,
        "one-command deployment uses forbidden Terraform target",
    )

    for port in (8000, 8100, 8200):
        require(f'"127.0.0.1:{port}:{port}"' in compose, f"host port {port} is not loopback-bound")
    require(
        '"${WEB_BIND_ADDRESS:-127.0.0.1}:3000:3000"' in compose,
        "web compose default is not loopback-bound",
    )
    require(
        re.search(r"location\s+~\s+\^/\(agent\|llm\)\(/\|\$\)\s*\{\s*return\s+404;\s*\}", nginx)
        is not None,
        "lab proxy must reject direct agent and llm paths",
    )
    require(
        "location /api/" in nginx and "proxy_pass $api_backend;" in nginx,
        "lab proxy API-only upstream route is missing",
    )
    for header in (
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Content-Security-Policy",
        "Permissions-Policy",
    ):
        require(f"add_header {header}" in nginx, f"lab proxy security header is missing: {header}")
    expected_limits = {
        "postgres": "384m",
        "redis": "128m",
        "agent": "256m",
        "llm-gateway": "384m",
        "api": "512m",
        "web": "128m",
    }
    for service, limit in expected_limits.items():
        require(
            re.search(
                rf"(?ms)^  {re.escape(service)}:\s+.*?^    mem_limit: {re.escape(limit)}$",
                lab_compose,
            )
            is not None,
            f"lab memory limit for {service} must remain {limit}",
        )
    require(
        "fallocate -l 2G /var/lib/jcareer-lab.swap" in user_data,
        "bounded encrypted-root swap file is missing",
    )

    forbid("runtime_public_url" in outputs, "public runtime URL output is present")
    forbid("aws_instance.runtime.public_ip" in outputs, "public IP is exposed as an output")
    require("operator_tunnel" in outputs and "http://127.0.0.1:3000/jobs" in outputs, "SSM tunnel output contract is missing")
    require("AWS use remains disabled" in readme, "current AWS-disabled boundary is missing from README")
    require("three Windows PCs, three Macs" in readme, "endpoint simulation boundary is missing")

    return errors


def audit_local_artifacts(root: Path) -> list[str]:
    """Report local state/cache exposure without printing any stored values."""
    warnings: list[str] = []
    lab = root / "terraform" / "lab"
    backup = lab / "terraform.tfstate.backup"
    if backup.is_file():
        try:
            state = json.loads(backup.read_text(encoding="utf-8"))
            resource_records = sum(
                len(resource.get("instances") or [])
                for resource in state.get("resources") or []
            )
            if resource_records:
                warnings.append(
                    "ignored terraform.tfstate.backup contains "
                    f"{resource_records} historical managed instance record(s); "
                    "a person must approve retention or disposal"
                )
        except (OSError, UnicodeError, json.JSONDecodeError):
            warnings.append(
                "ignored terraform.tfstate.backup exists but could not be safely inventoried"
            )

    state_artifacts = {
        path
        for path in lab.rglob("*")
        if path.is_file()
        and not path.name.startswith(".terraform.tfstate.lock.info")
        and (
            path.name == "terraform.tfstate"
            or path.name.endswith(".tfstate")
            or ".tfstate." in path.name
        )
        and path != backup
    }
    if state_artifacts:
        warnings.append(
            f"{len(state_artifacts)} additional Terraform state artifact(s) remain locally; "
            "stored values were not printed"
        )

    lock_artifacts = {
        path
        for path in lab.rglob("*")
        if path.is_file() and path.name.startswith(".terraform.tfstate.lock.info")
    }
    if lock_artifacts:
        warnings.append(f"{len(lock_artifacts)} Terraform lock artifact(s) remain locally")

    terraform_cache = lab / ".terraform"
    ignored_roots = {terraform_cache / "providers"}

    def under_ignored_root(path: Path) -> bool:
        return any(parent == path or parent in path.parents for parent in ignored_roots)

    plan_artifacts = {
        path
        for path in lab.rglob("*")
        if path.is_file()
        and not under_ignored_root(path)
        and (
            path.name.lower().startswith("tfplan")
            or path.suffix.lower() == ".tfplan"
            or (
                path.suffix.lower() == ".json"
                and "plan" in path.stem.lower()
            )
        )
    }
    if plan_artifacts:
        warnings.append(
            f"{len(plan_artifacts)} ignored saved plan/JSON artifact(s) remain locally; "
            "they may retain historical configuration values"
        )

    crash_artifacts = {
        path
        for path in lab.rglob("*")
        if path.is_file()
        and not under_ignored_root(path)
        and (path.name == "crash.log" or path.name.startswith("crash.") and path.suffix == ".log")
    }
    if crash_artifacts:
        warnings.append(
            f"{len(crash_artifacts)} Terraform crash artifact(s) remain locally; values were not printed"
        )

    if terraform_cache.is_dir():
        provider_bytes = sum(
            path.stat().st_size
            for path in (terraform_cache / "providers").rglob("*")
            if path.is_file()
        ) if (terraform_cache / "providers").is_dir() else 0
        if provider_bytes >= 256 * 1024 * 1024:
            warnings.append(
                "ignored Terraform provider cache occupies "
                f"approximately {provider_bytes // (1024 * 1024)} MiB on local disk"
            )
    return warnings


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
        sources = load_sources(args.root.resolve())
    except (OSError, UnicodeError) as exc:
        print(f"::error::{exc}")
        return 1

    errors = audit_sources(sources)
    warnings = audit_local_artifacts(args.root.resolve())
    print(
        "lab 정적 경계 · EC2 1대 · inbound 0 · Bedrock live 차단 · "
        "SSM loopback tunnel"
    )
    for warning in warnings:
        print(f"::warning::{warning}")
    for error in errors:
        print(f"::error::{error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
