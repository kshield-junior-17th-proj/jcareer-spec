#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_serverless_mlops_static",
    ROOT / "scripts" / "check_serverless_mlops_static.py",
)
assert SPEC and SPEC.loader
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class ServerlessMLOpsStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = CHECKER.load_sources(ROOT)

    def test_current_sources_match_boundary(self) -> None:
        self.assertEqual(CHECKER.audit_sources(self.sources), [])

    def test_sagemaker_resource_is_rejected(self) -> None:
        mutated = dict(self.sources)
        mutated["terraform_all"] += '\nresource "aws_sagemaker_endpoint" "bad" {}\n'
        errors = CHECKER.audit_sources(mutated)
        self.assertTrue(any("SageMaker" in error for error in errors))

    def test_vpc_database_lane_is_rejected(self) -> None:
        mutated = dict(self.sources)
        mutated["terraform_all"] += '\nvpc_config {}\nmember_database_url = "bad"\n'
        errors = CHECKER.audit_sources(mutated)
        self.assertTrue(any("lab VPC" in error for error in errors))
        self.assertTrue(any("database URLs" in error for error in errors))

    def test_digest_repository_binding_is_required(self) -> None:
        mutated = dict(self.sources)
        mutated["main"] = mutated["main"].replace(
            '"${aws_ecr_repository.mlops[0].repository_url}@sha256:"',
            '"unbound.example.invalid/repository@sha256:"',
            1,
        )
        mutated["terraform_all"] = mutated["terraform_all"].replace(
            '"${aws_ecr_repository.mlops[0].repository_url}@sha256:"',
            '"unbound.example.invalid/repository@sha256:"',
            1,
        )
        self.assertTrue(
            any("digest-pinned" in error for error in CHECKER.audit_sources(mutated))
        )

    def test_timeout_expansion_is_rejected(self) -> None:
        mutated = dict(self.sources)
        mutated["main"] = mutated["main"].replace("timeout       = 300", "timeout       = 900", 1)
        mutated["terraform_all"] = mutated["terraform_all"].replace(
            "timeout       = 300", "timeout       = 900", 1
        )
        self.assertTrue(any("timeout" in error for error in CHECKER.audit_sources(mutated)))

    def test_sse_s3_rejects_unwired_kms_options(self) -> None:
        mutated = dict(self.sources)
        mutated["main"] += "\nbucket_key_enabled = true\n"
        self.assertTrue(
            any("S3 Bucket Key" in error for error in CHECKER.audit_sources(mutated))
        )
        mutated = dict(self.sources)
        mutated["lambda_handler"] += '\nMLOPS_ARTIFACT_KMS_KEY_ID = "unwired"\n'
        self.assertTrue(
            any("unwired SSE-KMS" in error for error in CHECKER.audit_sources(mutated))
        )

    def test_operator_stop_command_is_rejected(self) -> None:
        mutated = dict(self.sources)
        mutated["operator"] += "\naws ec2 stop-instances --instance-ids bad\n"
        self.assertTrue(
            any("never stop" in error for error in CHECKER.audit_sources(mutated))
        )

    def test_operator_provider_account_hash_binding_is_required(self) -> None:
        mutated = dict(self.sources)
        mutated["operator"] = mutated["operator"].replace(
            "Get-StringSha256 -Value $account",
            "$account",
            1,
        )
        self.assertTrue(
            any(
                "provider account SHA-256" in error
                for error in CHECKER.audit_sources(mutated)
            )
        )

    def test_operator_absolute_tool_resolution_is_required(self) -> None:
        mutated = dict(self.sources)
        mutated["operator"] = mutated["operator"].replace(
            "$script:ToolPaths.aws ssm get-command-invocation",
            "aws ssm get-command-invocation",
            1,
        )
        errors = CHECKER.audit_sources(mutated)
        self.assertTrue(any("shadowable tool" in error for error in errors))

    def test_operator_saved_plan_lock_and_hash_binding_are_required(self) -> None:
        mutated = dict(self.sources)
        mutated["operator"] = mutated["operator"].replace(
            "$bootstrapContext.PlanPath",
            "$bootstrapPlan",
        )
        self.assertTrue(
            any(
                "read-locked and hash-bound" in error
                for error in CHECKER.audit_sources(mutated)
            )
        )

        mutated = dict(self.sources)
        mutated["operator"] = mutated["operator"].replace(
            "Protect-PlanJson ($planOutput",
            "($planOutput",
            1,
        )
        self.assertTrue(
            any(
                "read-locked and hash-bound" in error
                for error in CHECKER.audit_sources(mutated)
            )
        )

    def test_lambda_snapshot_module_is_required(self) -> None:
        mutated = dict(self.sources)
        mutated["lambda_dockerfile"] = mutated["lambda_dockerfile"].replace(
            "COPY run_snapshot_pipeline.py", "# removed", 1
        )
        self.assertTrue(
            any("snapshot pipeline" in error for error in CHECKER.audit_sources(mutated))
        )

    def test_lambda_human_review_module_and_conditional_transition_are_required(self) -> None:
        mutated = dict(self.sources)
        mutated["lambda_dockerfile"] = mutated["lambda_dockerfile"].replace(
            "COPY review_challenger.py", "# removed", 1
        )
        self.assertTrue(
            any("human-review module" in error for error in CHECKER.audit_sources(mutated))
        )

        mutated = dict(self.sources)
        mutated["lambda_handler"] = mutated["lambda_handler"].replace(
            "attribute_not_exists(review_receipt_sha256)",
            "attribute_exists(review_receipt_sha256)",
            1,
        )
        self.assertTrue(
            any("conditional single-record" in error for error in CHECKER.audit_sources(mutated))
        )

    def test_result_version_binding_and_review_invariants_are_required(self) -> None:
        mutated = dict(self.sources)
        mutated["lambda_handler"] = mutated["lambda_handler"].replace(
            '"IfNoneMatch": "*"', '"IfNoneMatch": "ignored"', 1
        )
        self.assertTrue(
            any("create-only" in error for error in CHECKER.audit_sources(mutated))
        )

        mutated = dict(self.sources)
        mutated["lambda_handler"] = mutated["lambda_handler"].replace(
            "automatic_model_activation = :false",
            "automatic_model_activation = :synthetic_true",
        )
        self.assertTrue(
            any("every synthetic non-activation" in error for error in CHECKER.audit_sources(mutated))
        )

    def test_training_completion_and_full_synthetic_preflight_are_required(self) -> None:
        mutated = dict(self.sources)
        mutated["lambda_handler"] = mutated["lambda_handler"].replace(
            "#state = :running_state AND human_input_state = :not_recorded",
            "#state = :pending_state AND human_input_state = :not_recorded",
        )
        self.assertTrue(
            any(
                "conditionally transition" in error
                for error in CHECKER.audit_sources(mutated)
            )
        )

        mutated = dict(self.sources)
        mutated["exporter_source"] = mutated["exporter_source"].replace(
            "for member in members.values():",
            "for member in ():",
            1,
        )
        self.assertTrue(
            any(
                "complete member/reference read set" in error
                for error in CHECKER.audit_sources(mutated)
            )
        )

        mutated = dict(self.sources)
        mutated["exporter_source"] = mutated["exporter_source"].replace(
            "_assert_synthetic_company_job_source(raw_jobs)",
            "pass  # company source not checked",
            1,
        )
        self.assertTrue(
            any(
                "complete member/reference read set" in error
                for error in CHECKER.audit_sources(mutated)
            )
        )

        mutated = dict(self.sources)
        mutated["review_source"] = mutated["review_source"].replace(
            'RECORDED_REVIEW_STATE = "HUMAN_INPUT_RECORDED"',
            'RECORDED_REVIEW_STATE = "APPROVED"',
            1,
        )
        self.assertTrue(
            any("without release authorization" in error for error in CHECKER.audit_sources(mutated))
        )

    def test_plan_rejects_unapproved_resource(self) -> None:
        plan = {
            "planned_values": {
                "outputs": {"deployment_stage": {"value": "runtime"}},
                "root_module": {
                    "resources": [{"type": "aws_nat_gateway", "address": "aws_nat_gateway.bad"}]
                }
            },
            "resource_changes": [],
        }
        self.assertTrue(
            any("unapproved" in error for error in CHECKER.audit_plan_document(plan))
        )

    def test_plan_rejects_delete_or_replace(self) -> None:
        plan = {
            "planned_values": {
                "outputs": {"deployment_stage": {"value": "disabled"}},
                "root_module": {"resources": []},
            },
            "resource_changes": [
                {"change": {"actions": ["delete", "create"]}}
            ],
        }
        self.assertTrue(
            any("delete" in error for error in CHECKER.audit_plan_document(plan))
        )

    def test_disabled_plan_requires_exact_zero_addresses(self) -> None:
        plan = {
            "planned_values": {
                "outputs": {"deployment_stage": {"value": "disabled"}},
                "root_module": {"resources": []},
            },
            "resource_changes": [],
        }
        self.assertEqual(CHECKER.audit_plan_document(plan), [])

    def test_bootstrap_plan_requires_exact_thirteen_addresses(self) -> None:
        resources = [
            {"address": address, "type": address.split(".", 1)[0]}
            for address in sorted(CHECKER.BOOTSTRAP_PLAN_ADDRESSES)
        ]
        plan = {
            "planned_values": {
                "outputs": {"deployment_stage": {"value": "bootstrap"}},
                "root_module": {"resources": resources},
            },
            "resource_changes": [],
        }
        self.assertEqual(CHECKER.audit_plan_document(plan), [])
        plan["planned_values"]["root_module"]["resources"].pop()
        self.assertTrue(
            any("expected=13" in error for error in CHECKER.audit_plan_document(plan))
        )

    def test_runtime_plan_requires_exact_fourteen_addresses(self) -> None:
        addresses = CHECKER.EXPECTED_PLAN_ADDRESSES["runtime"]
        plan = {
            "planned_values": {
                "outputs": {"deployment_stage": {"value": "runtime"}},
                "root_module": {
                    "resources": [
                        {"address": address, "type": address.split(".", 1)[0]}
                        for address in sorted(addresses)
                    ]
                },
            },
            "resource_changes": [],
        }
        self.assertEqual(CHECKER.audit_plan_document(plan), [])


if __name__ == "__main__":
    unittest.main()
