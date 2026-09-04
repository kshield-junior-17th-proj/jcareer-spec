from __future__ import annotations

import argparse
import re
from pathlib import Path


REL = Path("terraform/tobe-ai-security")


def _read(root: Path, relative: str) -> str:
    path = root / REL / relative
    if not path.is_file():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8")


def _blocks(text: str, header_pattern: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    for match in re.finditer(header_pattern, text):
        start = match.start()
        brace = text.find("{", match.end() - 1)
        if brace < 0:
            continue
        depth = 0
        in_string = False
        escaped = False
        for index in range(brace, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    blocks.append((match.group(0), text[start : index + 1]))
                    break
    return blocks


def validate(root: Path) -> list[str]:
    problems: list[str] = []

    workflow = (root / ".github/workflows/public-release-check.yml").read_text(
        encoding="utf-8"
    )
    root_main = _read(root, "main.tf")
    root_vars = _read(root, "variables.tf")
    versions = _read(root, "versions.tf")
    readme = _read(root, "README.md")
    evidence_map = _read(root, "EVIDENCE_MAP.md")
    validation_doc = _read(root, "VALIDATION.md")
    edge = _read(root, "modules/edge/main.tf")
    edge_vars = _read(root, "modules/edge/variables.tf")
    edge_outputs = _read(root, "modules/edge/outputs.tf")
    bedrock = _read(root, "modules/bedrock-boundary/main.tf")
    bedrock_vars = _read(root, "modules/bedrock-boundary/variables.tf")
    metadata = _read(root, "modules/metadata-observability/main.tf")
    metadata_vars = _read(root, "modules/metadata-observability/variables.tf")

    required_false = (
        'variable "enable"',
        'variable "enable_edge"',
        'variable "enable_bedrock_boundary"',
        'variable "enable_observability"',
        'variable "verify_cloudfront_binding"',
    )
    for variable in required_false:
        source = root_vars if variable in root_vars else edge_vars
        match = re.search(re.escape(variable) + r"\s*\{(?P<body>.*?)\n\}", source, re.S)
        if not match or "default     = false" not in match.group("body"):
            problems.append(f"{variable} must default to false")

    forbidden = (
        "backend \"",
        "terraform_remote_state",
        'resource "aws_wafv2_web_acl_association"',
    )
    all_tf = "\n".join(
        path.read_text(encoding="utf-8") for path in (root / REL).rglob("*.tf")
    )
    for token in forbidden:
        if token in all_tf:
            problems.append(f"forbidden construct present: {token}")

    edge_requirements = (
        'data "aws_cloudfront_distribution" "target"',
        'data.aws_cloudfront_distribution.target[0].status == "Deployed"',
        "data.aws_cloudfront_distribution.target[0].web_acl_id == aws_wafv2_web_acl.edge[0].arn",
        "EDGE-BINDING-",
    )
    for token in edge_requirements:
        if token not in edge + edge_vars + edge_outputs:
            problems.append(f"edge binding contract missing: {token}")

    bedrock_requirements = (
        'resource "aws_iam_policy" "gateway_invoke_broker"',
        'Action   = ["lambda:InvokeFunction"]',
        "Resource = var.broker_function_arn",
        'resource "aws_iam_policy" "gateway_direct_bedrock_deny"',
        "bedrock_invocation_resource_arns",
        "bedrock_approval_binding_sha256 == local.approval_input_sha256",
        'endswith(resource_arn, "/${var.exact_model_id}")',
        '!strcontains(resource_arn, "*")',
        '^arn:(aws|aws-us-gov|aws-cn):bedrock:',
        '^arn:(aws|aws-us-gov|aws-cn):lambda:',
        ':[1-9][0-9]*$',
        '"aws:RequestedRegion"',
        "broker_code_sha256",
        "broker_role_unique_id",
        "gateway_role_unique_id",
        "skip_destroy = true",
    )
    for token in bedrock_requirements:
        if token not in root_main + root_vars + bedrock + bedrock_vars:
            problems.append(f"Bedrock/Gateway/Broker boundary missing: {token}")

    provenance_requirements = (
        'data "aws_lambda_function" "broker_published"',
        "code_sha256 == var.broker_code_sha256",
        'data "aws_iam_role" "broker"',
        'data "aws_iam_role" "gateway"',
        "unique_id == var.broker_role_unique_id",
        "unique_id == var.gateway_role_unique_id",
        "terraform_data.role_provenance_gate",
        "terraform_data.broker_code_provenance_gate",
    )
    for token in provenance_requirements:
        if token not in root_main:
            problems.append(f"workload provenance gate missing: {token}")

    for name in ("broker_exact_model", "gateway_invoke_broker"):
        matches = [
            body
            for header, body in _blocks(
                bedrock, r'resource\s+"aws_iam_policy"\s+"[^"]+"\s*\{'
            )
            if f'"{name}"' in header
        ]
        if len(matches) != 1:
            problems.append(f"unable to isolate {name} policy")
        elif 'Resource = "*"' in matches[0]:
            problems.append(f"allow policy {name} contains wildcard Resource")

    publisher_matches = [
        body
        for header, body in _blocks(
            metadata, r'resource\s+"aws_iam_policy"\s+"[^"]+"\s*\{'
        )
        if '"metadata_publisher"' in header
    ]
    if len(publisher_matches) != 1:
        problems.append("unable to isolate metadata_publisher policy")
    elif 'Resource = "*"' in publisher_matches[0]:
        problems.append("metadata_publisher allow policy contains wildcard Resource")

    metadata_requirements = (
        "kms_key_id        = aws_kms_key.evidence[0].arn",
        'resource "aws_iam_policy" "metadata_publisher"',
        'resource "aws_cloudtrail" "metadata_audit"',
        's3_key_prefix                 = "cloudtrail"',
        'Resource = "${aws_s3_bucket.audit[0].arn}/cloudtrail/AWSLogs/${local.account_id}/*"',
        'type   = "AWS::S3::Object"',
        'type   = "AWS::DynamoDB::Table"',
        "enable_log_file_validation    = true",
        'resource "aws_cloudwatch_metric_alarm" "guardrail_block"',
        "local.publisher_channels",
        "toset(keys(var.publisher_roles)) == toset(keys(local.publisher_channels))",
        'Resource = "${aws_s3_bucket.evidence[0].arn}/${each.value.s3_prefix}/*"',
        '"dynamodb:LeadingKeys" = ["${each.value.dynamodb_prefix}*"]',
        "role       = var.publisher_roles[each.key]",
        's3_prefix        = "records/llm-gateway"',
        's3_prefix        = "records/capability-broker"',
    )
    for token in metadata_requirements:
        if token not in metadata + metadata_vars:
            problems.append(f"metadata/audit boundary missing: {token}")

    cloudtrail_kms_matches = [
        body
        for _header, body in _blocks(
            metadata,
            r'(?=\{\s*Sid\s*=\s*"AllowCloudTrailEncryption")',
        )
    ]
    if len(cloudtrail_kms_matches) != 1:
        problems.append("unable to isolate AllowCloudTrailEncryption statement")
    else:
        for token in (
            '"kms:Decrypt"',
            '"kms:GenerateDataKey*"',
            '"kms:DescribeKey"',
            '"aws:SourceArn"',
            '"kms:EncryptionContext:aws:cloudtrail:arn"',
        ):
            if token not in cloudtrail_kms_matches[0]:
                problems.append(f"CloudTrail S3 Bucket Key KMS grant missing: {token}")

    kms_key_matches = [
        body
        for header, body in _blocks(
            metadata, r'resource\s+"aws_kms_key"\s+"[^\"]+"\s*\{'
        )
        if '"evidence"' in header
    ]
    if len(kms_key_matches) != 1:
        problems.append("unable to isolate shared evidence KMS key")
    elif "prevent_destroy = true" not in kms_key_matches[0]:
        problems.append("shared evidence KMS key must set prevent_destroy = true")

    for path in (root / REL / "modules").rglob("*.tf"):
        text = path.read_text(encoding="utf-8")
        for header, block in _blocks(text, r'resource\s+"aws_[^"]+"\s+"[^"]+"\s*\{'):
            if not re.search(r"\b(count|for_each)\s*=\s*var\.enable", block):
                problems.append(f"ungated AWS resource in {path.relative_to(root)}: {header}")
        for header, block in _blocks(text, r'data\s+"aws_[^"]+"\s+"[^"]+"\s*\{'):
            if not re.search(r"\bcount\s*=\s*var\.enable", block):
                problems.append(f"ungated AWS data read in {path.relative_to(root)}: {header}")

    for module_name in ("edge", "bedrock-boundary", "metadata-observability"):
        child_versions = _read(root, f"modules/{module_name}/versions.tf")
        if 'source  = "hashicorp/aws"' not in child_versions:
            problems.append(f"{module_name} does not declare the AWS provider source")
        if 'version = "= 6.59.0"' not in child_versions:
            problems.append(f"{module_name} does not pin AWS provider 6.59.0")

    boundary_phrases = (
        "PROPOSED / NOT DEPLOYED / HUMAN REVIEW PENDING",
        "owner stack",
        "bedrock_approval_binding_sha256",
        "Local preparation performed `terraform init -backend=false`",
        "without a provider download",
        "clean Ubuntu runner may download the pinned",
        "performs no AWS API call or",
        "numeric published Broker Lambda version ARN",
        "role names, ARNs, unique IDs",
        "The shared KMS key has `prevent_destroy=true`",
        "registry-generated lock selection",
        "guard-content input-tag contract",
        "HCL can neither inspect the request body nor prove",
        "actual plan/apply is blocked until a",
        "status=PROPOSED_CONTROL_NOT_VERIFIED",
    )
    for phrase in boundary_phrases:
        if phrase not in readme:
            problems.append(f"README boundary missing: {phrase}")

    for finding in ("NF-02", "NF-03", "NF-04", "NF-05", "NF-06"):
        if finding not in evidence_map:
            problems.append(f"evidence map missing {finding}")
    for phrase in (
        "Prohibited claim",
        "not NIST AI RMF",
        "current proof",
        "guard-content input-tag request contract",
        "reviewed committed multi-platform",
    ):
        if phrase not in evidence_map:
            problems.append(f"evidence map boundary missing: {phrase}")

    if versions.count('status      = "PROPOSED_CONTROL_NOT_VERIFIED"') != 2:
        problems.append("both provider default tags must mark controls not verified")
    for module_name, source in (
        ("edge", edge),
        ("bedrock-boundary", bedrock),
        ("metadata-observability", metadata),
    ):
        if 'status      = "PROPOSED_CONTROL_NOT_VERIFIED"' not in source:
            problems.append(f"{module_name} resource tags must mark controls not verified")
        if 'status      = "PROPOSED_NOT_DEPLOYED"' in source:
            problems.append(f"{module_name} resource tags retain a not-deployed status")
    if 'status      = "PROPOSED_NOT_DEPLOYED"' in versions:
        problems.append("provider defaults retain a not-deployed status on created resources")
    if 'skip_credentials_validation = !var.enable' not in versions:
        problems.append("disabled provider must skip credential validation")

    for phrase in (
        "guard-content input tag",
        "reject missing/malformed tags",
        "actual plan/apply remains blocked",
        "not operating-effectiveness evidence",
    ):
        if phrase not in validation_doc:
            problems.append(f"validation live gate missing: {phrase}")

    workflow_requirements = (
        "hashicorp/setup-terraform@dfe3c3f87815947d99a8997f908cb6525fc44e9e",
        "terraform fmt -check -recursive terraform/tobe-ai-security",
        "scripts/check_tobe_ai_security_static.py --root .",
        'tobe_ci_root="$RUNNER_TEMP/jcareer-tobe-check"',
        'cp -R terraform/tobe-ai-security "$tobe_ci_root/terraform/tobe-ai-security"',
        'terraform -chdir="$tobe_ci_root/terraform/tobe-ai-security" init -backend=false -input=false',
        'scripts/check_tobe_provider_lock.py --root "$tobe_ci_root"',
        'terraform -chdir="$tobe_ci_root/terraform/tobe-ai-security" validate',
        'terraform -chdir="$tobe_ci_root/terraform/tobe-ai-security" test',
    )
    for command in workflow_requirements:
        if command not in workflow:
            problems.append(f"CI verification missing: {command}")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    problems = validate(args.root.resolve())
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}")
        return 1
    print("TO-BE AI security static contract PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
