from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "assessment-dashboard"


class AssessmentDashboardContract(unittest.TestCase):
    def test_public_interpretation_boundary_is_explicit(self) -> None:
        page = (DASHBOARD / "index.html").read_text(encoding="utf-8")
        snapshot = (DASHBOARD / "assessment-snapshot.js").read_text(encoding="utf-8")

        self.assertIn("NIST AI RMF", page)
        self.assertIn("NIST 기능은 판단의 구조이고", page)
        self.assertIn("T.x 내부 항목 · NIST ID 아님", page)
        self.assertIn("준수, 성숙도, 운영효과성 또는 잔여위험을 자동 판정하지 않습니다.", page)
        self.assertIn("NOT AN AI RMF SCORE", page)
        self.assertIn('framework: "NIST AI RMF"', snapshot)
        self.assertIn('projectControlIds: "INTERNAL_NOT_NIST_SUBCATEGORY_IDS"', snapshot)
        self.assertIn('targetStatus: "PROPOSED_NOT_VERIFIED"', snapshot)
        self.assertNotIn("OWASP", page + snapshot)
        self.assertNotRegex(snapshot, r"LLM\d{2}")

    def test_accessibility_and_metadata_contract(self) -> None:
        page = (DASHBOARD / "index.html").read_text(encoding="utf-8")
        styles = (DASHBOARD / "styles.css").read_text(encoding="utf-8")
        app = (DASHBOARD / "app.js").read_text(encoding="utf-8")

        self.assertIn('class="skip-link"', page)
        self.assertIn('id="content"', page)
        self.assertIn('rel="canonical"', page)
        self.assertIn('property="og:image:alt"', page)
        self.assertIn('data-assessment-boundary', page)
        self.assertIn('role="tablist"', page)
        self.assertIn('role="tabpanel"', page)
        self.assertIn(":focus-visible", styles)
        self.assertIn("@media (prefers-reduced-motion: reduce)", styles)
        self.assertNotIn("transition: all", styles)
        self.assertIn('role="tab"', app)
        self.assertIn('aria-selected', app)
        self.assertIn('event.key === "Home"', app)

    def test_snapshot_counts_and_finding_ids_are_consistent(self) -> None:
        snapshot = (DASHBOARD / "assessment-snapshot.js").read_text(encoding="utf-8")
        evidence_counts = [int(value) for value in re.findall(r'count: (\d+), tone:', snapshot)]
        finding_ids = re.findall(r'id: "(NF-\d{2})"', snapshot)

        self.assertEqual(evidence_counts, [4, 13, 6, 4])
        self.assertEqual(sum(evidence_counts), 27)
        self.assertEqual(finding_ids, ["NF-01", "NF-02", "NF-03", "NF-04", "NF-05", "NF-06"])


if __name__ == "__main__":
    unittest.main()
