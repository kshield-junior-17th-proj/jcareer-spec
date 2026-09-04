from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_tobe_ai_security_static.py"
SPEC = importlib.util.spec_from_file_location("check_tobe_ai_security_static", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TobeAiSecurityStaticContract(unittest.TestCase):
    def test_proposal_contract(self) -> None:
        self.assertEqual(MODULE.validate(ROOT), [])

    def test_evidence_map_never_upgrades_source_to_runtime(self) -> None:
        text = (ROOT / "terraform/tobe-ai-security/EVIDENCE_MAP.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("SOURCE PROPOSAL / NOT DEPLOYED / HUMAN REVIEW PENDING", text)
        self.assertIn("Prohibited claim", text)
        self.assertIn("current proof", text)
        self.assertNotIn("TRACE", text)
        self.assertNotIn("JC-RECEIPT", text)

    def test_cloudtrail_bucket_key_decrypt_regression_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(
                ROOT / "terraform" / "tobe-ai-security",
                root / "terraform" / "tobe-ai-security",
                ignore=shutil.ignore_patterns(".terraform"),
            )
            workflow = root / ".github" / "workflows"
            workflow.mkdir(parents=True)
            shutil.copy2(
                ROOT / ".github" / "workflows" / "public-release-check.yml",
                workflow / "public-release-check.yml",
            )
            metadata = (
                root
                / "terraform"
                / "tobe-ai-security"
                / "modules"
                / "metadata-observability"
                / "main.tf"
            )
            text = metadata.read_text(encoding="utf-8")
            marker = (
                "# Required when CloudTrail writes to an SSE-KMS bucket with S3 "
                "Bucket Keys.\n          \"kms:Decrypt\","
            )
            self.assertIn(marker, text)
            metadata.write_text(text.replace(marker, marker.split("\n")[0], 1), encoding="utf-8")
            self.assertTrue(
                any("Bucket Key KMS grant missing" in item for item in MODULE.validate(root))
            )

    def test_shared_kms_destroy_guard_regression_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(
                ROOT / "terraform" / "tobe-ai-security",
                root / "terraform" / "tobe-ai-security",
                ignore=shutil.ignore_patterns(".terraform"),
            )
            workflow = root / ".github" / "workflows"
            workflow.mkdir(parents=True)
            shutil.copy2(
                ROOT / ".github" / "workflows" / "public-release-check.yml",
                workflow / "public-release-check.yml",
            )
            metadata = (
                root
                / "terraform"
                / "tobe-ai-security"
                / "modules"
                / "metadata-observability"
                / "main.tf"
            )
            text = metadata.read_text(encoding="utf-8")
            self.assertIn("prevent_destroy = true", text)
            metadata.write_text(
                text.replace("prevent_destroy = true", "prevent_destroy = false", 1),
                encoding="utf-8",
            )
            self.assertIn(
                "shared evidence KMS key must set prevent_destroy = true",
                MODULE.validate(root),
            )


if __name__ == "__main__":
    unittest.main()
