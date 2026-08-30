#!/usr/bin/env python3
"""tfsec/Checkov 결과에서 EXPECTED_FINDINGS 미선언 항목을 정규화한다."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import yaml


def norm_address(value: object) -> str:
    address = str(value or "").strip()
    if not address:
        return ""
    address = address.split(":")[-1].strip()
    if address.startswith("module."):
        parts = address.split(".")
        if len(parts) > 2:
            address = ".".join(parts[2:])
    return address


def repo_path(value: object) -> str:
    path = str(value or "").replace("\\", "/")
    marker = "/terraform/asis/"
    if marker in path:
        return "terraform/asis/" + path.split(marker, 1)[1]
    return path.lstrip("/")


def declared_scanner_rules(spec_path: Path) -> tuple[set[tuple[str, str, str]], int]:
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    declared: set[tuple[str, str, str]] = set()
    incomplete = 0
    for finding in spec.get("findings", []):
        if finding.get("type") != "SCANNER":
            continue
        assertion = finding.get("scanner_assertion") or {}
        tool = str(assertion.get("tool") or "").strip().lower()
        rule_id = str(assertion.get("rule_id") or "").strip()
        if not tool or not rule_id:
            incomplete += 1
            continue
        declared.add((tool, rule_id, norm_address(assertion.get("resource_address"))))
    return declared, incomplete


def is_declared(item: dict[str, object], declared: set[tuple[str, str, str]]) -> bool:
    tool = str(item["tool"])
    rule_id = str(item["rule_id"])
    address = str(item["resource_address"])
    return (tool, rule_id, "") in declared or (tool, rule_id, address) in declared


def load_tfsec(path: Path) -> list[dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    findings = []
    for result in data.get("results", []):
        location = result.get("location") or {}
        findings.append(
            {
                "tool": "tfsec",
                "rule_id": str(result.get("long_id") or result.get("rule_id") or ""),
                "native_rule_id": str(result.get("rule_id") or ""),
                "title": str(result.get("rule_description") or result.get("description") or ""),
                "severity": str(result.get("severity") or "UNKNOWN"),
                "resource_address": norm_address(result.get("resource")),
                "file_path": repo_path(location.get("filename")),
                "line_start": location.get("start_line"),
                "line_end": location.get("end_line"),
            }
        )
    return findings


def load_checkov(path: Path) -> list[dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    findings = []
    for result in data.get("results", {}).get("failed_checks", []):
        line_range = result.get("file_line_range") or [None, None]
        findings.append(
            {
                "tool": "checkov",
                "rule_id": str(result.get("check_id") or ""),
                "native_rule_id": str(result.get("check_id") or ""),
                "title": str(result.get("check_name") or ""),
                "severity": str(result.get("severity") or "UNAVAILABLE"),
                "resource_address": norm_address(result.get("resource")),
                "file_path": repo_path(result.get("repo_file_path") or result.get("file_path")),
                "line_start": line_range[0] if line_range else None,
                "line_end": line_range[1] if len(line_range) > 1 else None,
            }
        )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--tfsec", required=True, type=Path)
    parser.add_argument("--checkov", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    declared, incomplete = declared_scanner_rules(args.spec)
    raw = load_tfsec(args.tfsec) + load_checkov(args.checkov)
    unique = {
        (str(item["tool"]), str(item["rule_id"]), str(item["resource_address"])): item
        for item in raw
        if item["rule_id"]
    }
    unexpected = sorted(
        (item for item in unique.values() if not is_declared(item, declared)),
        key=lambda item: (str(item["tool"]), str(item["rule_id"]), str(item["resource_address"])),
    )
    for item in unexpected:
        item["classification"] = "NOT_DECLARED_IN_EXPECTED_FINDINGS"

    by_tool = Counter(str(item["tool"]) for item in unexpected)
    payload = {
        "schema": "unexpected-findings/1",
        "classification_status": "PROVISIONAL" if incomplete else "COMPLETE",
        "reason": (
            f"EXPECTED_FINDINGS has {incomplete} SCANNER entries without tool/rule_id; "
            "unmatched scanner findings remain human-review input."
            if incomplete
            else "Scanner findings not matched by an approved EXPECTED_FINDINGS rule."
        ),
        "source_files": [args.tfsec.as_posix(), args.checkov.as_posix()],
        "expected_spec": args.spec.as_posix(),
        "raw_finding_count": len(raw),
        "deduplicated_finding_count": len(unique),
        "unexpected_finding_count": len(unexpected),
        "by_tool": dict(sorted(by_tool.items())),
        "findings": unexpected,
    }
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"unexpected findings: {len(unexpected)} "
        f"(deduplicated {len(unique)}, raw {len(raw)}, incomplete spec {incomplete})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
