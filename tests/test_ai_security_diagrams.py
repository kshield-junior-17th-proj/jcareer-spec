from __future__ import annotations

import hashlib
import json
import re
import struct
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"

DIAGRAMS = {
    "JCAREER_AI_RUNTIME_ACTUAL": {
        "status": "SOURCE_IMPLEMENTED_CURRENT_ACCOUNT_APPLY_SMOKE_UNVERIFIED",
        "nodes": 15,
        "edges": 17,
        "motion": 10,
    },
    "JCAREER_ASSESSMENT_EVIDENCE": {
        "status": "TARGET_EVIDENCE_PIPELINE_PARTIALLY_IMPLEMENTED_EXECUTION_PENDING",
        "nodes": 14,
        "edges": 14,
        "motion": 8,
    },
    "JCAREER_ENTERPRISE_TOBE_TARGET": {
        "status": "PLANNED_NOT_DEPLOYED_APPROVAL_GATED",
        "nodes": 17,
        "edges": 20,
        "motion": 9,
    },
}


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise AssertionError(f"not a PNG with IHDR: {path}")
    return struct.unpack(">II", data[16:24])


class AiSecurityDiagramContract(unittest.TestCase):
    def test_specs_bind_self_contained_animated_svg_and_still_png(self) -> None:
        for stem, expected in DIAGRAMS.items():
            with self.subTest(stem=stem):
                spec_path = ASSETS / f"{stem}.spec.json"
                svg_path = ASSETS / f"{stem}.svg"
                png_path = ASSETS / f"{stem}.png"
                spec_bytes = spec_path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
                spec = json.loads(spec_bytes)
                svg = svg_path.read_text(encoding="utf-8")

                self.assertEqual(spec["canvas"], {"w": 1800, "h": 980})
                self.assertEqual(spec["status"], expected["status"])
                self.assertEqual(len(spec["nodes"]), expected["nodes"])
                self.assertEqual(len(spec["edges"]), expected["edges"])
                self.assertEqual(
                    sum(len(journey["hops"]) for journey in spec["journeys"]),
                    expected["motion"],
                )
                self.assertEqual(svg.count("<animateMotion "), expected["motion"])
                self.assertEqual(svg.count('class="motion-dot"'), expected["motion"])
                self.assertNotRegex(svg, r'(?:href|src)="https?://|<image\b')
                self.assertIn('@media (prefers-reduced-motion: reduce)', svg)
                digest = hashlib.sha256(spec_bytes).hexdigest()
                self.assertIn(f'data-spec-sha256="{digest}"', svg)
                ET.fromstring(svg)
                self.assertEqual(png_dimensions(png_path), (1800, 980))

    def test_editable_drawio_has_three_bound_2400_by_1400_pages(self) -> None:
        tree = ET.parse(ASSETS / "JCAREER_AI_SECURITY_FLOWS.drawio")
        pages = tree.getroot().findall("diagram")
        self.assertEqual(
            [page.get("name") for page in pages],
            ["1-current-runtime", "2-assessment-evidence", "3-enterprise-tobe"],
        )
        for page in pages:
            model = page.find("mxGraphModel")
            self.assertIsNotNone(model)
            self.assertEqual((model.get("pageWidth"), model.get("pageHeight")), ("2400", "1400"))
            cells = model.findall("./root/mxCell")
            ids = {cell.get("id") for cell in cells}
            edges = [cell for cell in cells if cell.get("edge") == "1"]
            self.assertGreater(len(edges), 0)
            self.assertTrue(
                all(edge.get("source") in ids and edge.get("target") in ids for edge in edges)
            )
        drawio = (ASSETS / "JCAREER_AI_SECURITY_FLOWS.drawio").read_text(encoding="utf-8")
        for icon in ("cloudfront", "api_gateway", "lambda", "bedrock", "fargate", "rds", "elasticache"):
            self.assertIn(f"mxgraph.aws4.{icon}", drawio)

    def test_public_page_separates_current_evidence_and_tobe(self) -> None:
        page = (ROOT / "terraform" / "asis" / "index.html").read_text(encoding="utf-8")
        self.assertEqual(page.count('class="diagram-card"'), 3)
        positions = [page.index(f"../../assets/{stem}.svg") for stem in DIAGRAMS]
        self.assertEqual(positions, sorted(positions))
        section = re.search(
            r'<section id="production-assessment-slice".*?</section>', page, re.DOTALL
        )
        self.assertIsNotNone(section)
        self.assertIn("APPLY · LIVE SMOKE NOT RUN", section.group())
        self.assertNotIn("GITHUB E2E PASS", section.group())
        self.assertIn("TO-BE NOT DEPLOYED", section.group())


if __name__ == "__main__":
    unittest.main()
