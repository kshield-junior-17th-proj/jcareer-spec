#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_lab_static", ROOT / "scripts" / "check_lab_static.py"
)
assert SPEC and SPEC.loader
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)
BUDGET_SPEC = importlib.util.spec_from_file_location(
    "check_lab_budget", ROOT / "scripts" / "check_lab_budget.py"
)
assert BUDGET_SPEC and BUDGET_SPEC.loader
BUDGET_CHECKER = importlib.util.module_from_spec(BUDGET_SPEC)
BUDGET_SPEC.loader.exec_module(BUDGET_CHECKER)


def https_configuration_plan() -> dict[str, object]:
    requirements = {
        ("aws_vpc_security_group_ingress_rule.cloudfront_preview", ("security_group_id",)):
            ["aws_security_group.runtime.id"],
        ("aws_vpc_security_group_ingress_rule.cloudfront_preview", ("referenced_security_group_id",)):
            ["data.aws_security_group.cloudfront_vpc_origin_service[0].id"],
        ("aws_nat_gateway.preview", ("allocation_id",)): ["aws_eip.preview_nat[0].id"],
        ("aws_nat_gateway.preview", ("subnet_id",)): ["aws_subnet.public.id"],
        ("aws_route.private_preview_internet", ("route_table_id",)):
            ["aws_route_table.private_preview[0].id"],
        ("aws_route.private_preview_internet", ("nat_gateway_id",)):
            ["aws_nat_gateway.preview[0].id"],
        ("aws_route_table_association.private_preview", ("subnet_id",)):
            ["aws_subnet.private_preview[0].id"],
        ("aws_route_table_association.private_preview", ("route_table_id",)):
            ["aws_route_table.private_preview[0].id"],
        ("aws_instance.runtime", ("subnet_id",)): [
            "var.enable_aws_https_preview",
            "aws_subnet.private_preview[0].id",
            "aws_subnet.public.id",
        ],
        ("aws_instance.runtime", ("vpc_security_group_ids",)):
            ["aws_security_group.runtime.id"],
        ("aws_cloudfront_vpc_origin.preview", ("vpc_origin_endpoint_config", 0, "arn")):
            ["aws_instance.runtime.arn"],
        ("aws_cloudfront_distribution.preview", ("origin", 0, "domain_name")):
            ["aws_instance.runtime.private_dns"],
        ("aws_cloudfront_distribution.preview", ("origin", 0, "vpc_origin_config", 0, "vpc_origin_id")):
            ["aws_cloudfront_vpc_origin.preview[0].id"],
        ("aws_cloudfront_distribution.preview", ("default_cache_behavior", 0, "function_association", 0, "function_arn")):
            ["aws_cloudfront_function.preview_gate[0].arn"],
    }
    resources: dict[str, dict[str, object]] = {}
    for (address, path), references in requirements.items():
        resource = resources.setdefault(address, {"address": address, "expressions": {}})
        prefixes: list[str] = []
        for reference in references:
            prefixes.append(reference)
            if reference.endswith((".id", ".arn", ".private_dns")):
                without_attribute = reference.rsplit(".", 1)[0]
                prefixes.append(without_attribute)
                if without_attribute.endswith("[0]"):
                    prefixes.append(without_attribute[:-3])
        node: object = resource["expressions"]  # type: ignore[index]
        for index, component in enumerate(path):
            final = index == len(path) - 1
            if isinstance(component, str):
                assert isinstance(node, dict)
                if final:
                    node[component] = {"references": prefixes}
                else:
                    next_component = path[index + 1]
                    node = node.setdefault(component, [] if isinstance(next_component, int) else {})
            else:
                assert isinstance(node, list)
                while len(node) <= component:
                    node.append({})
                node = node[component]
    return {
        "configuration": {
            "root_module": {"resources": list(resources.values())}
        }
    }


class LabStaticBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = CHECKER.load_sources(ROOT)

    def assert_mutation_rejected(
        self, key: str, old: str, new: str, expected_error: str
    ) -> None:
        mutated = dict(self.sources)
        self.assertIn(old, mutated[key])
        mutated[key] = mutated[key].replace(old, new, 1)
        errors = CHECKER.audit_sources(mutated)
        self.assertTrue(
            any(expected_error in error for error in errors),
            f"expected {expected_error!r} in {errors!r}",
        )

    def test_current_sources_match_static_boundary(self) -> None:
        self.assertEqual(CHECKER.audit_sources(self.sources), [])

    def test_any_main_source_drift_requires_digest_review(self) -> None:
        mutated = dict(self.sources)
        mutated["main"] = mutated["main"].replace(
            'Project    = "jcareer"', 'Project    = "jcareer-drift"', 1
        )
        self.assertIn(
            "terraform/lab/main.tf differs from the reviewed exact source digest",
            CHECKER.audit_sources(mutated),
        )

    def test_lab_provider_lockfile_drift_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "lab_lockfile",
            'constraints = "6.59.0"',
            'constraints = ">= 6.59.0"',
            "terraform/lab AWS provider lockfile is missing or differs from the pinned provider",
        )

    def test_https_plan_configuration_bindings_are_exact(self) -> None:
        plan = https_configuration_plan()
        self.assertEqual(BUDGET_CHECKER.audit_https_configuration_bindings(plan), [])
        resources = plan["configuration"]["root_module"]["resources"]  # type: ignore[index]
        ingress = next(
            item for item in resources
            if item["address"] == "aws_vpc_security_group_ingress_rule.cloudfront_preview"
        )
        ingress["expressions"]["referenced_security_group_id"] = {  # type: ignore[index]
            "references": ["aws_security_group.unreviewed.id"]
        }
        errors = BUDGET_CHECKER.audit_https_configuration_bindings(plan)
        self.assertTrue(any("referenced_security_group_id" in error for error in errors))

    def test_https_plan_configuration_rejects_unrelated_terminal_reference(self) -> None:
        plan = https_configuration_plan()
        resources = plan["configuration"]["root_module"]["resources"]  # type: ignore[index]
        route = next(
            item for item in resources
            if item["address"] == "aws_route.private_preview_internet"
        )
        route["expressions"]["nat_gateway_id"]["references"].append(  # type: ignore[index]
            "aws_nat_gateway.unreviewed[0].id"
        )
        errors = BUDGET_CHECKER.audit_https_configuration_bindings(plan)
        self.assertTrue(any("nat_gateway_id" in error for error in errors))

    def test_https_plan_configuration_rejects_nested_origin_drift(self) -> None:
        plan = https_configuration_plan()
        resources = plan["configuration"]["root_module"]["resources"]  # type: ignore[index]
        distribution = next(
            item for item in resources
            if item["address"] == "aws_cloudfront_distribution.preview"
        )
        distribution["expressions"]["origin"][0]["domain_name"] = {  # type: ignore[index]
            "references": ["aws_instance.unreviewed.private_dns"]
        }
        errors = BUDGET_CHECKER.audit_https_configuration_bindings(plan)
        self.assertTrue(any("origin.[0].domain_name" in error for error in errors))

    def test_public_cidr_ingress_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "main",
            "referenced_security_group_id = (",
            'cidr_ipv4         = "0.0.0.0/0"',
            "HTTPS preview ingress must not use a public CIDR",
        )

    def test_https_private_subnet_or_nat_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "main",
            'map_public_ip_on_launch = false',
            'map_public_ip_on_launch = true',
            "HTTPS preview origin must move to a private subnet",
        )

    def test_https_subnet_condition_reversal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "main",
            """subnet_id = var.enable_aws_https_preview ? (
    aws_subnet.private_preview[0].id
  ) : aws_subnet.public.id""",
            """subnet_id = var.enable_aws_https_preview ? (
    aws_subnet.public.id
  ) : aws_subnet.private_preview[0].id""",
            "HTTPS subnet condition must map true to private and false to public",
        )

    def test_https_subnet_condition_comment_decoy_is_rejected(self) -> None:
        mutated = dict(self.sources)
        reviewed = """subnet_id = var.enable_aws_https_preview ? (
    aws_subnet.private_preview[0].id
  ) : aws_subnet.public.id"""
        reversed_expression = """subnet_id = var.enable_aws_https_preview ? (
    aws_subnet.public.id
  ) : aws_subnet.private_preview[0].id"""
        self.assertIn(reviewed, mutated["main"])
        mutated["main"] = (
            mutated["main"].replace(reviewed, reversed_expression, 1)
            + "\n/* decoy only:\n"
            + reviewed
            + "\n*/\n"
        )
        self.assertIn(
            "HTTPS subnet condition must map true to private and false to public",
            CHECKER.audit_sources(mutated),
        )

    def test_heredoc_quote_cannot_poison_following_comment_decoy(self) -> None:
        mutated = dict(self.sources)
        reviewed = """subnet_id = var.enable_aws_https_preview ? (
    aws_subnet.private_preview[0].id
  ) : aws_subnet.public.id"""
        reversed_expression = """subnet_id = var.enable_aws_https_preview ? (
    aws_subnet.public.id
  ) : aws_subnet.private_preview[0].id"""
        poisoned = """user_data = <<-PAYLOAD
"
PAYLOAD
  """ + reversed_expression + """
  /* subnet_id = var.enable_aws_https_preview ? (
    aws_subnet.private_preview[0].id
  ) : aws_subnet.public.id */"""
        self.assertIn(reviewed, mutated["main"])
        mutated["main"] = mutated["main"].replace(reviewed, poisoned, 1)
        self.assertIn(
            "HTTPS subnet condition must map true to private and false to public",
            CHECKER.audit_sources(mutated),
        )

    def test_comment_token_inside_heredoc_does_not_hide_following_hcl(self) -> None:
        source = """resource \"aws_instance\" \"runtime\" {
  user_data = <<PAYLOAD
/* heredoc data, deliberately unmatched
PAYLOAD
  subnet_id = var.enable_aws_https_preview ? (
    aws_subnet.private_preview[0].id
  ) : aws_subnet.public.id
}
"""
        block = CHECKER._extract_hcl_block(
            source, r'resource\s+"aws_instance"\s+"runtime"'
        )
        self.assertIn("subnet_id = var.enable_aws_https_preview", block)

    def test_quoted_heredoc_token_is_not_a_heredoc_start(self) -> None:
        source = """resource \"aws_instance\" \"runtime\" {
  tags = { Note = \"literal <<TOKEN only\" }
  subnet_id = var.enable_aws_https_preview ? (
    aws_subnet.private_preview[0].id
  ) : aws_subnet.public.id
}
"""
        block = CHECKER._extract_hcl_block(
            source, r'resource\s+"aws_instance"\s+"runtime"'
        )
        self.assertIn("literal <<TOKEN only", block)
        self.assertIn("subnet_id = var.enable_aws_https_preview", block)

    def test_quoted_subnet_decoy_cannot_hide_reversed_attribute(self) -> None:
        mutated = dict(self.sources)
        reviewed = """subnet_id = var.enable_aws_https_preview ? (
    aws_subnet.private_preview[0].id
  ) : aws_subnet.public.id"""
        reversed_expression = """subnet_id = var.enable_aws_https_preview ? (
    aws_subnet.public.id
  ) : aws_subnet.private_preview[0].id"""
        decoy = reviewed.replace("\n", " ")
        poisoned = reversed_expression + f'\n  tags = {{ ParserDecoy = "{decoy}" }}'
        self.assertIn(reviewed, mutated["main"])
        mutated["main"] = mutated["main"].replace(reviewed, poisoned, 1)
        self.assertIn(
            "HTTPS subnet condition must map true to private and false to public",
            CHECKER.audit_sources(mutated),
        )

    def test_hyphenated_heredoc_delimiter_is_recognized(self) -> None:
        source = """resource \"aws_instance\" \"runtime\" {
  user_data = <<-END-DATA
{ \"body\": \"data only\" }
END-DATA
  subnet_id = var.enable_aws_https_preview ? (
    aws_subnet.private_preview[0].id
  ) : aws_subnet.public.id
}
"""
        block = CHECKER._extract_hcl_block(
            source, r'resource\s+"aws_instance"\s+"runtime"'
        )
        self.assertIn("subnet_id = var.enable_aws_https_preview", block)

    def test_nested_expression_decoy_cannot_hide_reversed_attribute(self) -> None:
        mutated = dict(self.sources)
        reviewed = """subnet_id = var.enable_aws_https_preview ? (
    aws_subnet.private_preview[0].id
  ) : aws_subnet.public.id"""
        reversed_expression = """subnet_id = var.enable_aws_https_preview ? (
    aws_subnet.public.id
  ) : aws_subnet.private_preview[0].id"""
        nested_decoy = reviewed.replace("\n", " ")
        poisoned = (
            reversed_expression
            + "\n  tags = { ParserDecoy = jsonencode({ "
            + nested_decoy
            + " }) }"
        )
        self.assertIn(reviewed, mutated["main"])
        mutated["main"] = mutated["main"].replace(reviewed, poisoned, 1)
        self.assertIn(
            "HTTPS subnet condition must map true to private and false to public",
            CHECKER.audit_sources(mutated),
        )

    def test_template_interpolation_cannot_truncate_runtime_block(self) -> None:
        mutated = dict(self.sources)
        reviewed = """subnet_id = var.enable_aws_https_preview ? (
    aws_subnet.private_preview[0].id
  ) : aws_subnet.public.id"""
        reversed_expression = """subnet_id = var.enable_aws_https_preview ? (
    aws_subnet.public.id
  ) : aws_subnet.private_preview[0].id"""
        nested_decoy = reviewed.replace("\n", " ")
        poisoned = (
            "tags = {\n"
            + "    subnet_id = "
            + nested_decoy.removeprefix("subnet_id = ")
            + "\n"
            + '    Note = "${tostring("}")}"\n'
            + "  }\n  "
            + reversed_expression
        )
        self.assertIn(reviewed, mutated["main"])
        mutated["main"] = mutated["main"].replace(reviewed, poisoned, 1)
        block = CHECKER._extract_hcl_block(
            mutated["main"], r'resource\s+"aws_instance"\s+"runtime"'
        )
        self.assertIn(reversed_expression, block)
        self.assertIn(
            "HTTPS subnet condition must map true to private and false to public",
            CHECKER.audit_sources(mutated),
        )

    def test_multiline_block_comment_cannot_fake_attribute_end(self) -> None:
        mutated = dict(self.sources)
        reviewed = """subnet_id = var.enable_aws_https_preview ? (
    aws_subnet.private_preview[0].id
  ) : aws_subnet.public.id"""
        continued = reviewed + """ /*
*/ == aws_subnet.public.id ? \"subnet-00000000\" : aws_subnet.public.id"""
        self.assertIn(reviewed, mutated["main"])
        mutated["main"] = mutated["main"].replace(reviewed, continued, 1)
        self.assertIn(
            "HTTPS subnet condition must map true to private and false to public",
            CHECKER.audit_sources(mutated),
        )

    def test_cloudfront_planned_topology_rejects_extra_or_retargeted_origin(self) -> None:
        reviewed = {
            "origin": [{
                "origin_id": "jcareer-runtime-vpc-origin",
                "vpc_origin_config": [{"vpc_origin_id": "pending"}],
            }],
            "default_cache_behavior": [{
                "target_origin_id": "jcareer-runtime-vpc-origin",
            }],
        }
        self.assertEqual(
            BUDGET_CHECKER.audit_cloudfront_planned_topology(
                "aws_cloudfront_distribution.preview[0]", reviewed
            ),
            [],
        )
        extra = json.loads(json.dumps(reviewed))
        extra["origin"].append({
            "origin_id": "alternate",
            "custom_origin_config": [{"http_port": 80}],
        })
        self.assertTrue(BUDGET_CHECKER.audit_cloudfront_planned_topology(
            "aws_cloudfront_distribution.preview[0]", extra
        ))
        retargeted = json.loads(json.dumps(reviewed))
        retargeted["default_cache_behavior"][0]["target_origin_id"] = "alternate"
        self.assertTrue(any(
            "retargeted" in error
            for error in BUDGET_CHECKER.audit_cloudfront_planned_topology(
                "aws_cloudfront_distribution.preview[0]", retargeted
            )
        ))
        self.assert_mutation_rejected(
            "main",
            'nat_gateway_id         = aws_nat_gateway.preview[0].id',
            'gateway_id             = aws_internet_gateway.lab.id',
            "HTTPS preview origin must move to a private subnet",
        )

    def test_unexpected_terraform_file_is_rejected(self) -> None:
        mutated = dict(self.sources)
        mutated["terraform_file_names"] += "\nbackdoor.tf"
        self.assertIn(
            "terraform/lab contains an unexpected or missing top-level .tf file",
            CHECKER.audit_sources(mutated),
        )

    def test_unreviewed_resource_type_is_rejected(self) -> None:
        mutated = dict(self.sources)
        mutated["terraform_all"] += '\nresource "aws_lambda_function" "bad" {}\n'
        self.assertIn(
            "terraform/lab resource blocks differ from the reviewed exact source inventory",
            CHECKER.audit_sources(mutated),
        )

    def test_bedrock_default_true_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "variables",
            'variable "enable_bedrock_live" {\n  description = "lab instance role에 Bedrock 호출 권한을 추가할지 여부. 기본값은 false다."\n  type        = bool\n  default     = false',
            'variable "enable_bedrock_live" {\n  description = "lab instance role에 Bedrock 호출 권한을 추가할지 여부. 기본값은 false다."\n  type        = bool\n  default     = true',
            "Bedrock plan flag must default to false",
        )

    def test_unconditional_all_interface_web_binding_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy",
            "$webBindAddress = if ($EnableAwsHttpsPreview) { '0.0.0.0' } else { '127.0.0.1' }",
            "$webBindAddress = '0.0.0.0'",
            "remote web binding must be conditional",
        )

    def test_preview_default_true_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "variables",
            'variable "enable_aws_https_preview" {\n  description = "CloudFront HTTPS를 통한 단기 합성 프리뷰 활성화 여부. 기본값은 false다."\n  type        = bool\n  default     = false',
            'variable "enable_aws_https_preview" {\n  description = "CloudFront HTTPS를 통한 단기 합성 프리뷰 활성화 여부. 기본값은 false다."\n  type        = bool\n  default     = true',
            "AWS HTTPS preview must default to disabled",
        )

    def test_preview_secure_cookie_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "preview_gate",
            "delete request.cookies[cookieName]",
            "request.cookies[cookieName] = previewCookie",
            "preview edge function must hash",
        )

    def test_raw_preview_token_terraform_variable_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "variables",
            'variable "preview_access_token_sha256"',
            'variable "preview_access_token"',
            "raw preview token must not enter Terraform",
        )

    def test_preview_token_hashing_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "preview_gate",
            'crypto.createHash("sha256")',
            'crypto.createHash("md5")',
            "preview edge function must hash",
        )

    def test_preview_digest_replay_cookie_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "preview_gate",
            "value: bootstrap.value",
            "value: accessTokenSha256",
            "without accepting the stored digest as a bearer",
        )

    def test_preview_referrer_policy_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "preview_gate",
            '"referrer-policy": { value: "no-referrer" },',
            "",
            "without accepting the stored digest as a bearer",
        )

    def test_hashed_viewer_key_is_not_forwarded_as_ip(self) -> None:
        self.assert_mutation_rejected(
            "nginx",
            "proxy_set_header X-Forwarded-For $remote_addr;",
            "proxy_set_header X-Forwarded-For $jcareer_rate_key;",
            "must not place the hashed rate-limit key in X-Forwarded-For",
        )

    def test_preview_custom_header_overwrite_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "preview_gate",
            'request.headers["x-jcareer-viewer-key"]',
            'request.headers["x-untrusted-viewer-key"]',
            "preview edge function must overwrite custom header x-jcareer-viewer-key",
        )

    def test_preview_tls_floor_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "main",
            'minimum_protocol_version       = "TLSv1.2_2021"',
            'minimum_protocol_version       = "TLSv1"',
            "CloudFront TLS, no-cache",
        )

    def test_public_ip_output_is_rejected(self) -> None:
        mutated = dict(self.sources)
        mutated["outputs"] += "\noutput \"bad\" { value = aws_instance.runtime.public_ip }\n"
        self.assertIn("public IP is exposed as an output", CHECKER.audit_sources(mutated))

    def test_activation_precondition_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "main",
            'var.activation_acknowledgement == "JCAREER_SYNTHETIC_LAB_APPROVED"',
            "true",
            "Terraform activation precondition is missing",
        )

    def test_user_data_replacement_guard_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "main",
            "ignore_changes = [user_data]",
            "ignore_changes = []",
            "healthy lab host must not be replaced",
        )

    def test_auto_stop_output_does_not_claim_existing_timer_observation(self) -> None:
        self.assert_mutation_rejected(
            "outputs",
            "기존 인스턴스의 user_data 변경은 무시되므로 실제 타이머 관찰값이 아니다",
            "EC2가 OS shutdown으로 자동 중지되는 기동 후 시간",
            "auto-stop output must not claim an unobserved existing-instance timer",
        )

    def test_archive_integrity_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy",
            "$archiveSha256 = (Get-FileHash",
            "$archiveSha256 = (Removed-HashCommand",
            "runtime archive integrity check is missing",
        )

    def test_bootstrap_fail_safe_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "user_data",
            "trap fail_safe_stop ERR",
            "trap - ERR",
            "bootstrap failure must request an immediate stop",
        )

    def test_bootstrap_fail_safe_must_precede_unit_writes(self) -> None:
        mutated = dict(self.sources)
        mutated["user_data"] = mutated["user_data"].replace(
            "trap fail_safe_stop ERR\n", "", 1
        ).replace(
            "systemctl enable --now jcareer-lab-auto-stop.timer",
            "systemctl enable --now jcareer-lab-auto-stop.timer\ntrap fail_safe_stop ERR",
            1,
        )
        self.assertIn(
            "bootstrap failure trap must be armed before timer installation and package/network operations",
            CHECKER.audit_sources(mutated),
        )

    def test_bootstrap_direct_shutdown_fallback_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "user_data",
            "systemctl start --no-block jcareer-lab-auto-stop.service || /sbin/shutdown -h now",
            "systemctl start --no-block jcareer-lab-auto-stop.service",
            "bootstrap failure must request an immediate stop",
        )

    def test_bootstrap_trap_cannot_clear_before_readiness(self) -> None:
        mutated = dict(self.sources)
        mutated["user_data"] = mutated["user_data"].replace(
            "touch /var/lib/jcareer-lab/bootstrap-ready\ntrap - ERR",
            "trap - ERR\ntouch /var/lib/jcareer-lab/bootstrap-ready",
            1,
        )
        self.assertIn(
            "bootstrap failure trap must remain armed until the readiness marker is written",
            CHECKER.audit_sources(mutated),
        )

    def test_bootstrap_buildx_checksum_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "user_data",
            'buildx_sha256="48af8a397ebd60178778bf63611dbcebe5f5e7a9be90eb9147b24b9587455778"',
            'buildx_sha256=""',
            "bootstrap must install the checksum-pinned Docker Buildx plugin",
        )

    def test_bootstrap_buildx_shell_expansion_must_escape_terraform(self) -> None:
        self.assert_mutation_rejected(
            "user_data",
            'docker buildx version | grep -F "$${buildx_version#v}"',
            'docker buildx version | grep -F "${buildx_version#v}"',
            "bootstrap must install the checksum-pinned Docker Buildx plugin",
        )

    def test_deploy_buildx_repair_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy",
            "Install checksum-pinned Docker Buildx",
            "Inspect Docker Buildx",
            "deployment must repair and verify the checksum-pinned Docker Buildx plugin",
        )

    def test_deploy_diagnostic_redaction_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy",
            "[REDACTED_ACCOUNT]",
            "[RAW_ACCOUNT]",
            "deployment diagnostics must redact AWS account and resource identifiers",
        )

    def test_https_preview_redaction_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "destroy_lab",
            "[REDACTED_CLOUDFRONT_DOMAIN]",
            "[RAW_CLOUDFRONT_DOMAIN]",
            "guarded destroy diagnostics must cover HTTPS-preview resource and network identifiers",
        )

    def test_native_application_binding_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy_lab",
            "-CommandType Application",
            "-CommandType Function",
            "one-command deploy must bind native tools to Application-type absolute paths",
        )

    def test_preview_browser_module_binding_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy_lab",
            "Microsoft.PowerShell.Management\\Start-Process $bootstrapUrl",
            "Start-Process $bootstrapUrl",
            "one-command deployment must bind preview-token consumers to native or module-qualified commands",
        )

    def test_one_command_deploy_order_change_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy_lab",
            "scripts/check_lab_budget.py",
            "scripts/removed_budget_guard.py",
            "one-command deployment must preserve static-test-plan-budget-apply-runtime order",
        )

    def test_one_command_deploy_delete_guard_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy_lab",
            ".Contains('delete')",
            ".Contains('never-delete')",
            "one-command deployment must block deletes and replacements",
        )

    def test_one_command_deploy_runtime_skip_is_rejected(self) -> None:
        mutated = dict(self.sources)
        mutated["deploy_lab"] += "\n# $edgeGateOnlyUpdate\n"
        self.assertIn(
            "one-command deployment must not skip runtime checks for an edge-token-only update",
            CHECKER.audit_sources(mutated),
        )

    def test_provider_account_apply_recheck_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy_lab",
            "apply completion recording",
            "unchecked apply completion",
            "one-command deployment must bind plan and apply/destroy observations to one non-placeholder provider account digest",
        )

    def test_reviewed_plan_semantic_binding_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy_lab",
            "The retained saved plan does not match the human-reviewed semantic plan digest",
            "semantic plan review was skipped",
            "one-command deployment must bind apply to the human-reviewed timestamp-free semantic plan digest",
        )

    def test_destroy_plan_semantic_binding_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "destroy_lab",
            "The retained destroy plan does not match the human-reviewed semantic plan digest",
            "The retained destroy plan semantic review was skipped",
            "guarded destroy must bind apply to the human-reviewed timestamp-free semantic plan digest",
        )

    def test_deploy_exact_saved_plan_digest_comparison_is_required(self) -> None:
        self.assert_mutation_rejected(
            "deploy_lab",
            "$validatedPlanSha256,\n            $ReviewedSavedPlanSha256,",
            "$validatedPlanSha256,\n            $validatedPlanSha256,",
            "one-command deployment must mutex-serialize, exactly hash-bind, and durably consume the reviewed binary plan without re-planning on apply",
        )

    def test_destroy_exact_saved_plan_digest_comparison_is_required(self) -> None:
        self.assert_mutation_rejected(
            "destroy_lab",
            "$validatedPlanSha256,\n            $ReviewedSavedPlanSha256,",
            "$validatedPlanSha256,\n            $validatedPlanSha256,",
            "guarded destroy must mutex-serialize, exactly hash-bind, and durably consume the reviewed binary plan without re-planning on apply",
        )

    def test_apply_must_not_replan_instead_of_loading_reviewed_binary(self) -> None:
        self.assert_mutation_rejected(
            "deploy_lab",
            "no re-plan is performed",
            "a new plan is created",
            "one-command deployment must mutex-serialize, exactly hash-bind, and durably consume the reviewed binary plan without re-planning on apply",
        )

    def test_plan_bearing_runtime_intent_removal_is_rejected(self) -> None:
        intent_start = self.sources["deploy_lab"].index("function Assert-PlanRuntimeIntent")
        intent_end = self.sources["deploy_lab"].index(
            "function Get-ObservedProviderAccountSha256", intent_start
        )
        mutated = dict(self.sources)
        prefix = mutated["deploy_lab"][:intent_start]
        intent = mutated["deploy_lab"][intent_start:intent_end].replace(
            "preview_access_token_sha256", "unbound_preview_token_digest", 1
        )
        mutated["deploy_lab"] = prefix + intent + mutated["deploy_lab"][intent_end:]
        self.assertIn(
            "one-command deployment must bind Terraform-bearing runtime intent to the reviewed saved plan",
            CHECKER.audit_sources(mutated),
        )

    def test_https_preview_repeated_character_token_guard_is_required(self) -> None:
        self.assert_mutation_rejected(
            "deploy_lab",
            "if ($script:previewToken -match '^([0-9a-f])\\1{63}$')",
            "if ($false)",
            "HTTPS preview bootstrap token must reject obvious repeated-character placeholders",
        )

    def test_https_preview_low_period_token_guard_is_required(self) -> None:
        self.assert_mutation_rejected(
            "deploy_lab",
            "@(1..32)",
            "@(1)",
            "HTTPS preview bootstrap token must reject low-diversity and periodic placeholders",
        )

    def test_https_preview_period_nine_is_inside_guarded_range(self) -> None:
        self.assert_mutation_rejected(
            "deploy_lab",
            "@(1..32)",
            "@(1..8 + 10..32)",
            "HTTPS preview bootstrap token must reject low-diversity and periodic placeholders",
        )

    def test_apply_branch_extra_replan_is_rejected(self) -> None:
        mutated = dict(self.sources)
        insertion = "\n    # injected unsafe branch\n    $null = @('plan', '-input=false', '-no-color')\n"
        marker = "Write-Host '[6/9] Applying only the checked saved plan...'"
        mutated["deploy_lab"] = mutated["deploy_lab"].replace(marker, marker + insertion, 1)
        self.assertIn(
            "one-command deployment must mutex-serialize, exactly hash-bind, and durably consume the reviewed binary plan without re-planning on apply",
            CHECKER.audit_sources(mutated),
        )

    def test_plan_consumption_mutex_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy_lab",
            "[Threading.Mutex]::new",
            "[Threading.Semaphore]::new",
            "one-command deployment must mutex-serialize, exactly hash-bind, and durably consume the reviewed binary plan without re-planning on apply",
        )

    def test_plan_consumption_same_worktree_file_lock_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy_lab",
            "jcareer-lab-plan-operation.lock",
            "jcareer-lab-plan-operation.unlocked",
            "one-command deployment must mutex-serialize, exactly hash-bind, and durably consume the reviewed binary plan without re-planning on apply",
        )

    def test_plan_consumption_lock_must_precede_provider_and_terraform_preflight(self) -> None:
        self.assert_mutation_rejected(
            "deploy_lab",
            "    Assert-NoPendingLabPlanConsumption\n\n    Write-Host '[1/9]",
            "    Write-Host '[1/9]",
            "one-command deployment must mutex-serialize, exactly hash-bind, and durably consume the reviewed binary plan without re-planning on apply",
        )

    def test_destroy_plan_only_must_retain_reviewed_artifacts(self) -> None:
        self.assert_mutation_rejected(
            "destroy_lab",
            "if ($script:destroySucceeded)",
            "if ($true)",
            "guarded destroy plan-only must retain reviewed artifacts and failed consumption must retain recovery evidence",
        )

    def test_provider_account_destroy_recheck_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "destroy_lab",
            "destroy completion recording",
            "unchecked destroy completion",
            "guarded destroy must bind plan and apply/destroy observations to one non-placeholder provider account digest",
        )

    def test_one_command_deploy_auto_approve_is_rejected(self) -> None:
        mutated = dict(self.sources)
        mutated["deploy_lab"] += "\n# terraform apply -auto-approve\n"
        self.assertIn(
            "one-command deployment uses forbidden auto-approve",
            CHECKER.audit_sources(mutated),
        )

    def test_deploy_failure_stop_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy",
            "'ec2', 'stop-instances'",
            "'ec2', 'describe-instances'",
            "deployment failure must stop only a preflight-validated target",
        )

    def test_deploy_stop_target_must_precede_linked_provider_checks(self) -> None:
        self.assert_mutation_rejected(
            "deploy",
            "$script:validatedTarget = $true",
            "$script:validatedTarget = $false",
            "deployment must establish the bounded stop target before ingress and OpenDART checks",
        )

    def test_lab_init_lockfile_readonly_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy_lab",
            "'-lockfile=readonly'",
            "'-lockfile=update'",
            "lab and linked OpenDART Terraform init must use the reviewed provider lockfiles read-only",
        )

    def test_saved_plan_read_lock_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy_lab",
            "[IO.FileShare]::Read",
            "[IO.FileShare]::ReadWrite",
            "one-command deployment must read-lock and re-hash the saved plan and checked JSON through apply",
        )

    def test_post_apply_fail_safe_stop_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy_lab",
            "Post-apply lab verification failed; requesting a fail-safe stop",
            "Post-apply lab verification failed",
            "one-command post-apply failures must stop the validated runtime and preserve explicit destroy approval",
        )

    def test_deploy_profile_name_binding_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy",
            "$profileName -ne $instanceName",
            "$profileName -ne $profileName",
            "deployment must bind the target instance to its reviewed runtime profile name",
        )

    def test_opendart_policy_role_binding_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy",
            "-ExpectedApiRoleName $script:labRoleName",
            "-ExpectedApiRoleName 'unbound-role'",
            "deployment must consume the approved OpenDART state and separated capability brokers",
        )

    def test_opendart_name_boundary_drift_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy",
            "[a-z0-9][a-z0-9_-]{2,74}",
            "[A-Za-z0-9_-]{1,75}",
            "OpenDART deployment preflight and broker name allowlists must remain identical",
        )

    def test_opendart_table_name_boundary_drift_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy",
            "[a-z0-9][a-z0-9_.-]{2,79}",
            "[A-Za-z0-9_.-]{2,254}",
            "OpenDART deployment preflight and broker name allowlists must remain identical",
        )

    def test_opendart_clean_state_staging_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "readme",
            "Clean-state OpenDART staging",
            "OpenDART notes",
            "clean-state OpenDART staging and reverse-order teardown are not documented",
        )

    def test_opendart_stage_order_drift_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "readme",
            "2. **Stage B",
            "4. **Stage B",
            "clean-state OpenDART staging and reverse-order teardown are not documented",
        )

    def test_opendart_publisher_review_step_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "readme",
            "Invoke-ApprovedOpenDartWorkerPublish.ps1 -Mode Review",
            "Invoke-ApprovedOpenDartWorkerPublish.ps1 -Mode Inspect",
            "clean-state OpenDART staging and reverse-order teardown are not documented",
        )

    def test_opendart_publisher_review_acknowledgement_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "readme",
            "JCAREER_SYNTHETIC_OPENDART_PUBLISH_BINDINGS_REVIEW",
            "JCAREER_SYNTHETIC_OPENDART_REVIEW_REMOVED",
            "clean-state OpenDART staging and reverse-order teardown are not documented",
        )

    def test_opendart_publisher_no_execution_boundary_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "readme",
            "No human disposition, push, runtime apply, or",
            "Human disposition, push, runtime apply, and",
            "clean-state OpenDART staging and reverse-order teardown are not documented",
        )

    def test_runtime_role_handoff_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "outputs",
            'output "runtime_role_name"',
            'output "unbound_runtime_role"',
            "lab apply must emit the bounded non-secret OpenDART role-name handoff",
        )

    def test_operator_held_preview_token_boundary_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy_lab",
            "[Security.SecureString]$HttpsPreviewBootstrapToken",
            "[string]$HttpsPreviewBootstrapToken",
            "one-command deployment must hash the preview token",
        )

    def test_database_boundary_verification_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy",
            "python3 tests/database_boundary.py",
            "python3 tests/lab_remote_smoke.py",
            "remote member/company database boundary verification is missing",
        )

    def test_bedrock_capability_broker_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy",
            "bedrock-broker.compose.override.yaml",
            "missing-bedrock-override.yaml",
            "deployment must consume the approved OpenDART state and separated capability brokers",
        )

    def test_bedrock_socket_tmpfiles_owner_drift_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy",
            "d /run/jcareer-bedrock 0750 11002 11002 -",
            "d /run/jcareer-bedrock 0755 0 0 -",
            "broker socket directories must be recreated with fixed ownership before compose starts and after host reboot",
        )

    def test_opendart_socket_tmpfiles_creation_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy",
            "systemd-tmpfiles --create /etc/tmpfiles.d/jcareer-opendart.conf",
            "true # removed persistent socket preparation",
            "broker socket directories must be recreated with fixed ownership before compose starts and after host reboot",
        )

    def test_reviewed_ssm_policy_attachment_change_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "main",
            'policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"',
            'policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"',
            "reviewed AmazonSSMManagedInstanceCore attachment is missing",
        )

    def test_lab_proxy_internal_service_deny_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "nginx",
            "location ~ ^/(agent|llm)(/|$) {",
            "location ~ ^/(never-match)(/|$) {",
            "lab proxy must reject direct agent and llm paths",
        )

    def test_lab_proxy_security_header_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "nginx",
            "add_header Content-Security-Policy",
            "removed_header Content-Security-Policy",
            "lab proxy security header is missing: Content-Security-Policy",
        )

    def test_guarded_destroy_acknowledgement_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "destroy_lab",
            "JCAREER_SYNTHETIC_LAB_DESTROY_APPROVED",
            "UNREVIEWED_DESTROY",
            "guarded destroy must require a distinct mandatory acknowledgement",
        )

    def test_output_cannot_bypass_guarded_destroy(self) -> None:
        self.assert_mutation_rejected(
            "outputs",
            "powershell -NoProfile -File terraform/lab/provisioning/destroy-lab.ps1 -DestroyAcknowledgement JCAREER_SYNTHETIC_LAB_DESTROY_APPROVED",
            "terraform -chdir=terraform/lab destroy",
            "Terraform output must direct operators to the guarded destroy wrapper",
        )

    def test_guarded_destroy_saved_plan_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "destroy_lab",
            "'plan', '-destroy', '-input=false', '-no-color'",
            "'destroy', '-input=false', '-no-color'",
            "guarded destroy must create and apply only a saved destroy plan",
        )

    def test_guarded_destroy_partial_state_recovery_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "destroy_lab",
            "elseif (Test-ReviewedAddressSubset -Observed $managedState -ReviewedUnion $reviewedAddressUnion)",
            "elseif ($false)",
            "guarded destroy must reject addresses outside the reviewed union and retain exact partial-state recovery",
        )

    def test_runtime_route_association_wait_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "main",
            "    aws_route_table_association.private_preview,\n",
            "",
            "runtime bootstrap must wait for both selected route-table associations",
        )

    def test_runtime_egress_wait_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "main",
            "    aws_vpc_security_group_egress_rule.internet,\n",
            "",
            "runtime bootstrap must wait for the reviewed egress rule",
        )

    def test_unbounded_lab_service_memory_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "lab_compose",
            "    mem_limit: 512m",
            "    mem_limit: 1512m",
            "lab memory limit for api must remain 512m",
        )

    def test_local_artifact_audit_reports_counts_without_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory) / "terraform" / "lab"
            cache = lab / ".terraform"
            cache.mkdir(parents=True)
            (lab / "terraform.tfstate.backup").write_text(
                json.dumps(
                    {
                        "resources": [
                            {"instances": [{"attributes": {"secret": "must-not-print"}}]}
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (cache / "plan.json").write_text("{}", encoding="utf-8")
            warnings = CHECKER.audit_local_artifacts(Path(directory))
            rendered = "\n".join(warnings)
            self.assertIn("1 historical managed instance record", rendered)
            self.assertIn("1 ignored saved plan/JSON artifact", rendered)
            self.assertNotIn("must-not-print", rendered)

    def test_local_artifact_audit_covers_root_plan_state_lock_and_crash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory) / "terraform" / "lab"
            lab.mkdir(parents=True)
            (lab / "custom.tfstate").write_text("sensitive-state", encoding="utf-8")
            (lab / "tfplan-lab").write_text("sensitive-plan", encoding="utf-8")
            (lab / "plan_lab.json").write_text("sensitive-json", encoding="utf-8")
            (lab / ".terraform.tfstate.lock.info.stale-test").write_text(
                "sensitive-lock", encoding="utf-8"
            )
            (lab / "crash.log").write_text("sensitive-crash", encoding="utf-8")
            rendered = "\n".join(CHECKER.audit_local_artifacts(Path(directory)))
            self.assertIn("1 additional Terraform state artifact", rendered)
            self.assertIn("1 Terraform lock artifact", rendered)
            self.assertIn("2 ignored saved plan/JSON artifact", rendered)
            self.assertIn("1 Terraform crash artifact", rendered)
            for secret in (
                "sensitive-state",
                "sensitive-plan",
                "sensitive-json",
                "sensitive-lock",
                "sensitive-crash",
            ):
                self.assertNotIn(secret, rendered)


if __name__ == "__main__":
    unittest.main()
