from __future__ import annotations

import json
import re
import struct
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
STEMS = (
    "JCAREER_CANDIDATE_RECOMMENDATION_FLOW",
    "JCAREER_RECRUITER_TALENT_SEARCH_FLOW",
)
EXPECTED_AWS_ICONS = {
    "apigateway",
    "bedrock",
    "cloudfront",
    "cloudwatch",
    "cognito",
    "dynamodb",
    "ecs",
    "lambda",
    "s3",
    "sqs",
}


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise AssertionError(f"not a PNG with IHDR: {path}")
    return struct.unpack(">II", data[16:24])


def gif_metadata(path: Path) -> tuple[tuple[int, int], int]:
    data = path.read_bytes()
    if data[:6] not in {b"GIF87a", b"GIF89a"}:
        raise AssertionError(f"not a GIF: {path}")
    dimensions = struct.unpack("<HH", data[6:10])
    frames = data.count(b"\x21\xf9\x04")
    return dimensions, frames


def mp4_track_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    marker = data.find(b"tkhd")
    if marker < 4:
        raise AssertionError(f"MP4 tkhd box missing: {path}")
    box_start = marker - 4
    box_size = struct.unpack(">I", data[box_start:marker])[0]
    box_end = box_start + box_size
    if box_end > len(data) or box_size < 32:
        raise AssertionError(f"invalid MP4 tkhd box: {path}")
    width_fixed, height_fixed = struct.unpack(">II", data[box_end - 8:box_end])
    return width_fixed >> 16, height_fixed >> 16


class CandidateRecruiterFlowContract(unittest.TestCase):
    def load_spec(self, stem: str) -> dict:
        return json.loads((ASSETS / f"{stem}.spec.json").read_text(encoding="utf-8"))

    def test_specs_keep_truth_statuses_and_not_assets_explicit(self) -> None:
        for stem in STEMS:
            with self.subTest(stem=stem):
                spec = self.load_spec(stem)
                self.assertEqual(spec["canvas"], {"w": 1800, "h": 980})
                self.assertEqual(spec["status"], "LIVE_VERIFIED_SYNTHETIC_SERVERLESS_2026_09_01")
                self.assertEqual(set(spec["status_key"]), {"implemented", "proposed", "unconfirmed"})
                self.assertEqual(spec["not_assets"], ["TRACE", "JC-RECEIPT"])

                node_text = " ".join(
                    " ".join(str(node.get(key, "")) for key in ("id", "label", "sub", "icon"))
                    for node in spec["nodes"]
                )
                self.assertNotRegex(node_text, r"TRACE|JC-RECEIPT")
                self.assertIn("PROPOSED", node_text)
                self.assertIn("UNCONFIRMED", node_text)
                self.assertIn("LIVE", node_text)

                context_ids = {"enterprise_target", "customer_evidence", "tenant_evidence"}
                edge_ids = {edge["from"] for edge in spec["edges"]} | {edge["to"] for edge in spec["edges"]}
                self.assertTrue(context_ids.isdisjoint(edge_ids))

    def test_main_journeys_are_left_to_right_and_all_edges_are_orthogonal(self) -> None:
        for stem in STEMS:
            with self.subTest(stem=stem):
                spec = self.load_spec(stem)
                nodes = {node["id"]: node for node in spec["nodes"]}
                edges = {(edge["from"], edge["to"]): edge for edge in spec["edges"]}
                main = spec["journeys"][0]["hops"]
                self.assertEqual(len(main), 8)
                for source, target in main:
                    self.assertLess(nodes[source]["x"], nodes[target]["x"])
                    self.assertEqual(nodes[source]["y"], nodes[target]["y"])

                def anchor(node_id: str, side: str) -> tuple[int, int]:
                    node = nodes[node_id]
                    x, y = node["x"], node["y"]
                    return {
                        "t": (x, y - 23),
                        "b": (x, y + 23),
                        "l": (x - 23, y),
                        "r": (x + 23, y),
                    }[side]

                for edge in spec["edges"]:
                    points = [anchor(edge["from"], edge.get("fs", "r"))]
                    points.extend(tuple(point) for point in edge.get("mids", []))
                    points.append(anchor(edge["to"], edge.get("ts", "l")))
                    for first, second in zip(points, points[1:]):
                        self.assertTrue(
                            first[0] == second[0] or first[1] == second[1],
                            f"diagonal segment in {stem}: {edge}",
                        )

                for journey in spec["journeys"]:
                    for hop in journey["hops"]:
                        self.assertIn(tuple(hop), edges)

    def test_only_official_aws_icons_and_bounded_external_tiles_are_used(self) -> None:
        for stem in STEMS:
            with self.subTest(stem=stem):
                spec = self.load_spec(stem)
                icons = {node["icon"] for node in spec["nodes"]}
                aws_icons = {icon for icon in icons if not icon.startswith("tile:")}
                tiles = {icon for icon in icons if icon.startswith("tile:")}
                self.assertEqual(aws_icons, EXPECTED_AWS_ICONS)
                self.assertLessEqual(tiles, {"tile:external", "tile:generic"})

    def test_svg_png_gif_and_h264_mp4_deliverables(self) -> None:
        for stem in STEMS:
            with self.subTest(stem=stem):
                svg = (ASSETS / f"{stem}.svg").read_text(encoding="utf-8")
                root = ET.fromstring(svg)
                self.assertTrue(root.tag.endswith("svg"))
                self.assertEqual(svg.count("<animateMotion "), 17)
                self.assertNotIn("<image", svg)
                self.assertNotRegex(svg, r'(?:href|src)="https?://')
                icon_source = (ASSETS / "aws" / "README.md").read_bytes()
                self.assertIn(b"https://aws.amazon.com/architecture/icons/", icon_source)

                self.assertEqual(png_dimensions(ASSETS / f"{stem}.png"), (1800, 980))
                self.assertEqual(gif_metadata(ASSETS / f"{stem}.gif"), ((1800, 980), 36))

                mp4 = (ASSETS / f"{stem}.mp4").read_bytes()
                self.assertIn(b"ftyp", mp4[:32])
                self.assertIn(b"avc1", mp4)
                self.assertLess(mp4.find(b"moov"), mp4.find(b"mdat"))
                self.assertEqual(mp4_track_dimensions(ASSETS / f"{stem}.mp4"), (1800, 980))

    def test_gallery_is_self_contained_and_exposes_both_flows(self) -> None:
        gallery = (ASSETS / "JCAREER_ARCHITECTURE_FLOW_GALLERY.html").read_text(encoding="utf-8")
        self.assertEqual(gallery.count("data:image/svg+xml;base64,"), 2)
        self.assertEqual(gallery.count("data:image/gif;base64,"), 2)
        self.assertEqual(gallery.count("data:video/mp4;base64,"), 2)
        self.assertIsNone(re.search(r'(?:src|href)=["\'](?!data:|#)', gallery))
        for status in ("IMPLEMENTED", "PROPOSED", "UNCONFIRMED", "NOT-ASSET"):
            self.assertIn(status, gallery)
        self.assertIn("TRACE and JC-RECEIPT", gallery)

    def test_readme_links_every_format_and_public_gallery(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for stem in STEMS:
            for suffix in (".svg", ".gif", ".mp4", ".png"):
                self.assertIn(f"assets/{stem}{suffix}", readme)
        self.assertIn(
            "https://kshield-junior-17th-proj.github.io/jcareer-spec/assets/"
            "JCAREER_ARCHITECTURE_FLOW_GALLERY.html",
            readme,
        )


if __name__ == "__main__":
    unittest.main()
