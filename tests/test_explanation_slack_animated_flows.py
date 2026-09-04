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
    "JCAREER_AI_RECOMMENDATION_EXPLANATION": {
        "status": "LIVE_VERIFIED_2026_09_01_SYNTHETIC_SERVERLESS_SLICE",
        "nodes": 15,
        "edges": 17,
        "motion": 17,
    },
    "JCAREER_SLACK_BUSINESS_INTEGRATION": {
        "status": "SOURCE_IMPLEMENTED_DEFAULT_OFF_EXTERNAL_DELIVERY_UNCONFIRMED",
        "nodes": 14,
        "edges": 9,
        "motion": 15,
    },
}


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise AssertionError(f"not a PNG with IHDR: {path}")
    return struct.unpack(">II", data[16:24])


def gif_metadata(path: Path) -> tuple[tuple[int, int], int, set[int]]:
    data = path.read_bytes()
    if data[:6] not in {b"GIF87a", b"GIF89a"}:
        raise AssertionError(f"not a GIF: {path}")
    width, height = struct.unpack("<HH", data[6:10])
    position = 13
    packed = data[10]
    if packed & 0x80:
        position += 3 * (2 ** ((packed & 0x07) + 1))
    frames = 0
    delays: set[int] = set()
    while position < len(data):
        marker = data[position]
        if marker == 0x3B:
            break
        if marker == 0x21:
            label = data[position + 1]
            position += 2
            first_block = True
            while True:
                block_size = data[position]
                position += 1
                if block_size == 0:
                    break
                if label == 0xF9 and first_block and block_size == 4:
                    delays.add(struct.unpack("<H", data[position + 1 : position + 3])[0])
                position += block_size
                first_block = False
            continue
        if marker == 0x2C:
            frames += 1
            descriptor_packed = data[position + 9]
            position += 10
            if descriptor_packed & 0x80:
                position += 3 * (2 ** ((descriptor_packed & 0x07) + 1))
            position += 1
            while True:
                block_size = data[position]
                position += 1
                if block_size == 0:
                    break
                position += block_size
            continue
        raise AssertionError(f"unexpected GIF block 0x{marker:02x} at {position}: {path}")
    return (width, height), frames, delays


def anchor(node: dict[str, object], side: str) -> tuple[float, float]:
    x = float(node["x"])
    y = float(node["y"])
    return {
        "t": (x, y - 23),
        "b": (x, y + 23),
        "l": (x - 23, y),
        "r": (x + 23, y),
    }[side]


