#!/usr/bin/env python3
"""Validate the editable J-Career AWS diagram without AWS access.

The contract separates the unapplied ``terraform/asis`` topology,
runtime-source-only additions, optional integrations, and the disabled-by-
default serverless MLOps root. It makes no conformity or risk judgment.
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
import urllib.parse
import zlib
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


EXPECTED_RES_ICONS = {
    "mxgraph.aws4.bedrock",
    "mxgraph.aws4.cloudfront",
    "mxgraph.aws4.cloudtrail",
    "mxgraph.aws4.cloudwatch_2",
    "mxgraph.aws4.dynamodb",
    "mxgraph.aws4.elasticache",
    "mxgraph.aws4.fargate",
    "mxgraph.aws4.guardduty",
    "mxgraph.aws4.lambda",
    "mxgraph.aws4.rds",
    "mxgraph.aws4.route_53",
    "mxgraph.aws4.s3",
}

REQUIRED_RES_ICON_BY_CELL = {
    "route53": "mxgraph.aws4.route_53",
    "cloudfront": "mxgraph.aws4.cloudfront",
    "web": "mxgraph.aws4.fargate",
    "api": "mxgraph.aws4.fargate",
    "agent": "mxgraph.aws4.fargate",
    "llm-gateway": "mxgraph.aws4.fargate",
    "rds": "mxgraph.aws4.rds",
    "cache": "mxgraph.aws4.elasticache",
    "bedrock": "mxgraph.aws4.bedrock",
    "s3": "mxgraph.aws4.s3",
    "cloudwatch": "mxgraph.aws4.cloudwatch_2",
    "cloudtrail": "mxgraph.aws4.cloudtrail",
    "guardduty": "mxgraph.aws4.guardduty",
    "mlops-s3": "mxgraph.aws4.s3",
    "mlops-lambda": "mxgraph.aws4.lambda",
    "mlops-dynamodb": "mxgraph.aws4.dynamodb",
}

EXPECTED_STANDALONE_SHAPES = {
    "mxgraph.aws4.application_load_balancer",
    "mxgraph.aws4.client",
    "mxgraph.aws4.generic_firewall",
    "mxgraph.aws4.traditional_server",
}

REQUIRED_CELLS = {
    "bg": ("fillColor=#F5F5F5",),
    "title": ("J-Career AS-IS", "NOT DEPLOYED", "APPLY FORBIDDEN"),
    "candidate": ("지원자 고객", "shape=mxgraph.aws4.client"),
    "company-customer": ("기업 고객", "shape=mxgraph.aws4.client"),
    "cloud": (
        "AWS Cloud",
        "Terraform topology model",
        "container=1",
        "dropTarget=1",
        "fillColor=none",
    ),
    "route53": ("Route 53",),
    "cloudfront": ("CloudFront",),
    "waf": ("AWS WAF",),
    "vpc": (
        "2-AZ / 6 subnets",
        "container=1",
        "dropTarget=1",
        "fillColor=none",
    ),
    "publictier": ("PUBLIC TIER", "2 subnets", "container=1"),
    "apptier": ("APPLICATION TIER", "2 subnets", "container=1"),
    "datatier": ("DATA TIER", "2 subnets", "container=1"),
    "alb": ("Application", "Load Balancer"),
    "web": ("web", "SPA", "image URI only"),
    "api": ("api", "three-DB orchestrator", "Terraform wiring partial"),
    "agent": ("agent", "deterministic 70/20/10", "no model activation"),
    "llm-gateway": ("llm-gateway", "explanation only", "score effect NONE"),
    "bedrock-broker": ("Bedrock broker", "peer UID 11002", "explanation only"),
    "opendart-broker": ("OpenDART broker", "peer UID 11001", "no credential return"),
    "app-route-note": ("/agent/*", "/llm/*", "runtime lab denies direct ingress"),
    "rds": ("RDS PostgreSQL", "shared physical failure domain"),
    "member-db": ("jcareer_member", "Terraform URL modeled"),
    "company-db": ("jcareer_company", "bootstrap NOT IMPLEMENTED"),
    "outcome-db": (
        "jcareer_outcome",
        "runtime source only",
        "Terraform URL/role absent",
        "score/rank effect NONE",
    ),
    "cache": ("ElastiCache Redis", "endpoint injection NOT MODELED"),
    "bedrock": (
        "Amazon Bedrock",
        "CONDITIONAL",
        "default stub / live=false",
        "conditional IAM policy",
        "execution NOT EVIDENCED",
    ),
    "opendart-path": (
        "serverless OpenDART",
        "SQS FIFO",
        "Lambda",
        "DynamoDB result",
        "default 0 / 8 / 11",
        "role-bound sender policy",
        "DB direct access false",
        "NOT DEPLOYED",
    ),
    "opendart": ("OpenDART", "conditional external lookup", "score effect NONE"),
    "endpoint-samples": (
        "가상 J사 업무망·정보처리시스템 선언 경계",
        "AWS 흐름과 비연결",
        "container=1",
    ),
    "scenario-declared-systems": (
        "SCENARIO_DECLARED",
        "VPN + MFA",
        "UTM",
        "Slack",
        "자산대장 선언",
        "AWS 리소스 아님",
    ),
    "mentor-requested-systems": (
        "MENTOR_REQUESTED_UNVERIFIED",
        "IPS",
        "IDS",
        "rack",
        "구현/관찰 증거 없음",
    ),
    "windows-sample": (
        "Windows × 3",
        "NOT_DEPLOYED",
        "Image Builder definition 12",
        "endpoint deploy 9",
        "SSM-tunneled RDP",
    ),
    "macos-sample": (
        "macOS × 3",
        "NOT_DEPLOYED",
        "physical Mac / MDM source only",
        "HUMAN MDM",
    ),
    "endpoint-note": (
        "ingress 0",
        "one-time bootstrap",
        "expiry cleanup",
        "cookie purge",
        "NOT OBSERVED / NOT_DEPLOYED",
        "AWS 리소스",
        "AWS 경로와 연결하지 않는다",
    ),
    "mlops-root": (
        "terraform/serverless-mlops",
        "default disabled = 0 managed resources",
        "NOT DEPLOYED / NOT INVOKED",
        "container=1",
    ),
    "mlops-exporter": ("source-only exporter", "synthetic member + company DB"),
    "mlops-s3": ("S3 feature snapshot", "if enabled"),
    "mlops-lambda": ("Lambda challenger", "runtime stage only"),
    "mlops-dynamodb": ("DynamoDB run state", "if enabled"),
    "mlops-human": ("TRAINED_PENDING_HUMAN_REVIEW", "no agent wiring"),
    "mlops-note": ("SSE-S3", "no schedule", "no automatic activation"),
    "planning-boundary": ("Planning / evaluation boundary", "no resources"),
    "trace-boundary": ("TRACE", "NOT IMPLEMENTED"),
    "oauth-boundary": (
        "openai-oauth",
        "security / licensing evaluation only",
        "NO INTEGRATION",
    ),
    "dashboard-boundary": (
        "Consultant dashboard separate",
        "no direct client AWS connection",
    ),
    "legend": (
        "last recorded AS-IS 110-add mock plan",
        "current AS-IS plan NOT REVALIDATED",
        "default to 0 resources",
        "process boundary, not IAM isolation",
        "no image build",
    ),
}

REQUIRED_EDGES = {
    ("candidate", "route53"),
    ("company-customer", "route53"),
    ("route53", "cloudfront"),
    ("cloudfront", "waf"),
    ("waf", "alb"),
    ("alb", "web"),
    ("alb", "api"),
    ("api", "agent"),
    ("api", "llm-gateway"),
    ("api", "rds"),
    ("api", "cache"),
    ("rds", "member-db"),
    ("rds", "company-db"),
    ("rds", "outcome-db"),
    ("llm-gateway", "bedrock-broker"),
    ("bedrock-broker", "bedrock"),
    ("api", "opendart-broker"),
    ("opendart-broker", "opendart-path"),
    ("opendart-path", "opendart"),
    ("mlops-exporter", "mlops-s3"),
    ("mlops-s3", "mlops-lambda"),
    ("mlops-lambda", "mlops-dynamodb"),
    ("mlops-lambda", "mlops-human"),
}

DECLARATION_ONLY_CELL_IDS = {
    "endpoint-samples",
    "scenario-declared-systems",
    "mentor-requested-systems",
    "windows-sample",
    "macos-sample",
    "endpoint-note",
}

MAIN_ICON_IDS = {
    "candidate", "company-customer", "route53", "cloudfront", "waf", "alb",
    "web", "api", "agent", "llm-gateway", "rds", "cache", "bedrock", "opendart",
}

SECONDARY_ICON_IDS = {
    "windows-sample", "macos-sample", "s3", "cloudwatch", "cloudtrail",
    "guardduty", "mlops-exporter", "mlops-s3", "mlops-lambda", "mlops-dynamodb",
}

SENSITIVE_OR_IDENTIFIER_PATTERNS = {
    "AWS ARN": re.compile(r"arn:aws", re.IGNORECASE),
    "12-digit account identifier": re.compile(r"(?<!\d)\d{12}(?!\d)"),
    "access key shape": re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}"),
    "secret assignment": re.compile(
        r"(?:secret|password|api[_-]?key)\s*[=:]\s*[^\s;&]+", re.IGNORECASE
    ),
}


def _geometry(cell: ET.Element) -> ET.Element | None:
    return cell.find("mxGeometry")


def validate_diagram(source: str) -> list[str]:
    errors: list[str] = []
    if "<!--" in source:
        errors.append("XML comments are not allowed in the draw.io source")
    try:
        root = ET.fromstring(source)
    except ET.ParseError as exc:
        return [f"XML parse failed: {exc}"]

    graph = root.find(".//mxGraphModel")
    if graph is None:
        return ["mxGraphModel is missing"]
    for name, expected in (
        ("pageWidth", "2400"), ("pageHeight", "1400"), ("dx", "2800"), ("dy", "1600")
    ):
        if graph.get(name) != expected:
            errors.append(f"{name} must be {expected}")

    cells = root.findall(".//mxCell")
    ids = [cell.get("id", "") for cell in cells]
    duplicates = sorted(key for key, count in Counter(ids).items() if key and count > 1)
    if duplicates:
        errors.append(f"duplicate cell IDs: {', '.join(duplicates)}")
    by_id = {cell.get("id", ""): cell for cell in cells if cell.get("id")}
    for root_id in ("0", "1"):
        if root_id not in by_id:
            errors.append(f"root cell {root_id} is missing")

    visible_ids = [cell.get("id") for cell in cells if cell.get("id") not in {"0", "1"}]
    if visible_ids[:2] != ["bg", "title"]:
        errors.append("background and title must be the first two visible cells")

    for cell_id, fragments in REQUIRED_CELLS.items():
        cell = by_id.get(cell_id)
        if cell is None:
            errors.append(f"required cell is missing: {cell_id}")
            continue
        combined = f"{cell.get('value', '')}\n{cell.get('style', '')}"
        for fragment in fragments:
            if fragment not in combined:
                errors.append(f"{cell_id}: required boundary text/style is missing ({fragment})")

    for cell_id, expected_icon in REQUIRED_RES_ICON_BY_CELL.items():
        cell = by_id.get(cell_id)
        if cell is not None and f"resIcon={expected_icon}" not in cell.get("style", ""):
            errors.append(f"{cell_id}: expected AWS resIcon {expected_icon}")

    actual_edges: set[tuple[str, str]] = set()
    for cell in cells:
        for attribute in ("parent", "source", "target"):
            reference = cell.get(attribute)
            if reference and reference not in by_id:
                errors.append(
                    f"{cell.get('id', '<no-id>')}: unknown {attribute} reference {reference}"
                )
        if cell.get("edge") != "1":
            continue
        source_id, target_id = cell.get("source"), cell.get("target")
        if not source_id or not target_id:
            errors.append(f"{cell.get('id', '<no-id>')}: edge lacks source or target")
        else:
            actual_edges.add((source_id, target_id))
            declaration_endpoint = (
                source_id
                if source_id in DECLARATION_ONLY_CELL_IDS
                else target_id if target_id in DECLARATION_ONLY_CELL_IDS else None
            )
            if declaration_endpoint is not None:
                errors.append(
                    f"{cell.get('id')}: declaration-only cell must not have flow edge "
                    f"({declaration_endpoint})"
                )
            if source_id in by_id and target_id in by_id:
                source_parent = by_id[source_id].get("parent")
                target_parent = by_id[target_id].get("parent")
                if source_parent != target_parent and cell.get("parent") != "1":
                    errors.append(f"{cell.get('id')}: cross-container edge must have parent=1")
        geometry = _geometry(cell)
        if geometry is None or geometry.get("relative") != "1":
            errors.append(f"{cell.get('id', '<no-id>')}: relative edge geometry is missing")
        style = cell.get("style", "")
        if not all(token in style for token in ("exitX=", "exitY=", "entryX=", "entryY=")):
            errors.append(f"{cell.get('id', '<no-id>')}: explicit edge anchors are missing")
    for source_id, target_id in sorted(REQUIRED_EDGES - actual_edges):
        errors.append(f"required flow edge is missing: {source_id} -> {target_id}")

    for cell in cells:
        cell_id = cell.get("id", "")
        style = cell.get("style", "")
        group_shape = "shape=mxgraph.aws4.group_" in style
        if group_shape and not all(
            token in style for token in ("container=1", "dropTarget=1", "fillColor=none")
        ):
            errors.append(f"{cell_id}: AWS group container boundary is incomplete")
        res_match = re.search(r"resIcon=([^;]+)", style)
        if res_match and res_match.group(1) not in EXPECTED_RES_ICONS:
            errors.append(f"{cell_id}: unverified AWS resIcon {res_match.group(1)}")
        shape_match = re.search(r"shape=(mxgraph\.aws4\.[^;]+)", style)
        if shape_match and not group_shape and not res_match:
            shape = shape_match.group(1)
            if shape not in EXPECTED_STANDALONE_SHAPES:
                errors.append(f"{cell_id}: unverified standalone AWS shape {shape}")
        if (res_match or shape_match) and not group_shape and "strokeColor=#ffffff" not in style:
            errors.append(f"{cell_id}: AWS service icon requires a white stroke")

        if cell_id in MAIN_ICON_IDS | SECONDARY_ICON_IDS:
            geometry = _geometry(cell)
            if geometry is None:
                errors.append(f"{cell_id}: icon geometry is missing")
                continue
            expected_size = "78" if cell_id in MAIN_ICON_IDS else "65"
            if geometry.get("width") != expected_size or geometry.get("height") != expected_size:
                errors.append(f"{cell_id}: icon must be {expected_size}x{expected_size}")

    for description, pattern in SENSITIVE_OR_IDENTIFIER_PATTERNS.items():
        if pattern.search(source):
            errors.append(f"diagram contains prohibited {description}")
    return errors


def _png_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("PNG signature is missing")
    offset = 8
    chunks: list[tuple[bytes, bytes]] = []
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("PNG chunk is truncated")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        end = offset + 12 + length
        if end > len(data):
            raise ValueError("PNG chunk payload is truncated")
        chunks.append((chunk_type, data[offset + 8 : offset + 8 + length]))
        offset = end
        if chunk_type == b"IEND":
            break
    return chunks


def validate_png_export(data: bytes) -> list[str]:
    """Check that a PNG carries the editable metadata made by draw.io ``-e``."""

    try:
        chunks = _png_chunks(data)
    except ValueError as exc:
        return [str(exc)]
    chunk_types = {chunk_type for chunk_type, _ in chunks}
    if not {b"IHDR", b"IDAT", b"IEND"}.issubset(chunk_types):
        return ["PNG lacks required IHDR/IDAT/IEND chunks"]
    embedded_documents: list[bytes] = []
    for chunk_type, payload in chunks:
        if chunk_type == b"tEXt" and payload.startswith(b"mxfile\x00"):
            embedded_documents.append(payload.split(b"\x00", 1)[1])
        elif chunk_type == b"zTXt":
            try:
                keyword, compressed = payload.split(b"\x00", 1)
                if keyword not in {b"mxfile", b"mxGraphModel"} or compressed[:1] != b"\x00":
                    continue
                decoded = zlib.decompress(compressed[1:])
                if decoded.startswith(b"%3C"):
                    decoded = urllib.parse.unquote_to_bytes(decoded.decode("ascii"))
                embedded_documents.append(decoded)
            except (ValueError, zlib.error, UnicodeDecodeError):
                return ["PNG draw.io zTXt metadata is malformed"]
    if not any(b"<mxfile" in document and b"<mxGraphModel" in document for document in embedded_documents):
        return ["PNG lacks embedded draw.io mxfile metadata; export with -e"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("diagram", type=Path)
    parser.add_argument("--png", type=Path, help="optional editable draw.io PNG export")
    args = parser.parse_args()
    try:
        source = args.diagram.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"diagram read failed: {exc}", file=sys.stderr)
        return 1
    errors = validate_diagram(source)
    if args.png is not None:
        try:
            png_data = args.png.read_bytes()
        except OSError as exc:
            errors.append(f"PNG read failed: {exc}")
        else:
            errors.extend(validate_png_export(png_data))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    cell_count = source.count("<mxCell ")
    edge_count = source.count(' edge="1"')
    png_status = "embedded PNG checked" if args.png is not None else "PNG not requested"
    print(
        "J-Career AWS draw.io source contract: PASS "
        f"(cells={cell_count}, edges={edge_count}, {png_status}, AWS not accessed)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
