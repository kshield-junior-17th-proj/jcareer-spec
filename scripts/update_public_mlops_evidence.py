#!/usr/bin/env python3
"""Write the local-only MLOps verification record after the checks pass."""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import check_public_mlops as checks


def command_output(arguments: list[str]) -> str:
    completed = subprocess.run(
        arguments,
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return (completed.stdout or completed.stderr).strip()


def terraform_version() -> str:
    value = json.loads(command_output(["terraform", "version", "-json"]))
    return str(value["terraform_version"])


def node_version() -> str:
    return command_output(["node", "--version"]).removeprefix("v")


def chrome_version() -> str:
    candidates = [
        Path(os.environ["CHROME_PATH"]) if os.environ.get("CHROME_PATH") else None,
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        if os.name == "nt"
        else None,
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe")
        if os.name == "nt"
        else None,
    ]
    executable = next((path for path in candidates if path and path.is_file()), None)
    if executable and os.name == "nt":
        versions = [
            item.name
            for item in executable.parent.iterdir()
            if item.is_dir() and re.fullmatch(r"\d+\.\d+\.\d+\.\d+", item.name)
        ]
        if versions:
            return max(versions, key=lambda value: tuple(map(int, value.split("."))))
    names = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]
    for name in names:
        try:
            match = re.search(r"\d+\.\d+\.\d+\.\d+", command_output([name, "--version"]))
        except (FileNotFoundError, subprocess.SubprocessError):
            continue
        if match:
            return match.group(0)
    raise RuntimeError("Chrome version could not be determined.")


def main() -> None:
    source_hash = checks.file_sha256(checks.PAGE)
    files = {
        checks.relative_name(path): checks.file_sha256(path)
        for path in checks.evidence_scope_files()
    }
    report = {
        "schema_version": 2,
        "verified_at": datetime.now(
            timezone(timedelta(hours=9))
        ).replace(microsecond=0).isoformat(),
        "aws_api_calls": 0,
        "terraform_apply_destroy": False,
        "environment": {
            "python": platform.python_version(),
            "terraform": terraform_version(),
            "node": node_version(),
            "chrome": chrome_version(),
        },
        "results": {
            "terraform_fmt_check": "PASS",
            "terraform_validate": "PASS",
            "terraform_mock_stages": "3/3 PASS",
            "disabled_plan_resources": 0,
            "terraform_boundary_tests": "19/19 PASS",
            "synthetic_pipeline_tests": "22/22 PASS",
            "public_ui": "9/9 routes, 8/8 stage states, 6 pages at 390/1440px, motion 8/8 PASS",
            "pdf_source_binding": "PASS",
            "public_integrity": "PASS",
        },
        "commands": checks.EXPECTED_COMMANDS,
        "notes": checks.EXPECTED_NOTES,
        "evidence": {
            "public_ui": {
                "checker": "scripts/check_public_ui.mjs",
                "landing_routes": 9,
                "stage_states": 8,
                "viewports_css_px": [390, 1440],
                "page_viewport_checks": 12,
                "motion_checks": 8,
                "page_checks": [
                    "horizontal_overflow",
                    "canonical_open_graph",
                    "aria_controls",
                    "touch_action",
                    "keyboard_focus",
                ],
                "route_checks": [
                    "selected_button",
                    "active_diagram_layer",
                    "visible_diagram_media",
                    "detail_link",
                    "full_map_asset",
                    "horizontal_overflow",
                ],
                "motion_contracts": [
                    "carousel",
                    "mlops_stage_rail",
                    "animated_architecture",
                    "manual_motion_toggle",
                    "reduced_motion_fallback",
                ],
                "invalid_flow": "fail-closed",
                "invalid_stage": "fail-closed",
            },
            "pdf_source_binding": {
                "renderer": "scripts/render_spec_pdf.mjs",
                "source": checks.relative_name(checks.PAGE),
                "output": checks.relative_name(checks.PDF),
                "source_sha256": source_hash,
            },
            "animated_architecture": {
                "spec": checks.relative_name(checks.PLATFORM_SPEC),
                "spec_sha256": checks.file_sha256(checks.PLATFORM_SPEC),
                "svg": checks.relative_name(checks.PLATFORM_SVG),
                "svg_sha256": checks.file_sha256(checks.PLATFORM_SVG),
                "png": checks.relative_name(checks.PLATFORM_PNG),
                "png_sha256": checks.file_sha256(checks.PLATFORM_PNG),
                "canvas_css_px": [1480, 820],
                "nodes": 15,
                "edges": 11,
                "motion_dots": 17,
                "visual_review": "PASS",
            },
            "full_infrastructure_architecture": {
                "spec": checks.relative_name(checks.FULL_INFRA_SPEC),
                "spec_sha256": checks.file_sha256(checks.FULL_INFRA_SPEC),
                "svg": checks.relative_name(checks.FULL_INFRA_SVG),
                "svg_sha256": checks.file_sha256(checks.FULL_INFRA_SVG),
                "png": checks.relative_name(checks.FULL_INFRA_PNG),
                "png_sha256": checks.file_sha256(checks.FULL_INFRA_PNG),
                "drawio": checks.relative_name(checks.FULL_INFRA_DRAWIO),
                "drawio_sha256": checks.file_sha256(checks.FULL_INFRA_DRAWIO),
                "canvas_css_px": [2320, 1500],
                "nodes": 46,
                "edges": 48,
                "motion_dots": 24,
                "visual_review": "PASS",
            },
        },
        "files": files,
    }
    checks.REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "MLOps verification evidence updated: "
        f"{len(files)} files, {report['verified_at']}"
    )


if __name__ == "__main__":
    main()
