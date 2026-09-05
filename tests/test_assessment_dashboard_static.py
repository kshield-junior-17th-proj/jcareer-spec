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
        self.assertIn('projectControlIds: "PROJECT_T_ID_NOT_NIST_CONTROL_ID"', snapshot)
        self.assertIn('targetStatus: "UNVERIFIED_TARGET"', snapshot)
        self.assertIn('actualAfter: null', snapshot)
        self.assertNotIn("OWASP", page + snapshot)
        self.assertNotIn("ISO/IEC", page + snapshot)

    def test_accessibility_metadata_and_csp_contract(self) -> None:
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
        self.assertIn('content="assessment-metadata-only"', page)
        csp = re.search(
            r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">', page
        )
        self.assertIsNotNone(csp)
        policy = csp.group(1)
        self.assertIn("default-src 'self'", policy)
        self.assertIn("connect-src 'none'", policy)
        self.assertIn("object-src 'none'", policy)
        self.assertIn("form-action 'none'", policy)
        self.assertNotIn("'unsafe-inline'", policy)
        self.assertNotIn("'unsafe-eval'", policy)
        self.assertNotRegex(page, r"<script[^>]*>\s*[^<]+")
        self.assertNotRegex(page, r"\sstyle=")
        self.assertIn(":focus-visible", styles)
        self.assertIn("@media (prefers-reduced-motion: reduce)", styles)
        self.assertNotIn("transition: all", styles)
        self.assertIn('role="tab"', app)
        self.assertIn("aria-selected", app)
        self.assertIn('event.key === "Home"', app)

    def test_public_pages_and_aws_dashboard_are_not_conflated(self) -> None:
        page = (DASHBOARD / "index.html").read_text(encoding="utf-8")
        snapshot = (DASHBOARD / "assessment-snapshot.js").read_text(encoding="utf-8")

        self.assertIn("정적 페이지 게시와 기존 AWS 격리형 구축 계획은 구분합니다.", page)
        self.assertIn("GitHub Pages 공개 명세", page)
        self.assertIn("ACTUAL AFTER", page)
        self.assertIn("실측값 없음", page)
        self.assertIn('currentSurface: "GITHUB_PAGES_PUBLIC_SPEC_REFERENCE"', snapshot)
        self.assertIn('targetSurface: "AWS_ISOLATED_STATIC_S3_CLOUDFRONT_WAF"', snapshot)
        self.assertIn('status: "NOT_DEPLOYED"', snapshot)
        self.assertIn('githubPagesRelationship: "SEPARATE_PUBLIC_SPEC_REFERENCE_ONLY"', snapshot)

    def test_snapshot_counts_and_finding_ids_are_consistent(self) -> None:
        snapshot = (DASHBOARD / "assessment-snapshot.js").read_text(encoding="utf-8")
        evidence_counts = [int(value) for value in re.findall(r'count: (\d+), tone:', snapshot)]
        finding_ids = re.findall(r'id: "(NF-\d{2})", priority:', snapshot)

        self.assertEqual(evidence_counts, [4, 13, 6, 4])
        self.assertEqual(sum(evidence_counts), 27)
        self.assertEqual(finding_ids, ["NF-01", "NF-02", "NF-03", "NF-04", "NF-05", "NF-06"])


if __name__ == "__main__":
    unittest.main()
