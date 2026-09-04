from __future__ import annotations

import json
import re
import struct
import unittest
import xml.etree.ElementTree as ET
import zlib
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


def decoded_png_rows(path: Path) -> tuple[int, int, int, list[bytearray]]:
    """Decode the 8-bit RGB/RGBA PNG subset emitted by the render pipeline."""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"not a PNG: {path}")

    cursor = 8
    compressed = bytearray()
    header: tuple[int, int, int, int, int, int, int] | None = None
    while cursor < len(data):
        length = struct.unpack(">I", data[cursor : cursor + 4])[0]
        kind = data[cursor + 4 : cursor + 8]
        payload = data[cursor + 8 : cursor + 8 + length]
        cursor += length + 12
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", payload)
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break

    if header is None:
        raise AssertionError(f"PNG IHDR missing: {path}")
    width, height, bit_depth, color_type, compression, filtering, interlace = header
    if (bit_depth, color_type, compression, filtering, interlace) not in {
        (8, 2, 0, 0, 0),
        (8, 6, 0, 0, 0),
    }:
        raise AssertionError(f"unsupported PNG encoding in {path}: {header}")

    channels = 3 if color_type == 2 else 4
    stride = width * channels
    raw = zlib.decompress(compressed)
    if len(raw) != height * (stride + 1):
        raise AssertionError(f"unexpected PNG payload length: {path}")

    rows: list[bytearray] = []
    offset = 0
    previous = bytearray(stride)

    def paeth(left: int, above: int, upper_left: int) -> int:
        estimate = left + above - upper_left
        distances = (
            abs(estimate - left),
            abs(estimate - above),
            abs(estimate - upper_left),
        )
        return (left, above, upper_left)[distances.index(min(distances))]

    for _ in range(height):
        filter_type = raw[offset]
        encoded = raw[offset + 1 : offset + 1 + stride]
        offset += stride + 1
        row = bytearray(stride)
        for index, value in enumerate(encoded):
            left = row[index - channels] if index >= channels else 0
            above = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = above
            elif filter_type == 3:
                predictor = (left + above) // 2
            elif filter_type == 4:
                predictor = paeth(left, above, upper_left)
            else:
                raise AssertionError(f"unsupported PNG filter {filter_type}: {path}")
            row[index] = (value + predictor) & 0xFF
        rows.append(row)
        previous = row
    return width, height, channels, rows


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

    def test_committed_png_frames_are_opaque_light_and_keep_service_labels_visible(self) -> None:
        for stem in STEMS:
            with self.subTest(stem=stem):
                spec = self.load_spec(stem)
                svg = (ASSETS / f"{stem}.svg").read_text(encoding="utf-8")
                width, height, channels, rows = decoded_png_rows(ASSETS / f"{stem}.png")
                total = width * height
                near_black = 0
                light = 0
                transparent = 0

                for row in rows:
                    for offset in range(0, len(row), channels):
                        red, green, blue = row[offset : offset + 3]
                        near_black += red < 48 and green < 48 and blue < 48
                        light += red > 220 and green > 220 and blue > 220
                        if channels == 4:
                            transparent += row[offset + 3] < 255

                self.assertEqual(transparent, 0, f"transparent pixels in {stem}")
                self.assertLess(near_black / total, 0.02, f"predominantly black frame: {stem}")
                self.assertGreater(light / total, 0.85, f"light background missing: {stem}")

                for x_start, y_start in (
                    (0, 0),
                    (width - 16, 0),
                    (0, height - 16),
                    (width - 16, height - 16),
                ):
                    light_corner_pixels = 0
                    for y in range(y_start, y_start + 16):
                        for x in range(x_start, x_start + 16):
                            offset = x * channels
                            red, green, blue = rows[y][offset : offset + 3]
                            light_corner_pixels += red > 220 and green > 220 and blue > 220
                    self.assertGreater(
                        light_corner_pixels / 256,
                        0.90,
                        f"non-light canvas corner {(x_start, y_start)} in {stem}",
                    )

                service_nodes = [node for node in spec["nodes"] if not node["icon"].startswith("tile:")]
                for node in service_nodes:
                    with self.subTest(stem=stem, service=node["label"]):
                        self.assertIn(node["label"], svg)
                        x_start = max(0, node["x"] - 110)
                        x_end = min(width, node["x"] + 111)
                        y_start = max(0, node["y"] + 26)
                        y_end = min(height, node["y"] + 59)
                        label_ink = 0
                        for y in range(y_start, y_end):
                            row = rows[y]
                            for x in range(x_start, x_end):
                                offset = x * channels
                                red, green, blue = row[offset : offset + 3]
                                label_ink += max(red, green, blue) < 180
                        self.assertGreater(
                            label_ink,
                            250,
                            f"service label did not render visibly: {node['label']} in {stem}",
                        )

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
