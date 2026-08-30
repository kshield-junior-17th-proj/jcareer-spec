#!/usr/bin/env python3
"""AWS 호출 없이 terraform/lab의 소스 수준 실행 경계를 검사한다.

이 검사는 HCL validate/plan, 실제 AWS 구성, 비용 또는 통제 판정을 대신하지 않는다.
"""

from __future__ import annotations

import argparse
import hashlib
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
    "destroy_lab": Path("terraform/lab/provisioning/destroy-lab.ps1"),
    "lab_compose": Path("terraform/lab/provisioning/lab.compose.override.yaml"),
    "opendart_broker_compose": Path("terraform/lab/provisioning/opendart-broker.compose.override.yaml"),
    "bedrock_broker_compose": Path("terraform/lab/provisioning/bedrock-broker.compose.override.yaml"),
    "nginx": Path("terraform/lab/provisioning/nginx.lab.conf"),
    "preview_gate": Path("terraform/lab/preview_gate.js.tftpl"),
    "lab_lockfile": Path("terraform/lab/.terraform.lock.hcl"),
    "compose": Path("src/runtime/compose.yaml"),
    "broker": Path("src/runtime/aws_broker/app/main.py"),
    "broker_dockerfile": Path("src/runtime/aws_broker/Dockerfile"),
    "api_dockerfile": Path("src/runtime/api/Dockerfile"),
    "llm_dockerfile": Path("src/runtime/llm_gateway/Dockerfile"),
    "api_broker": Path("src/runtime/api/app/aws_broker_client.py"),
    "llm_broker": Path("src/runtime/llm_gateway/app/aws_broker_client.py"),
    "opendart_binding": Path("scripts/check_opendart_runtime_binding.py"),
    "readme": Path("terraform/lab/README.md"),
}

EXPECTED_NORMALIZED_SOURCE_SHA256 = {
    # Updated only after a human reviews the complete terraform/lab/main.tf
    # delta. Path.read_text normalizes platform newline sequences first.
    "main": "ea411f133cf82c3a137ab2e796f69974d25597140fb5eacc4d9f01a77677b2fb",
}


def _consume_hcl_heredoc(source: str, start: int) -> int:
    marker = re.match(r"<<-?([A-Za-z_][A-Za-z0-9_-]*)", source[start:])
    if marker is None:
        return start
    terminator = marker.group(1)
    line_end = source.find("\n", start)
    if line_end < 0:
        return len(source)
    index = line_end + 1
    while index < len(source):
        line_end = source.find("\n", index)
        if line_end < 0:
            line_end = len(source)
            next_index = line_end
        else:
            next_index = line_end + 1
        if source[index:line_end].strip() == terminator:
            return next_index
        index = next_index
    return len(source)


def _consume_hcl_template_expression(source: str, start: int) -> int:
    """Return the first offset after one ${...} or %{...} expression."""
    index = start + 2
    depth = 1
    while index < len(source):
        char = source[index]
        nxt = source[index + 1] if index + 1 < len(source) else ""
        if char == '"':
            index = _consume_hcl_quoted_template(source, index)
            continue
        if char == "/" and nxt == "*":
            close = source.find("*/", index + 2)
            if close < 0:
                return len(source)
            index = close + 2
            continue
        if (char == "/" and nxt == "/") or char == "#":
            line_end = source.find("\n", index)
            index = len(source) if line_end < 0 else line_end + 1
            continue
        if char == "<" and nxt == "<":
            heredoc_end = _consume_hcl_heredoc(source, index)
            if heredoc_end != index:
                index = heredoc_end
                continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return len(source)


def _consume_hcl_quoted_template(source: str, start: int) -> int:
    """Return the first offset after a quoted HCL template string."""
    index = start + 1
    while index < len(source):
        char = source[index]
        nxt = source[index + 1] if index + 1 < len(source) else ""
        if char == "\\":
            index += 2
            continue
        if char == '"':
            return index + 1
        if (
            char in {"$", "%"}
            and nxt == "{"
            and (index == start + 1 or source[index - 1] != char)
        ):
            index = _consume_hcl_template_expression(source, index)
            continue
        index += 1
    return len(source)


def _strip_hcl_comments_and_heredocs(source: str) -> str:
    """Remove comments and heredocs with one lexer while preserving newlines.

    A heredoc body is data: quotes and comment delimiters inside it must not
    change the lexer state used for the HCL that follows the terminator.
    Conversely, a heredoc-looking token inside a quoted string is only text.
    """
    output: list[str] = []
    index = 0
    block_comment = False
    heredoc_end: str | None = None
    while index < len(source):
        if heredoc_end is not None:
            line_end = source.find("\n", index)
            if line_end < 0:
                line_end = len(source)
                has_newline = False
            else:
                has_newline = True
            line = source[index:line_end]
            output.extend(" " for _ in line)
            if has_newline:
                output.append("\n")
                index = line_end + 1
            else:
                index = line_end
            if line.strip() == heredoc_end:
                heredoc_end = None
            continue

        char = source[index]
        nxt = source[index + 1] if index + 1 < len(source) else ""
        if block_comment:
            if char == "*" and nxt == "/":
                output.extend((" ", " "))
                index += 2
                block_comment = False
            else:
                # A block comment is expression whitespace. Preserving an
                # internal newline would create a false end-of-attribute anchor.
                output.append(" ")
                index += 1
            continue
        if char == '"':
            quoted_end = _consume_hcl_quoted_template(source, index)
            output.extend(source[index:quoted_end])
            index = quoted_end
            continue
        if char == "/" and nxt == "*":
            output.extend((" ", " "))
            index += 2
            block_comment = True
            continue
        if (char == "/" and nxt == "/") or char == "#":
            while index < len(source) and source[index] != "\n":
                output.append(" ")
                index += 1
            continue
        if char == "<" and nxt == "<":
            marker = re.match(r"<<-?([A-Za-z_][A-Za-z0-9_-]*)", source[index:])
            if marker is not None:
                heredoc_end = marker.group(1)
                line_end = source.find("\n", index)
                if line_end < 0:
                    output.extend(" " for _ in source[index:])
                    index = len(source)
                else:
                    output.extend(" " for _ in source[index:line_end])
                    output.append("\n")
                    index = line_end + 1
                continue
        output.append(char)
        index += 1
    return "".join(output)


