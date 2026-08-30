from __future__ import annotations

import json
import unittest
from pathlib import Path


RUNTIME_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = RUNTIME_ROOT.parents[1]
CONTRACT_PATH = RUNTIME_ROOT / "contracts" / "mentor_feedback_2026_08_28.json"
BRIEF_ROOT = RUNTIME_ROOT / "mentor-brief"


class MentorFeedbackContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_source_and_decision_boundary_are_explicit(self) -> None:
        source = self.contract["source"]
        boundary = self.contract["decision_boundary"]
        self.assertEqual(source["meeting_date"], "2026-08-28")
        self.assertEqual(source["section"], "0828 회의록 정리본")
        self.assertIn("3ca0be5710e8805badf9c7fa7c8f762b", source["notion_url"])
        self.assertEqual(self.contract["document_state"], "DRAFT_FOR_HUMAN_DECISION")
        self.assertFalse(boundary["automatic_assessment"])
        self.assertFalse(boundary["automatic_compliance_decision"])
        self.assertFalse(boundary["automatic_risk_rating"])
        self.assertFalse(boundary["automatic_remediation_approval"])
        self.assertFalse(boundary["current_organization_baseline_replaced"])
        focus = self.contract["implementation_focus"]
        self.assertEqual(focus["primary"], "AI_SERVICE_FACT_BOUNDARY")
        self.assertEqual(focus["organization"], "CHANGEABLE_CONTEXT_HUMAN_DECISION_PENDING")
        self.assertEqual(len(focus["invariants"]), 5)

    def test_local_source_references_point_to_existing_headings(self) -> None:
        references: list[str] = []

        def collect(value: object) -> None:
            if isinstance(value, str) and value.startswith(("src/", "fleet/", "context/")):
                references.append(value)
            elif isinstance(value, dict):
                for nested in value.values():
                    collect(nested)
            elif isinstance(value, list):
                for nested in value:
                    collect(nested)

        collect(self.contract)
        self.assertGreater(len(references), 0)
        for reference in references:
            path_text, separator, heading = reference.partition("#")
            self.assertTrue(separator, f"source reference has no heading: {reference}")
            path = REPOSITORY_ROOT / path_text
            self.assertTrue(path.is_file(), f"source reference file is missing: {reference}")
            headings = {
                line.lstrip("#").strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.startswith("#")
            }
            self.assertIn(heading, headings, f"source reference heading is missing: {reference}")

    def test_devops_is_moved_out_without_rewriting_whiteboard_observation(self) -> None:
        organization = self.contract["organization"]
        observed = organization["observed_whiteboard"]
        proposal = organization["mentor_target_proposal"]
        self.assertIn("DevOps", observed["ai_service"]["observed_functions"])
        self.assertEqual(proposal["ai_service"]["moved_out_functions"], ["DevOps"])
        self.assertNotIn("DevOps", proposal["ai_service"]["retained_functions"])
        self.assertIn("Agent 자체학습", proposal["ai_service"]["explicitly_not_modeled"])
        self.assertFalse(proposal["infrastructure_team"]["devops_team_created"])
        infra_functions = {item["id"] for item in proposal["infrastructure_team"]["functions"]}
        self.assertEqual(infra_functions, {"INFRA-DEVOPS", "INFRA-SI", "INFRA-DATA"})
        capabilities = {
            item["label"] for item in proposal["information_security_team"]["capabilities"]
        }
        self.assertEqual(capabilities, {"Blue", "Red", "Compliance"})
        self.assertEqual(proposal["information_security_team"]["whiteboard_function_mapping"], "HUMAN_DECISION_PENDING")
        self.assertIn("80명 상위 노드명", observed["unresolved_labels"])
        self.assertIn("정보보안팀 첫 기능 명칭", observed["unresolved_labels"])

    def test_asset_scope_contains_requested_dimensions_and_explicit_exclusions(self) -> None:
        assets = self.contract["assets"]
        item_types = {item["type"] for item in assets["items"]}
        required_types = {
            "APPLICATION_RUNTIME",
            "BACKUP_SYSTEM",
            "FIREWALL",
            "WAF",
            "NETWORK_SECURITY_GROUP",
            "REMOTE_ACCESS_VPN",
            "PRIVILEGED_ACCESS_CHANNEL",
            "ACCESS_CONTROL_SYSTEM",
            "THREAT_DETECTION_SYSTEM",
            "AUDIT_TRAIL_SYSTEM",
            "NETWORK_TRAFFIC_LOGGING_SYSTEM",
            "SECURITY_LOG_REPOSITORY",
            "ANTIVIRUS",
            "EDR",
            "IPS",
            "IDS",
            "RACK_EQUIPMENT",
            "COLLABORATION_SAAS",
            "MEMBER_DATABASE",
            "COMPANY_DATABASE",
        }
        self.assertTrue(required_types.issubset(item_types))
        protection_items = [
            item for item in assets["items"] if item["category"] == "INFORMATION_PROTECTION_SYSTEM"
        ]
        self.assertEqual(len(protection_items), 14)
        slack = next(item for item in assets["items"] if item["id"] == "AST-SAAS-SLACK")
        self.assertEqual(slack["label"], "Slack")
        self.assertEqual(slack["operational_state"], "SCENARIO_USE_UNVERIFIED")
        firewall = next(item for item in assets["items"] if item["id"] == "AST-PROT-FIREWALL")
        self.assertEqual(firewall["scope_state"], "SCENARIO_BASELINE_AND_MENTOR_REQUIRED_DIMENSION")
        self.assertEqual(firewall["operational_state"], "DOCUMENTED_NOT_LAB_EVIDENCE")
        exclusions = {item["id"]: item["state"] for item in assets["scope_exclusions"]}
        self.assertEqual(exclusions["EX-ASSET-GROUPWARE"], "EXCLUDED_BY_2026_08_28_MENTOR_NOTE")
        self.assertEqual(exclusions["EX-ASSET-INTERNAL-DB"], "EXCLUDED_BY_2026_08_28_MENTOR_NOTE")
        self.assertEqual(exclusions["EX-ASSET-ROUTER"], "EXCLUDED_BY_WHITEBOARD_STRIKETHROUGH")
        self.assertTrue(all(item["owner"] == "HUMAN_ASSIGNMENT_PENDING" for item in assets["items"]))

    def test_information_protection_register_separates_present_unknown_and_absent(self) -> None:
        inventory = (RUNTIME_ROOT / "INFORMATION_PROTECTION_SYSTEM_INVENTORY.md").read_text(encoding="utf-8")
        for system_id in (
            "IPS-EDGE-01",
            "IPS-EDGE-02",
            "IPS-NET-01",
            "IPS-ACCESS-01",
            "IPS-ACCESS-02",
            "IPS-ACCESS-03",
            "IPS-DETECT-01",
            "IPS-AUDIT-01",
            "IPS-AUDIT-02",
            "IPS-AUDIT-03",
            "IPS-ENDPOINT-01",
            "IPS-NET-02",
            "IPS-NET-03",
        ):
            self.assertIn(f"`{system_id}`", inventory)
        self.assertIn("MENTOR_REQUESTED_UNVERIFIED", inventory)
        self.assertIn("DECLARED_ABSENT", inventory)
        self.assertIn("정보보호시스템 수에 포함하지 않음", inventory)
        self.assertIn("실제 운영 배포를 자동으로 증명하지 않는다", inventory)

    def test_real_user_training_is_disabled_and_synthetic_serverless_source_is_bounded(self) -> None:
        training = self.contract["training_and_mlops"]
        transfer = training["data_transfer"]
        matcher = training["runtime_matcher"]
        synthetic = training["synthetic_mlops"]
        user_data = training["user_data_training"]
        self.assertFalse(matcher["trains_agent"])
        self.assertFalse(matcher["training_endpoint_implemented"])
        self.assertEqual(matcher["bedrock_role"], "EXPLANATION_ONLY_NOT_SCORING")
        self.assertEqual(transfer["candidate_context_key_count"], 8)
        self.assertEqual(transfer["company_context_key_count"], 6)
        self.assertEqual(transfer["counter_flagged_key_count"], 6)
        self.assertFalse(transfer["approved_minimization_allowlist_implemented"])
        self.assertEqual(transfer["allowlist_state"], "NOT_IMPLEMENTED_HUMAN_DECISION_PENDING")
        self.assertTrue(synthetic["member_data_used"])
        self.assertTrue(synthetic["company_customer_data_used"])
        self.assertFalse(synthetic["runtime_wired"])
        self.assertTrue(synthetic["source_runtime_db_wired"])
        self.assertFalse(synthetic["ranking_runtime_wired"])
        self.assertEqual(synthetic["synthetic_attestation"], "JCAREER_SYNTHETIC_ONLY")
        self.assertEqual(len(synthetic["training_features"]), 5)
        self.assertEqual(synthetic["label"], "pipeline_progression_proxy")
        qualitative = synthetic["qualitative_feature_boundary"]
        self.assertEqual(qualitative["self_intro_job_method"], "TOKEN_OVERLAP_PROXY_V1")
        self.assertFalse(qualitative["bedrock_embedding_wired"])
        self.assertFalse(qualitative["semantic_understanding_claim_allowed"])
        self.assertEqual(synthetic["serverless_source"]["compute"], "LAMBDA_ONE_SHOT")
        self.assertEqual(synthetic["serverless_source"]["source_mode"], "S3_FEATURE_SNAPSHOT")
        self.assertEqual(synthetic["serverless_source"]["trigger"], "APPROVED_MANUAL_INVOCATION_ONLY")
        self.assertFalse(synthetic["serverless_source"]["schedule_enabled"])
        self.assertFalse(synthetic["serverless_source"]["database_urls_in_terraform"])
        self.assertEqual(
            synthetic["serverless_source"]["object_encryption"],
            "SSE_S3_ONLY_KMS_NOT_WIRED",
        )
        self.assertIn("PRESTATE", synthetic["serverless_source"]["failed_safe_boundary"])
        self.assertFalse(synthetic["serverless_source"]["sagemaker_used"])
        self.assertEqual(synthetic["serverless_source"]["aws_execution_state"], "NOT_CLAIMED")
        self.assertEqual(
            user_data["default_state"],
            "REAL_USER_DATA_DISABLED_SYNTHETIC_RUNTIME_DATA_ENABLED",
        )
        self.assertEqual(user_data["current_training_consent_type"], "NOT_IMPLEMENTED")
        self.assertNotIn("model_training", user_data["current_runtime_consent_types"])
        self.assertFalse(user_data["ai_recommendation_purpose_is_training_consent"])
        self.assertGreaterEqual(len(user_data["required_gates_before_any_enablement"]), 7)

    def test_checklist_and_ceo_scenario_counts_are_not_silently_changed(self) -> None:
        checklist = self.contract["checklist"]
        brief = self.contract["ceo_brief"]
        scenarios = brief["candidate_scenarios"]
        self.assertEqual(checklist["declared_item_count"], 97)
        self.assertFalse(checklist["reduction_allowed"])
        self.assertEqual(checklist["full_items_imported"], 0)
        self.assertFalse(checklist["completion_claim_allowed"])
        self.assertEqual(brief["candidate_scenario_count"], 8)
        self.assertEqual(len(scenarios), 8)
        self.assertEqual(
            {item["classification"] for item in scenarios},
            {"MANAGEMENT", "TECHNICAL", "PHYSICAL"},
        )
        self.assertTrue(all(item["owner"] == "HUMAN_ASSIGNMENT_PENDING" for item in scenarios))
        scenario_ids = {item["id"] for item in scenarios}
        masterplan_ids = {
            item_id
            for phase in brief["masterplan"]
            for item_id in phase["workstream_ids"]
        }
        self.assertEqual(masterplan_ids, scenario_ids)
        self.assertTrue(
            all(phase["approval_state"] == "HUMAN_DECISION_NOT_RECORDED" for phase in brief["masterplan"])
        )

    def test_runtime_docs_keep_observation_and_mentor_proposal_separate(self) -> None:
        spec = (RUNTIME_ROOT / "ASIS_RUNTIME_SPEC.md").read_text(encoding="utf-8")
        flow = (RUNTIME_ROOT / "AI_MATCHING_FLOW.md").read_text(encoding="utf-8")
        for content in (spec, flow):
            self.assertIn("MENTOR_PROPOSED_HUMAN_DECISION_PENDING", content)
            self.assertIn("AI서비스", content)
            self.assertIn("인프라팀", content)
            self.assertIn("SI팀", content)
            self.assertIn("데이터팀", content)
            self.assertIn("Blue", content)
            self.assertIn("Red", content)
            self.assertIn("Compliance", content)
            self.assertIn("AI 서비스 사실 경계", content)

    def test_brief_uses_text_nodes_and_has_accessibility_guards(self) -> None:
        html = (BRIEF_ROOT / "index.html").read_text(encoding="utf-8")
        script = (BRIEF_ROOT / "app.js").read_text(encoding="utf-8")
        styles = (BRIEF_ROOT / "styles.css").read_text(encoding="utf-8")
        for element_id in (
            "source-link",
            "org-map",
            "asset-register",
            "training-boundary",
            "scenario-list",
            "masterplan",
            "checklist-state",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("../contracts/mentor_feedback_2026_08_28.json", script)
        self.assertIn("textContent", script)
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("eval(", script)
        self.assertNotIn("pill(tone, tone)", script)
        self.assertNotIn("pill(stateTone(asset.operational_state)", script)
        self.assertIn("boundary-card--data", script)
        self.assertIn("승인 allowlist", script)
        self.assertIn(":focus-visible", styles)
        self.assertIn("prefers-reduced-motion", styles)
        self.assertIn("@media (max-width:", styles)
        self.assertLess(html.index('id="training-boundary"'), html.index('id="asset-register"'))
        self.assertLess(html.index('id="asset-register"'), html.index('id="scenario-list"'))
        self.assertLess(html.index('id="scenario-list"'), html.index('id="org-map"'))


if __name__ == "__main__":
    unittest.main()