class ExplanationSlackAnimatedFlowContract(unittest.TestCase):
    def test_specs_bind_self_contained_svg_and_all_media_formats(self) -> None:
        for stem, expected in DIAGRAMS.items():
            with self.subTest(stem=stem):
                spec_path = ASSETS / f"{stem}.spec.json"
                svg_path = ASSETS / f"{stem}.svg"
                png_path = ASSETS / f"{stem}.png"
                gif_path = ASSETS / f"{stem}.gif"
                mp4_path = ASSETS / f"{stem}.mp4"
                spec_bytes = spec_path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
                spec = json.loads(spec_bytes)
                svg = svg_path.read_text(encoding="utf-8")

                self.assertEqual(spec["canvas"], {"w": 1800, "h": 980})
                self.assertEqual(spec["status"], expected["status"])
                self.assertEqual(len(spec["nodes"]), expected["nodes"])
                self.assertEqual(len(spec["edges"]), expected["edges"])
                motion = sum(len(journey["hops"]) for journey in spec["journeys"])
                self.assertEqual(motion, expected["motion"])
                self.assertEqual(svg.count("<animateMotion "), motion)
                self.assertEqual(svg.count('class="motion-dot"'), motion)
                self.assertNotRegex(svg, r'(?:href|src)="https?://|<image\b')
                self.assertIn("@media (prefers-reduced-motion: reduce)", svg)
                self.assertIn(
                    f'data-spec-sha256="{hashlib.sha256(spec_bytes).hexdigest()}"',
                    svg,
                )
                ET.fromstring(svg)

                self.assertEqual(png_dimensions(png_path), (1800, 980))
                gif_size, gif_frames, gif_delays = gif_metadata(gif_path)
                self.assertEqual(gif_size, (1200, 653))
                self.assertEqual(gif_frames, 40)
                self.assertEqual(gif_delays, {10})

                mp4 = mp4_path.read_bytes()
                self.assertEqual(mp4[4:8], b"ftyp")
                self.assertIn(b"avc1", mp4)
                self.assertLess(mp4.index(b"moov"), mp4.index(b"mdat"))

    def test_every_component_and_connector_has_evidence_and_truth_status(self) -> None:
        for stem in DIAGRAMS:
            with self.subTest(stem=stem):
                spec = json.loads((ASSETS / f"{stem}.spec.json").read_text(encoding="utf-8"))
                self.assertIn("architecture_truth_and_tobe.md", spec["source_of_truth"]["architecture_truth"])
                for collection in ("nodes", "edges", "groups"):
                    for component in spec[collection]:
                        self.assertTrue(component.get("status"), component)
                        self.assertTrue(component.get("evidence"), component)

                nodes = {node["id"]: node for node in spec["nodes"]}
                for edge in spec["edges"]:
                    points = [
                        anchor(nodes[edge["from"]], edge.get("fs", "r")),
                        *(tuple(point) for point in edge.get("mids", [])),
                        anchor(nodes[edge["to"]], edge.get("ts", "l")),
                    ]
                    for start, end in zip(points, points[1:]):
                        self.assertTrue(
                            start[0] == end[0] or start[1] == end[1],
                            f"diagonal segment in {stem}: {edge['from']} -> {edge['to']} {start} {end}",
                        )

                visible_text = " ".join(
                    [spec["title"], spec["subtitle"], spec["footer"]]
                    + [str(node.get("label", "")) + " " + str(node.get("sub", "")) for node in spec["nodes"]]
                )
                self.assertIsNone(re.search(r"\b(?:TRACE|JC-RECEIPT)\b", visible_text, re.IGNORECASE))

    def test_ai_flow_keeps_score_and_bedrock_authority_separate(self) -> None:
        spec = json.loads(
            (ASSETS / "JCAREER_AI_RECOMMENDATION_EXPLANATION.spec.json").read_text(encoding="utf-8")
        )
        nodes = {node["id"]: node for node in spec["nodes"]}
        self.assertEqual(nodes["agent"]["sub"], "deterministic score owner")
        self.assertEqual(nodes["bedrock"]["sub"], "qualitative evidence only")
        self.assertIn("Broker-only Bedrock invoke", " ".join(group["label"] for group in spec["groups"]))
        self.assertIn("no autonomous hire or reject action", spec["footer"])
        self.assertNotIn("score owner", nodes["bedrock"]["sub"])
        self.assertTrue(
            {"cloudfront", "cognito", "apigateway", "lambda", "sqs", "bedrock", "s3", "dynamodb", "cloudwatch"}
            .issubset({node["icon"] for node in spec["nodes"]})
        )

    def test_business_systems_are_disconnected_and_slack_is_receive_only(self) -> None:
        spec = json.loads(
            (ASSETS / "JCAREER_SLACK_BUSINESS_INTEGRATION.spec.json").read_text(encoding="utf-8")
        )
        nodes = {node["id"]: node for node in spec["nodes"]}
        external_nodes = {"slack_external", "notion_external", "smtp_external"}
        edge_nodes = {edge[side] for edge in spec["edges"] for side in ("from", "to")}
        self.assertTrue(external_nodes.isdisjoint(edge_nodes))
        self.assertEqual(nodes["slack_external"]["sub"], "RECEIVE-ONLY · UNCONFIRMED")
        self.assertIn("no business adapters wired", nodes["api_lambda"]["sub"])
        self.assertFalse(
            any(
                {edge["from"], edge["to"]} == {"api_lambda", "integration_api"}
                for edge in spec["edges"]
            )
        )
        self.assertIn("no Slack-to-J-Career path", spec["footer"])
        self.assertIn("no line to SaaS", spec["footer"])
        self.assertTrue(
            {"cloudfront", "apigateway", "lambda"}.issubset(
                {node["icon"] for node in spec["nodes"]}
            )
        )

    def test_public_gallery_links_every_delivery_format(self) -> None:
        landing = (ROOT / "index.html").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertEqual(landing.count('class="animated-flow-card '), 1)
        self.assertEqual(landing.count('class="animated-flow-card"'), 1)
        self.assertIn('id="animated-flow-gallery"', landing)
        for stem in DIAGRAMS:
            for extension in ("svg", "png", "gif", "mp4"):
                asset = f"assets/{stem}.{extension}"
                self.assertIn(asset, landing)
            self.assertIn(f"assets/{stem}.svg", readme)
            self.assertIn(f"assets/{stem}.gif", readme)
            self.assertIn(f"assets/{stem}.mp4", readme)


if __name__ == "__main__":
    unittest.main()