def _mask_hcl_quoted_strings(source: str) -> str:
    """Mask quoted-string contents so attribute checks cannot match decoys."""
    output: list[str] = []
    index = 0
    while index < len(source):
        char = source[index]
        if char == '"':
            quoted_end = _consume_hcl_quoted_template(source, index)
            output.extend("\n" if item == "\n" else " " for item in source[index:quoted_end])
            index = quoted_end
        else:
            output.append(char)
            index += 1
    return "".join(output)


def _extract_hcl_block(source: str, header_pattern: str) -> str:
    cleaned = _strip_hcl_comments_and_heredocs(source)
    match = re.search(header_pattern + r"\s*\{", cleaned)
    if match is None:
        return ""
    start = match.end()
    depth = 1
    index = start
    while index < len(cleaned):
        char = cleaned[index]
        if char == '"':
            index = _consume_hcl_quoted_template(cleaned, index)
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return cleaned[start:index]
        index += 1
    return ""


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
    destroy_lab = sources["destroy_lab"]
    lab_compose = sources["lab_compose"]
    opendart_broker_compose = sources["opendart_broker_compose"]
    bedrock_broker_compose = sources["bedrock_broker_compose"]
    nginx = sources["nginx"]
    preview_gate = sources["preview_gate"]
    lab_lockfile = sources["lab_lockfile"]
    compose = sources["compose"]
    broker = sources["broker"]
    broker_dockerfile = sources["broker_dockerfile"]
    api_dockerfile = sources["api_dockerfile"]
    llm_dockerfile = sources["llm_dockerfile"]
    api_broker = sources["api_broker"]
    llm_broker = sources["llm_broker"]
    opendart_binding = sources["opendart_binding"]
    readme = sources["readme"]
    runtime_instance_block = _extract_hcl_block(
        main,
        r'resource\s+"aws_instance"\s+"runtime"',
    )
    runtime_instance_code = _mask_hcl_quoted_strings(runtime_instance_block)

    def require(observed: bool, message: str) -> None:
        if not observed:
            errors.append(message)

    def forbid(observed: bool, message: str) -> None:
        if observed:
            errors.append(message)

    def variable_block(name: str) -> str:
        match = re.search(
            rf'(?ms)^variable\s+"{re.escape(name)}"\s*\{{.*?^\}}',
            variables,
        )
        return match.group(0) if match else ""

    require(
        hashlib.sha256(main.encode("utf-8")).hexdigest()
        == EXPECTED_NORMALIZED_SOURCE_SHA256["main"],
        "terraform/lab/main.tf differs from the reviewed exact source digest",
    )

    require(
        set(sources["terraform_file_names"].splitlines())
        == {"main.tf", "outputs.tf", "variables.tf", "versions.tf"},
        "terraform/lab contains an unexpected or missing top-level .tf file",
    )
    require(
        'provider "registry.terraform.io/hashicorp/aws"' in lab_lockfile
        and 'version     = "6.59.0"' in lab_lockfile
        and 'constraints = "6.59.0"' in lab_lockfile
        and '"zh:' in lab_lockfile,
        "terraform/lab AWS provider lockfile is missing or differs from the pinned provider",
    )
    require(
        len(re.findall(r'resource\s+"aws_instance"\s+"', terraform_all)) == 1,
        "aws_instance resource must appear exactly once",
    )
    expected_resource_blocks = Counter(
        {
            "aws_vpc": 1,
            "aws_subnet": 2,
            "aws_internet_gateway": 1,
            "aws_eip": 1,
            "aws_nat_gateway": 1,
            "aws_route_table": 2,
            "aws_route": 2,
            "aws_route_table_association": 2,
            "aws_security_group": 1,
            "aws_vpc_security_group_egress_rule": 1,
            "aws_vpc_security_group_ingress_rule": 1,
            "aws_iam_role": 1,
            "aws_iam_role_policy_attachment": 1,
            "aws_iam_role_policy": 1,
            "aws_iam_instance_profile": 1,
            "aws_instance": 1,
            "aws_budgets_budget": 1,
            "aws_cloudfront_vpc_origin": 1,
            "aws_cloudfront_function": 1,
            "aws_cloudfront_distribution": 1,
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
        == Counter(
            {
                "aws_ssm_parameter": 1,
                "aws_iam_policy_document": 2,
                "aws_security_group": 1,
            }
        ),
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
        re.search(r"(?m)^\s*default\s*=\s*false\s*$", variable_block("enable_bedrock_live"))
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
        'var.bedrock_live_acknowledgement == "JCAREER_SYNTHETIC_BEDROCK_APPROVED"'
        in variables
        and 'var.bedrock_live_acknowledgement == "JCAREER_SYNTHETIC_BEDROCK_APPROVED"'
        in main,
        "Bedrock live must require the separate capability-broker acknowledgement",
    )
    require(
        re.search(r"(?m)^\s*default\s*=\s*false\s*$", variable_block("enable_opendart_live"))
        is not None
        and 'var.opendart_live_acknowledgement == "JCAREER_SYNTHETIC_OPENDART_LIVE_APPROVED"'
        in variables
        and 'var.opendart_live_acknowledgement == "JCAREER_SYNTHETIC_OPENDART_LIVE_APPROVED"'
        in main,
        "OpenDART live must default off and require its separate acknowledgement",
    )

    require(
        re.search(
            r"(?m)^\s*default\s*=\s*false\s*$",
            variable_block("enable_aws_https_preview"),
        )
        is not None,
        "AWS HTTPS preview must default to disabled",
    )
    require(
        'JCAREER_SYNTHETIC_HTTPS_PREVIEW_APPROVED' in variables
        and 'can(regex("^[0-9a-f]{64}$", var.preview_access_token_sha256))' in variables
        and 'sensitive   = true' in variables,
        "AWS HTTPS preview requires a separate acknowledgement and sensitive token digest",
    )
    forbid(
        re.search(r"\bpreview_access_token\b", variables + main) is not None,
        "raw preview token must not enter Terraform variables or resources",
    )
    require(
        'resource "aws_vpc_security_group_ingress_rule" "cloudfront_preview"' in main
        and 'count = var.enable_aws_https_preview ? 1 : 0' in main
        and 'values = ["CloudFront-VPCOrigins-Service-SG"]' in main
        and 'depends_on = [aws_cloudfront_vpc_origin.preview]' in main
        and 'data.aws_security_group.cloudfront_vpc_origin_service[0].id' in main
        and 'from_port   = 3000' in main
        and 'to_port     = 3000' in main
        and 'ip_protocol = "tcp"' in main,
        "HTTPS preview ingress must be conditional VPC-origin service-SG TCP/3000 only",
    )
    require(
        'resource "aws_subnet" "private_preview"' in main
        and 'cidr_block              = "10.91.0.64/26"' in main
        and 'map_public_ip_on_launch = false' in main
        and 'resource "aws_nat_gateway" "preview"' in main
        and 'nat_gateway_id         = aws_nat_gateway.preview[0].id' in main
        and 'aws_subnet.private_preview[0].id' in main
        and 'associate_public_ip_address = var.enable_aws_https_preview ? false : true' in main,
        "HTTPS preview origin must move to a private subnet with conditional NAT egress",
    )
    require(
        len(re.findall(r"(?m)^\s*subnet_id\s*=", runtime_instance_code)) == 1
        and re.search(
            r"(?m)^[ \t]*subnet_id\s*=\s*var\.enable_aws_https_preview\s*\?\s*"
            r"\(\s*aws_subnet\.private_preview\[0\]\.id\s*\)\s*:\s*"
            r"aws_subnet\.public\.id[ \t]*$",
            runtime_instance_code,
        )
        is not None,
        "HTTPS subnet condition must map true to private and false to public",
    )
    forbid(
        re.search(
            r'resource\s+"aws_vpc_security_group_ingress_rule"[\s\S]*?cidr_ipv[46]\s*=',
            main,
        )
        is not None,
        "HTTPS preview ingress must not use a public CIDR",
    )
    forbid(re.search(r"\bingress\s*\{", terraform_all) is not None, "inline security-group ingress is present")
    forbid(re.search(r"\b(from_port|to_port)\s*=\s*22\b", terraform_all) is not None, "SSH port is present")
    forbid(re.search(r"\bkey_name\s*=", terraform_all) is not None, "EC2 key pair attachment is present")
    for forbidden_type in ("aws_key_pair", "tls_private_key", "local_file", "null_resource"):
        forbid(
            re.search(rf'resource\s+"{forbidden_type}"\s+"', terraform_all) is not None,
            f"forbidden lab resource type is present: {forbidden_type}",
        )

    require(
        'resource "aws_cloudfront_vpc_origin" "preview"' in main
        and 'arn                    = aws_instance.runtime.arn' in main
        and 'http_port              = 3000' in main
        and 'origin_protocol_policy = "http-only"' in main
        and 'domain_name = aws_instance.runtime.private_dns' in main,
        "CloudFront must use the reviewed VPC origin rather than the public EC2 address",
    )
    require(
        len(re.findall(r"(?m)^\s{2}origin\s*\{", main)) == 1
        and main.count('origin_id   = "jcareer-runtime-vpc-origin"') == 1
        and main.count('target_origin_id       = "jcareer-runtime-vpc-origin"') == 1,
        "CloudFront must have one reviewed origin and route its default behavior to it",
    )
    require(
        'viewer_protocol_policy = "redirect-to-https"' in main
        and 'is_ipv6_enabled     = false' in main
        and 'cache_policy_id            = local.cloudfront_caching_disabled_policy_id' in main
        and 'origin_request_policy_id   = local.cloudfront_all_viewer_except_host_policy' in main
        and 'cloudfront_default_certificate = true' in main
        and 'minimum_protocol_version       = "TLSv1.2_2021"' in main
        and 'event_type   = "viewer-request"' in main,
        "CloudFront TLS, no-cache, full-request, and viewer gate contracts are incomplete",
    )
    for method in ("DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"):
        require(f'"{method}"' in main, f"CloudFront allowed methods omit {method}")
    require(
        "request.querystring" in preview_gate
        and 'require("crypto")' in preview_gate
        and preview_gate.count('createHash("sha256")') >= 2
        and "accessTokenSha256" in preview_gate
        and 'attributes: "Secure; HttpOnly; SameSite=Strict; Path=/; Max-Age=' in preview_gate
        and "function tokenMatches(value)" in preview_gate
        and "value: bootstrap.value" in preview_gate
        and "!tokenMatches(previewCookie.value)" in preview_gate
        and preview_gate.count('"referrer-policy": { value: "no-referrer" }') == 2
        and 'update(event.viewer.ip).digest("hex")' in preview_gate
        and "delete request.cookies[cookieName]" in preview_gate
        and '"location": { value: "/jobs" }' in preview_gate
        and "J-Career synthetic preview access is required." in preview_gate,
        "preview edge function must hash bootstrap and cookie values without accepting the stored digest as a bearer",
    )
    for header in (
        "x-jcareer-viewer-key",
        "x-jcareer-forwarded-proto",
        "x-jcareer-edge-request-id",
    ):
        require(
            f'request.headers["{header}"]' in preview_gate,
            f"preview edge function must overwrite custom header {header}",
        )
        require(
            f"$http_{header.replace('-', '_')}" in nginx,
            f"lab proxy must consume custom header {header}",
        )
    forbid(
        "cloudfront_viewer_address" in nginx or "cloudfront_forwarded_proto" in nginx,
        "lab proxy must not depend on absent CloudFront-generated headers",
    )
    require(
        "proxy_set_header X-Forwarded-For $remote_addr;" in nginx,
        "lab proxy must not place the hashed rate-limit key in X-Forwarded-For",
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
        "ignore_changes = [user_data]" in main,
        "healthy lab host must not be replaced solely by an SSM-delivered bootstrap revision",
    )
    require(
        "기존 인스턴스의 user_data 변경은 무시되므로 실제 타이머 관찰값이 아니다" in outputs,
        "auto-stop output must not claim an unobserved existing-instance timer",
    )

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
    for operator_source, label in (
        (deploy, "runtime deploy"),
        (deploy_lab, "one-command deploy"),
        (destroy_lab, "guarded destroy"),
    ):
        require(
            all(
                marker in operator_source
                for marker in (
                    "nat|eipalloc",
                    "[REDACTED_VPC_ORIGIN_ID]",
                    "[REDACTED_CLOUDFRONT_ID]",
                    "[REDACTED_CLOUDFRONT_DOMAIN]",
                    "[REDACTED_IP]",
                )
            ),
            f"{label} diagnostics must cover HTTPS-preview resource and network identifiers",
        )
        require(
            "Resolve-RequiredApplication" in operator_source
            and "-CommandType Application" in operator_source
            and "[IO.Path]::GetFullPath([string]$command.Source)" in operator_source,
            f"{label} must bind native tools to Application-type absolute paths",
        )
    require(
        "$script:curlPath = Resolve-RequiredApplication -Name 'curl.exe'" in deploy_lab
        and "Microsoft.PowerShell.Management\\Start-Process $bootstrapUrl" in deploy_lab,
        "one-command deployment must bind preview-token consumers to native or module-qualified commands",
    )
    require("InstanceType -ne 't3.small'" in deploy, "deployment must reject unverified instance sizes")
    require("IamInstanceProfile.Arn" in deploy, "deployment instance-profile check is missing")
    require(
        "$profileName -ne $instanceName" in deploy
        and "instance profile does not match the reviewed runtime Name tag" in deploy
        and "iam', 'get-instance-profile'" in deploy
        and "$roles.Count -ne 1" in deploy,
        "deployment must bind the target instance to its reviewed runtime profile name",
    )
    require(
        "JCAREER_SYNTHETIC_BEDROCK_APPROVED" in deploy,
        "separate Bedrock acknowledgement is missing",
    )
    require(
        "bedrock-broker.compose.override.yaml" in deploy
        and "opendart-broker.compose.override.yaml" in deploy
        and "check_opendart_runtime_binding.py" in deploy
        and "OpenDART wiring requires the exact 11-resource runtime-stage state" in deploy
        and "-ExpectedApiRoleName $script:labRoleName" in deploy
        and "OpenDART sender policy is not attached to the validated lab instance role" in deploy
        and "Verify J-Career AWS capability broker boundaries" in deploy,
        "deployment must consume the approved OpenDART state and separated capability brokers",
    )
    require(
        "$queueName -notmatch '^[a-z0-9][a-z0-9_-]{2,74}\\.fifo$'" in deploy
        and "$tableName -notmatch '^[a-z0-9][a-z0-9_.-]{2,79}$'" in deploy
        and 'SAFE_FIFO_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{2,74}\\.fifo$")'
        in broker
        and 'SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,79}$")' in broker
        and "SAFE_FIFO_NAME.fullmatch(queue_name)" in broker,
        "OpenDART deployment preflight and broker name allowlists must remain identical",
    )
    require(
        "$provider = if ($EnableBedrockLive) { 'bedrock' } else { 'local-synthetic-stub' }" in deploy,
        "deployment provider must default to the local stub",
    )
    require(
        "$webBindAddress = if ($EnableAwsHttpsPreview) { '0.0.0.0' } else { '127.0.0.1' }"
        in deploy
        and "Assert-PreviewIngressBoundary" in deploy
        and "CloudFront-VPCOrigins-Service-SG" in deploy
        and "VPC origin service SG on TCP/3000" in deploy
        and "HTTPS preview instance must not have a public IP" in deploy
        and "MapPublicIpOnLaunch" in deploy
        and "JCAREER_SYNTHETIC_HTTPS_PREVIEW_APPROVED" in deploy,
        "remote web binding must be conditional on the exact VPC-origin service-SG boundary",
    )
    require(
        "$archiveSha256 = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256)"
        in deploy
        and "echo '$archiveSha256  /tmp/jcareer-runtime.tgz' | sha256sum --check --strict"
        in deploy,
        "runtime archive integrity check is missing",
    )
    require(
        "$script:validatedTarget" in deploy and "'ec2', 'stop-instances'" in deploy,
        "deployment failure must stop only a preflight-validated target",
    )
    target_validation_steps = [
        deploy.find("$validatedInstance = Get-ValidatedLabInstance"),
        deploy.find("$script:validatedTarget = $true"),
        deploy.find("Assert-PreviewIngressBoundary -Instance $validatedInstance"),
        deploy.find("$script:openDartBackendConfig = (Resolve-Path"),
    ]
    require(
        all(index >= 0 for index in target_validation_steps)
        and target_validation_steps == sorted(target_validation_steps),
        "deployment must establish the bounded stop target before ingress and OpenDART checks",
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
        deploy_lab.find("'apply', '-input=false', '-no-color', $operationPlanRelativePath"),
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
        and "'apply', '-input=false', '-no-color', $operationPlanRelativePath" in deploy_lab,
        "one-command deployment must apply only its checked saved plan",
    )
    for operator_source, label in (
        (deploy_lab, "one-command deployment"),
        (destroy_lab, "guarded destroy"),
    ):
        require(
            all(
                marker in operator_source
                for marker in (
                    "Open-ReadLockedFile",
                    "Get-ReadLockedSha256",
                    "[IO.FileShare]::Read\n",
                    "$planReadLock",
                    "$planJsonReadLock",
                    "changed after validation; apply is blocked",
                )
            ),
            f"{label} must read-lock and re-hash the saved plan and checked JSON through apply",
        )
    require(
        "-lockfile=readonly" in deploy_lab
        and "-lockfile=readonly" in destroy_lab
        and "-lockfile=readonly" in deploy,
        "lab and linked OpenDART Terraform init must use the reviewed provider lockfiles read-only",
    )
    require(
        "$destructiveChanges" in deploy_lab
        and ".Contains('delete')" in deploy_lab
        and "one-command apply is blocked" in deploy_lab,
        "one-command deployment must block deletes and replacements",
    )
    forbid(
        "$edgeGateOnlyUpdate" in deploy_lab or "Only the preview edge token changed" in deploy_lab,
        "one-command deployment must not skip runtime checks for an edge-token-only update",
    )
    require(
        "get-caller-identity" in deploy_lab
        and "Protect-Diagnostic" in deploy_lab
        and "TF_VAR_enable_bedrock_live" in deploy_lab
        and "TF_VAR_bedrock_live_acknowledgement" in deploy_lab
        and "TF_VAR_enable_opendart_live" in deploy_lab
        and "TF_VAR_opendart_live_acknowledgement" in deploy_lab
        and "TF_VAR_enable_aws_https_preview" in deploy_lab
        and "TF_VAR_preview_access_token_sha256" in deploy_lab
        and "[Security.SecureString]$HttpsPreviewBootstrapToken" in deploy_lab
        and "ZeroFreeBSTR" in deploy_lab
        and "Preview bootstrap approval SHA-256 (not a bearer)" in deploy_lab
        and "[Security.Cryptography.SHA256]::Create()" in deploy_lab
        and "same operator-retained SecureString bootstrap token" in deploy_lab
        and "[REDACTED_PREVIEW_TOKEN]" in deploy_lab
        and "[REDACTED_PREVIEW_DIGEST]" in deploy_lab
        and "Start-Process $bootstrapUrl" in deploy_lab,
        "one-command deployment must hash the preview token, redact diagnostics, and bind live-provider acknowledgements",
    )
    for operator_source, phases, label in (
        (
            deploy_lab,
            (
                "saved-plan review completion",
                "Terraform apply",
                "apply completion recording",
            ),
            "one-command deployment",
        ),
        (
            destroy_lab,
            (
                "saved destroy-plan review completion",
                "Terraform destroy apply",
                "destroy completion recording",
            ),
            "guarded destroy",
        ),
    ):
        require(
            "[string]$ProviderAccountSha256" in operator_source
            and "Get-ObservedProviderAccountSha256" in operator_source
            and "Assert-ProviderAccountBinding" in operator_source
            and "'--query', 'Account'" in operator_source
            and "'--output', 'text'" in operator_source
            and "^([0-9a-f])\\1{63}$" in operator_source
            and "provider_account_sha256=$plannedProviderAccountSha256" in operator_source
            and all(phase in operator_source for phase in phases),
            f"{label} must bind plan and apply/destroy observations to one non-placeholder provider account digest",
        )
    for operator_source, label in (
        (deploy_lab, "one-command deployment"),
        (destroy_lab, "guarded destroy"),
    ):
        require(
            "[string]$ReviewedPlanSemanticSha256" in operator_source
            and "Get-PlanSemanticSha256" in operator_source
            and "$planDocument.PSObject.Properties.Remove('timestamp')" in operator_source
            and "reviewed_plan_semantic_sha256=$planSemanticSha256" in operator_source
            and "human-reviewed semantic plan digest" in operator_source,
            f"{label} must bind apply to the human-reviewed timestamp-free semantic plan digest",
        )
    for operator_source, plan_command, operation_plan_argument, consumption_marker, label in (
        (
            deploy_lab,
            "'plan', '-input=false', '-no-color'",
            "$operationPlanRelativePath",
            "$script:planConsumptionStarted",
            "one-command deployment",
        ),
        (
            destroy_lab,
            "'plan', '-destroy', '-input=false', '-no-color'",
            "$operationPlanRelativePath",
            "$script:destroyPlanConsumptionStarted",
            "guarded destroy",
        ),
    ):
        main_start = operator_source.find("Push-Location $repoRoot")
        mutex_index = operator_source.find("$planMutex = [Threading.Mutex]::new", main_start)
        file_lock_index = operator_source.find("$planOperationLock = [IO.File]::Open", main_start)
        pending_check_index = operator_source.find(
            "\n    Assert-NoPendingLabPlanConsumption\n", main_start
        )
        account_preflight_index = operator_source.find(
            "$plannedProviderAccountSha256 = Get-ObservedProviderAccountSha256", main_start
        )
        terraform_version_index = operator_source.find("-Label 'Terraform version'", main_start)
        terraform_init_index = operator_source.find("-Label 'terraform init'", main_start)
        load_index = operator_source.find("Loading the retained human-reviewed saved")
        else_index = operator_source.find("\n    else {", load_index)
        plan_index = operator_source.find(plan_command, else_index)
        semantic_index = operator_source.find("$planSemanticSha256 =", plan_index)
        consume_index = operator_source.find(f"{consumption_marker} = $true", semantic_index)
        apply_index = operator_source.find(
            f"'apply', '-input=false', '-no-color', {operation_plan_argument}",
            consume_index,
        )
        cleanup_index = operator_source.find("Complete-LabPlanConsumption", apply_index)
        require(
            "[string]$ReviewedSavedPlanSha256" in operator_source
            and "reviewed_saved_plan_sha256=$validatedPlanSha256" in operator_source
            and "no re-plan is performed" in operator_source
            and "[IO.File]::ReadAllText($planJsonPath, [Text.Encoding]::UTF8)" in operator_source
            and re.search(
                r"\[string\]::Equals\(\s*\$validatedPlanSha256,\s*"
                r"\$ReviewedSavedPlanSha256,\s*\[StringComparison\]::Ordinal\s*\)",
                operator_source,
            )
            is not None
            and operator_source.count(plan_command) == 1
            and len(re.findall(r'''(?<![A-Za-z0-9_])(["'])plan\1''', operator_source)) == 1
            and "[Threading.Mutex]::new" in operator_source
            and "jcareer-lab-plan-operation.lock" in operator_source
            and "[IO.FileMode]::OpenOrCreate" in operator_source
            and "[IO.FileShare]::None" in operator_source
            and "Assert-NoPendingLabPlanConsumption" in operator_source
            and "New-LabPlanConsumptionMarker" in operator_source
            and "IN_PROGRESS_REVIEWED_PLAN_CONSUMPTION" in operator_source
            and "[IO.File]::Move($planPath, $operationPlanPath)" in operator_source
            and "[IO.File]::Move($planJsonPath, $operationPlanJsonPath)" in operator_source
            and "the durable marker and operation artifacts remain" in operator_source
            and all(index >= 0 for index in (
                load_index,
                else_index,
                plan_index,
                semantic_index,
                consume_index,
                apply_index,
                cleanup_index,
                main_start,
                mutex_index,
                file_lock_index,
                pending_check_index,
                account_preflight_index,
                terraform_version_index,
                terraform_init_index,
            ))
            and main_start < mutex_index < file_lock_index < pending_check_index
            < account_preflight_index < terraform_version_index < terraform_init_index < plan_index
            and load_index < else_index < plan_index < semantic_index < consume_index < apply_index < cleanup_index,
            f"{label} must mutex-serialize, exactly hash-bind, and durably consume the reviewed binary plan without re-planning on apply",
        )
    required_runtime_intent_variables = (
        "activation_acknowledgement",
        "enable_bedrock_live",
        "bedrock_live_acknowledgement",
        "enable_opendart_live",
        "opendart_live_acknowledgement",
        "enable_aws_https_preview",
        "https_preview_acknowledgement",
        "preview_access_token_sha256",
    )
    intent_function_start = deploy_lab.find("function Assert-PlanRuntimeIntent")
    intent_function_end = deploy_lab.find("function Get-ObservedProviderAccountSha256", intent_function_start)
    intent_function = (
        deploy_lab[intent_function_start:intent_function_end]
        if 0 <= intent_function_start < intent_function_end
        else ""
    )
    require(
        all(name in intent_function for name in required_runtime_intent_variables)
        and 0 <= deploy_lab.find("Assert-PlanRuntimeIntent -PlanDocument $planDocument")
        < deploy_lab.find("scripts/check_lab_budget.py"),
        "one-command deployment must bind Terraform-bearing runtime intent to the reviewed saved plan",
    )
    require(
        "if ($script:previewToken -match '^([0-9a-f])\\1{63}$')" in deploy_lab
        and "obvious repeated-character placeholder" in deploy_lab,
        "HTTPS preview bootstrap token must reject obvious repeated-character placeholders",
    )
    require(
        "[Collections.Generic.HashSet[char]]::new()" in deploy_lab
        and "$tokenAlphabet.Count -lt 8" in deploy_lab
        and "@(1..32)" in deploy_lab
        and "repeated low-period pattern" in deploy_lab,
        "HTTPS preview bootstrap token must reject low-diversity and periodic placeholders",
    )
    require(
        destroy_lab.count("destroy completion recording") >= 2,
        "guarded destroy must bind plan and apply/destroy observations to one non-placeholder provider account digest",
    )
    require(
        "Post-apply lab verification failed; requesting a fail-safe stop" in deploy_lab
        and "'ec2', 'stop-instances'" in deploy_lab
        and "Stopping EC2 does not remove NAT or CloudFront" in deploy_lab,
        "one-command post-apply failures must stop the validated runtime and preserve explicit destroy approval",
    )
    forbid(
        re.search(r"TF_VAR_preview_access_token(?!_sha256)", deploy_lab) is not None,
        "one-command deployment must not pass the raw preview token to Terraform",
    )
    forbid("-auto-approve" in deploy_lab, "one-command deployment uses forbidden auto-approve")
    forbid(
        re.search(r"(?:^|[\s'\"])\-target(?:=|[\s'\"])", deploy_lab) is not None,
        "one-command deployment uses forbidden Terraform target",
    )

    broker_compose = opendart_broker_compose + "\n" + bedrock_broker_compose
    require(
        "SO_PEERCRED" in broker
        and 'credentials.method != "iam-role"' in broker
        and "FORBIDDEN_CREDENTIAL_ENV" in broker
        and "asyncio.start_unix_server" in broker,
        "capability broker must require EC2 role credentials and a peer-checked Unix socket",
    )
    require(
        "network_mode: host" in opendart_broker_compose
        and "network_mode: host" in bedrock_broker_compose
        and 'BROKER_EXPECTED_PEER_UID: "11001"' in opendart_broker_compose
        and 'BROKER_EXPECTED_PEER_UID: "11002"' in bedrock_broker_compose
        and "/run/jcareer-opendart/broker.sock" in api_broker + opendart_broker_compose
        and "/run/jcareer-bedrock/broker.sock" in llm_broker + bedrock_broker_compose,
        "OpenDART and Bedrock must use separate fixed-UID Unix-socket brokers",
    )
    opendart_tmpfiles_rule = "d /run/jcareer-opendart 0750 11001 11001 -"
    bedrock_tmpfiles_rule = "d /run/jcareer-bedrock 0750 11002 11002 -"
    opendart_tmpfiles_index = deploy.find(opendart_tmpfiles_rule)
    bedrock_tmpfiles_index = deploy.find(bedrock_tmpfiles_rule)
    compose_up_index = deploy.find("docker compose $composeFileArguments up --build")
    require(
        opendart_tmpfiles_index >= 0
        and bedrock_tmpfiles_index >= 0
        and compose_up_index >= 0
        and opendart_tmpfiles_index < compose_up_index
        and bedrock_tmpfiles_index < compose_up_index
        and "systemd-tmpfiles --create /etc/tmpfiles.d/jcareer-opendart.conf" in deploy
        and "systemd-tmpfiles --create /etc/tmpfiles.d/jcareer-bedrock.conf" in deploy
        and "stat -c ''%u:%g:%a'' /run/jcareer-opendart" in deploy
        and "stat -c ''%u:%g:%a'' /run/jcareer-bedrock" in deploy
        and '"11001:11001:750"' in deploy
        and '"11002:11002:750"' in deploy,
        "broker socket directories must be recreated with fixed ownership before compose starts and after host reboot",
    )
    forbid("ports:" in broker_compose, "capability brokers must not publish TCP ports")
    forbid("docker.sock" in broker_compose, "capability brokers must not receive the Docker socket")
    forbid(
        "AccessKeyId" in broker or "SecretAccessKey" in broker,
        "capability broker must not implement a credential-return path",
    )
    require(
        'AWS_EC2_METADATA_DISABLED: "true"' in compose
        and "USER 11001:11001" in api_dockerfile
        and "USER 11002:11002" in llm_dockerfile
        and "USER ${RUNTIME_UID}:${RUNTIME_GID}" in broker_dockerfile,
        "application and broker images must preserve their reviewed non-root UID boundary",
    )
    require(
        "OpenDART runtime receipt/backend binding" in opendart_binding
        and "runtime_smoke_completed" in opendart_binding
        and "artifact_sha256" in opendart_binding,
        "OpenDART runtime binding checker is incomplete",
    )
    stage_a_index = readme.find("1. **Stage A")
    stage_b_index = readme.find("2. **Stage B")
    stage_c_index = readme.find("3. **Stage C")
    teardown_index = readme.find("For teardown, reverse the dependency.")
    publisher_prepare_index = readme.find("Invoke-ApprovedOpenDartWorkerPublish.ps1 -Mode Prepare")
    publisher_review_index = readme.find("Invoke-ApprovedOpenDartWorkerPublish.ps1 -Mode Review")
    publisher_publish_index = readme.find("Invoke-ApprovedOpenDartWorkerPublish.ps1 -Mode Publish")
    publisher_runtime_index = readme.find("# Stage B2 runtime")
    publisher_bootstrap_index = readme.find("# Stage B1 bootstrap")
    stage_c_command_index = readme.find("# Stage C plan-only")
    require(
        "Clean-state OpenDART staging" in readme
        and 0 <= stage_a_index < stage_b_index < stage_c_index < teardown_index
        and 0 <= publisher_bootstrap_index < publisher_prepare_index < publisher_review_index
        < publisher_publish_index < publisher_runtime_index < stage_c_command_index
        and "Choose the final HTTPS shape in Stage A" in readme
        and "runtime_role_name=<non-secret-role-name>" in readme
        and "-VarFile <bootstrap-var-file>" in readme
        and "-VarFile <runtime-var-file>" in readme
        and "-ArtifactSha256 <64-hex-ECR-image-digest-without-sha256-prefix>" in readme
        and "JCAREER_SYNTHETIC_OPENDART_SCAN_PREPARATION" in readme
        and "JCAREER_SYNTHETIC_OPENDART_PUBLISH_BINDINGS_REVIEW" in readme
        and "<separate-human-approved-publish-record>" in readme
        and "recorded six vulnerability occurrences" in readme
        and "`AWAITING_HUMAN_SCAN_DISPOSITION`" in readme
        and "No human disposition, push, runtime apply, or" in readme
        and "OpenDART call has been recorded." in readme
        and "does not contain a guarded OpenDART worker image publisher" not in readme
        and readme.count("-EnableOpenDartLive") >= 3
        and "Disable the lab broker first" in readme
        and "remove the OpenDART root before destroying the lab role" in readme,
        "clean-state OpenDART staging and reverse-order teardown are not documented",
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
    require(
        "$http_x_jcareer_viewer_key" in nginx
        and "$jcareer_rate_key" in nginx
        and "$http_x_jcareer_forwarded_proto" in nginx
        and "$http_x_jcareer_edge_request_id" in nginx,
        "lab proxy must derive rate, scheme, and request context from overwritten preview headers",
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

    forbid("aws_instance.runtime.public_ip" in outputs, "public IP is exposed as an output")
    require("operator_tunnel" in outputs and "http://127.0.0.1:3000/jobs" in outputs, "SSM tunnel output contract is missing")
    require(
        "runtime_role_name" in outputs
        and "aws_iam_role.runtime.name" in outputs
        and "terraform runtime role output" in deploy_lab
        and 'Write-Host "runtime_role_name=$runtimeRoleName"' in deploy_lab,
        "lab apply must emit the bounded non-secret OpenDART role-name handoff",
    )
    require(
        "aws_https_preview_url" in outputs
        and "aws_cloudfront_distribution.preview[0].domain_name" in outputs
        and "jcareer_preview" not in outputs,
        "CloudFront output must expose only the clean HTTPS URL without a bootstrap token",
    )
    require(
        "terraform/lab/provisioning/destroy-lab.ps1" in outputs
        and "JCAREER_SYNTHETIC_LAB_DESTROY_APPROVED" in outputs,
        "Terraform output must direct operators to the guarded destroy wrapper",
    )
    forbid(
        "terraform -chdir=terraform/lab destroy" in outputs,
        "Terraform output exposes an unguarded destroy command",
    )
    require(
        "AWS resource mutation" in readme
        and "Plan-only is not offline" in readme
        and "read-only STS" in readme,
        "README must distinguish disabled AWS mutation from plan-only read calls",
    )
    require("three Windows PCs, three Macs" in readme, "endpoint simulation boundary is missing")

    require(
        "JCAREER_SYNTHETIC_LAB_DESTROY_APPROVED" in destroy_lab
        and "[Parameter(Mandatory = $true)]" in destroy_lab,
        "guarded destroy must require a distinct mandatory acknowledgement",
    )
    require(
        "'plan', '-destroy', '-input=false', '-no-color'" in destroy_lab
        and "tfplan-destroy" in destroy_lab
        and "'apply', '-input=false', '-no-color', $operationPlanRelativePath" in destroy_lab,
        "guarded destroy must create and apply only a saved destroy plan",
    )
    require(
        destroy_lab.count("if ($script:destroySucceeded)") == 2
        and "if ($script:destroyPlanConsumptionStarted -or $script:destroySucceeded)" not in destroy_lab,
        "guarded destroy plan-only must retain reviewed artifacts and failed consumption must retain recovery evidence",
    )
    require(
        "13/14 base-or-Bedrock or 23/24 private-origin HTTPS-preview graph union" in destroy_lab
        and "elseif (Test-ReviewedAddressSubset -Observed $managedState -ReviewedUnion $reviewedAddressUnion)" in destroy_lab
        and "$expectedAddresses = @($managedState)" in destroy_lab
        and "Interrupted-apply recovery mode" in destroy_lab
        and "saved-plan deletes differ" in destroy_lab
        and "managed action other than delete" in destroy_lab,
        "guarded destroy must reject addresses outside the reviewed union and retain exact partial-state recovery",
    )
    require(
        "aws_route_table_association.public" in main
        and "aws_route_table_association.private_preview" in main,
        "runtime bootstrap must wait for both selected route-table associations",
    )
    require(
        "aws_vpc_security_group_egress_rule.internet" in main,
        "runtime bootstrap must wait for the reviewed egress rule",
    )
    require(
        "terraform post-destroy state inventory" in destroy_lab
        and "Terraform state is not empty" in destroy_lab
        and "Remove-KnownArtifact" in destroy_lab
        and "terraform.tfstate.backup" in destroy_lab,
        "guarded destroy must verify state zero and clean known sensitive artifacts",
    )
    forbid("-auto-approve" in destroy_lab, "guarded destroy uses forbidden auto-approve")
    forbid(
        re.search(r"(?:^|[\s'\"])\-target(?:=|[\s'\"])", destroy_lab) is not None,
        "guarded destroy uses forbidden Terraform target",
    )

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
        "lab 정적 경계 · EC2 1대 · 기본 inbound 0 · 조건부 CloudFront TCP/3000 · "
        "Bedrock/OpenDART 기본 비활성 · 승인형 capability broker"
    )
    for warning in warnings:
        print(f"::warning::{warning}")
    for error in errors:
        print(f"::error::{error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
