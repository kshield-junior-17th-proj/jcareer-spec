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

    def test_public_ingress_is_rejected(self) -> None:
        mutated = dict(self.sources)
        mutated["terraform_all"] += '\nresource "aws_vpc_security_group_ingress_rule" "bad" {}\n'
        self.assertIn("public/VPC ingress rule is present", CHECKER.audit_sources(mutated))

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

    def test_all_interface_web_binding_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy",
            "WEB_BIND_ADDRESS=127.0.0.1",
            "WEB_BIND_ADDRESS=0.0.0.0",
            "remote web binding must remain loopback",
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

    def test_archive_integrity_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy",
            "Get-FileHash",
            "Removed-HashCommand",
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

    def test_deploy_profile_name_binding_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy",
            "$profileName -ne $instanceName",
            "$profileName -ne $profileName",
            "deployment must bind the target instance to its reviewed runtime profile name",
        )

    def test_database_boundary_verification_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy",
            "python3 tests/database_boundary.py",
            "python3 tests/lab_remote_smoke.py",
            "remote member/company database boundary verification is missing",
        )

    def test_bedrock_credential_boundary_block_removal_is_rejected(self) -> None:
        self.assert_mutation_rejected(
            "deploy",
            "Bedrock live is blocked until a container-scoped credential boundary",
            "Bedrock live was allowed without isolation",
            "deployment must fail closed on the unresolved Bedrock credential boundary",
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
