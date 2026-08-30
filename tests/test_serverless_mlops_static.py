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

    def test_operator_stop_command_is_rejected(self) -> None:
        mutated = dict(self.sources)
        mutated["operator"] += "\naws ec2 stop-instances --instance-ids bad\n"
        self.assertTrue(
            any("never stop" in error for error in CHECKER.audit_sources(mutated))
        )

    def test_lambda_snapshot_module_is_required(self) -> None:
        mutated = dict(self.sources)
        mutated["lambda_dockerfile"] = mutated["lambda_dockerfile"].replace(
            "COPY run_snapshot_pipeline.py", "# removed", 1
        )
        self.assertTrue(
            any("snapshot pipeline" in error for error in CHECKER.audit_sources(mutated))
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
