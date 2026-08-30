#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_serverless_opendart_static",
    ROOT / "scripts/check_serverless_opendart_static.py",
)
assert SPEC and SPEC.loader
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class ServerlessOpenDartStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = CHECKER.load_sources(ROOT)

    def test_current_sources_match_boundary(self) -> None:
        self.assertEqual(CHECKER.audit_sources(self.sources), [])

    def test_nat_and_database_lane_are_rejected(self) -> None:
        mutated = dict(self.sources)
        mutated["terraform_all"] += '\nresource "aws_nat_gateway" "bad" {}\ncompany_database_url = "bad"\n'
        errors = CHECKER.audit_sources(mutated)
        self.assertTrue(any("NAT Gateway" in error for error in errors))
        self.assertTrue(any("database URLs" in error for error in errors))

    def test_mutable_image_reference_is_rejected(self) -> None:
        mutated = dict(self.sources)
        old = 'can(regex("@sha256:[0-9a-f]{64}$", var.lambda_image_uri))'
        mutated["main"] = mutated["main"].replace(old, "true", 1)
        self.assertTrue(any("digest-pinned" in error for error in CHECKER.audit_sources(mutated)))

    def test_missing_partial_batch_response_is_rejected(self) -> None:
        mutated = dict(self.sources)
        mutated["main"] = mutated["main"].replace('function_response_types            = ["ReportBatchItemFailures"]', "", 1)
        self.assertTrue(any("partial batch" in error for error in CHECKER.audit_sources(mutated)))

    def test_example_cannot_self_approve(self) -> None:
        mutated = dict(self.sources)
        mutated["approval"] = mutated["approval"].replace("PENDING_HUMAN_DECISION", "APPROVED", 1)
        self.assertTrue(any("remain pending" in error for error in CHECKER.audit_sources(mutated)))

    def test_disabled_plan_requires_zero_addresses(self) -> None:
        plan = {
            "planned_values": {
                "outputs": {"deployment_stage": {"value": "disabled"}},
                "root_module": {"resources": []},
            },
            "resource_changes": [],
        }
        self.assertEqual(CHECKER.audit_plan_document(plan), [])

    def test_bootstrap_plan_requires_exact_eight_addresses(self) -> None:
        addresses = CHECKER.EXPECTED_PLAN_ADDRESSES["bootstrap"]
        plan = {
            "planned_values": {
                "outputs": {"deployment_stage": {"value": "bootstrap"}},
                "root_module": {"resources": [
                    {"address": address, "type": address.split(".", 1)[0]}
                    for address in sorted(addresses)
                ]},
            },
            "resource_changes": [],
        }
        self.assertEqual(CHECKER.audit_plan_document(plan), [])
        plan["planned_values"]["root_module"]["resources"].pop()
        self.assertTrue(any("expected=8" in error for error in CHECKER.audit_plan_document(plan)))

    def test_runtime_plan_requires_exact_eleven_addresses(self) -> None:
        addresses = CHECKER.EXPECTED_PLAN_ADDRESSES["runtime"]
        plan = {
            "planned_values": {
                "outputs": {"deployment_stage": {"value": "runtime"}},
                "root_module": {"resources": [
                    {"address": address, "type": address.split(".", 1)[0]}
                    for address in sorted(addresses)
                ]},
            },
            "resource_changes": [],
        }
        self.assertEqual(CHECKER.audit_plan_document(plan), [])

    def test_delete_or_unapproved_resource_is_rejected(self) -> None:
        plan = {
            "planned_values": {
                "outputs": {"deployment_stage": {"value": "disabled"}},
                "root_module": {"resources": [
                    {"address": "aws_instance.bad", "type": "aws_instance"}
                ]},
            },
            "resource_changes": [{"change": {"actions": ["delete", "create"]}}],
        }
        errors = CHECKER.audit_plan_document(plan)
        self.assertTrue(any("unapproved" in error for error in errors))
        self.assertTrue(any("delete" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
