#!/usr/bin/env python3
"""Check the public MLOps specification without network or AWS access."""

from __future__ import annotations

import hashlib
import json
import re
import struct
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "mlops" / "index.html"
PDF = ROOT / "mlops" / "JCAREER_MLOPS_SYSTEM_SPEC.pdf"
DRAWIO = ROOT / "terraform" / "serverless-mlops" / "JCAREER_MLOPS_FLOW.drawio"
SVG = ROOT / "terraform" / "serverless-mlops" / "JCAREER_MLOPS_FLOW.svg"
PNG = ROOT / "terraform" / "serverless-mlops" / "JCAREER_MLOPS_FLOW.drawio.png"
REPORT = ROOT / "mlops" / "VERIFICATION.json"
ASIS_PAGE = ROOT / "terraform" / "asis" / "index.html"
ASIS_ARCHITECTURE = ROOT / "terraform" / "asis" / "architecture.html"
PLATFORM_SVG = ROOT / "assets" / "JCAREER_PLATFORM_ANIMATED.svg"
PLATFORM_PNG = ROOT / "assets" / "JCAREER_PLATFORM_ANIMATED.png"
PLATFORM_SPEC = ROOT / "assets" / "JCAREER_PLATFORM_ANIMATED.spec.json"
FULL_INFRA_SVG = ROOT / "assets" / "JCAREER_FULL_INFRA_ANIMATED.svg"
FULL_INFRA_PNG = ROOT / "assets" / "JCAREER_FULL_INFRA_ANIMATED.png"
FULL_INFRA_SPEC = ROOT / "assets" / "JCAREER_FULL_INFRA_ANIMATED.spec.json"
FULL_INFRA_DRAWIO = ROOT / "terraform" / "asis" / "JCAREER_FULL_INFRA.drawio"
FULL_INFRA_GUIDE = ROOT / "terraform" / "asis" / "JCAREER_FULL_INFRA.md"

EXPECTED_COMMANDS = [
    "python -B scripts/check_serverless_mlops_static.py --root .",
    "python -B tests/test_serverless_mlops_static.py",
    "python -B -m unittest src/mlops/tests/test_synthetic_pipeline.py",
    "terraform -chdir=terraform/serverless-mlops fmt -check -recursive",
    "terraform -chdir=<temporary-source-copy> init -backend=false -input=false -lockfile=readonly",
    "terraform -chdir=<temporary-source-copy> validate -no-color",
    "terraform -chdir=<temporary-source-copy> test -test-directory=tests -no-color",
    "terraform -chdir=<temporary-source-copy> plan -input=false -lock=false -refresh=false (saved plan path outside repository)",
    "node --check mlops/app.js",
    "node --check assets/motion.js",
    "node scripts/finalize_animated_arch.mjs --check",
    "node scripts/finalize_animated_arch.mjs assets/JCAREER_FULL_INFRA_ANIMATED.svg --spec=assets/JCAREER_FULL_INFRA_ANIMATED.spec.json --check",
    "node scripts/check_public_ui.mjs",
    "node scripts/render_spec_pdf.mjs mlops/index.html mlops/JCAREER_MLOPS_SYSTEM_SPEC.pdf",
    "python -B scripts/update_public_mlops_evidence.py",
    "python -B scripts/check_public_mlops.py",
]

EXPECTED_NOTES = [
    "No AWS credentials were used.",
    "No AWS API, terraform apply/destroy, or Terraform state inspection was performed.",
    "Terraform init, validate, mock tests, and the disabled plan ran from a temporary source copy outside the repository.",
    "bootstrap/runtime counts were checked only with Terraform mock_provider tests.",
    "The disabled default plan used the ordinary provider configuration with AWS validation disabled by the configuration and planned zero managed resources.",
    "All nine architecture states were opened and checked for the selected button, active diagram layer, visible diagram media, detail link, full-map asset, and 390px overflow by scripts/check_public_ui.mjs.",
    "Five public pages were checked at 390px and 1440px for overflow, canonical and Open Graph metadata, touch action, and keyboard focus; MLOps aria-controls was also checked.",
    "MLOps stage URL state, invalid-stage fallback, and browser history were checked by scripts/check_public_ui.mjs.",
    "Eight motion checks covered the carousel, MLOps stage rail, animated architecture, manual motion toggle, and reduced-motion fallback.",
    "The animated architecture source hash, 15 nodes, 11 edges, 17 motion dots, 1480x820 PNG, and manual visual review were recorded together.",
    "The full infrastructure source hash, 27 nodes, 21 edges, 21 motion dots, 1780x1160 PNG, editable draw.io source, and manual visual review were recorded together.",
    "The MLOps PDF was rendered from mlops/index.html and carries that source file's SHA-256 marker.",
    "The recent three-logical-database outcome delta is documented as unmerged and is not included in these PASS results.",
]

GENERATED_RESULT_NAMES = {
    "challenger_model.json",
    "dataset_manifest.json",
    "evaluation_observations.json",
    "pipeline_run_receipt.json",
    "ranking_dataset.csv",
    "source_read_receipt.json",
}

TEXT_SUFFIXES = {
    "",
    ".css",
    ".csv",
    ".drawio",
    ".hcl",
    ".html",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".sh",
    ".svg",
    ".tf",
    ".txt",
    ".yml",
    ".yaml",
}


def is_hash_text_artifact(path: Path) -> bool:
    return (
        path.suffix.lower() in TEXT_SUFFIXES
        or path.suffix.lower() == ".mjs"
        or path.name.startswith("Dockerfile.")
    )


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.links: list[str] = []
        self.stage_tabs = 0
        self.stage_items = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(str(values["id"]))
        for name in ("href", "src"):
            if values.get(name):
                self.links.append(str(values[name]))
        if values.get("data-stage-tab") is not None:
            self.stage_tabs += 1
        if values.get("data-stage") is not None:
            self.stage_items += 1


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        signature = stream.read(24)
    if signature[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("diagram is not a PNG")
    return struct.unpack(">II", signature[16:24])


def local_target(page: Path, raw_link: str) -> Path | None:
    parsed = urlsplit(raw_link)
    if parsed.scheme or parsed.netloc or raw_link.startswith("#"):
        return None
    relative = unquote(parsed.path)
    if not relative:
        return None
    target = (page.parent / relative).resolve()
    return target / "index.html" if target.is_dir() else target


def workspace_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(ROOT).parts
    )


def evidence_scope_files() -> list[Path]:
    """Files whose hashes bind the published MLOps claims to this source copy."""
    roots = (
        ROOT / "assets" / "aws",
        ROOT / "mlops",
        ROOT / "src" / "mlops",
        ROOT / "terraform" / "serverless-mlops",
    )
    explicit = {
        ROOT / ".gitignore",
        ROOT / "README.md",
        ROOT / "index.html",
        ROOT / "assets" / "site.css",
        ROOT / "assets" / "motion.js",
        ROOT / "assets" / "JCAREER_PLATFORM_ANIMATED.spec.json",
        ROOT / "assets" / "JCAREER_PLATFORM_ANIMATED.svg",
        ROOT / "assets" / "JCAREER_PLATFORM_ANIMATED.png",
        FULL_INFRA_SPEC,
        FULL_INFRA_SVG,
        FULL_INFRA_PNG,
        ROOT / ".github" / "workflows" / "public-release-check.yml",
        ROOT / "scripts" / "browser_support.mjs",
        ROOT / "scripts" / "check_public_ui.mjs",
        ROOT / "scripts" / "finalize_animated_arch.mjs",
        ROOT / "scripts" / "check_public_mlops.py",
        ROOT / "scripts" / "check_serverless_mlops_static.py",
        ROOT / "scripts" / "render_spec_pdf.mjs",
        ROOT / "scripts" / "update_public_mlops_evidence.py",
        ROOT / "tests" / "run_all_tests.sh",
        ROOT / "tests" / "test_serverless_mlops_static.py",
        ROOT / "terraform" / "README.md",
        ROOT / "terraform" / "lab" / "index.html",
        ROOT / "terraform" / "asis" / "architecture.html",
        ROOT / "terraform" / "asis" / "build-spec.mjs",
        ROOT / "terraform" / "asis" / "index.html",
        ROOT / "terraform" / "asis" / "JCAREER_ASIS_FLOW.md",
        ROOT / "terraform" / "asis" / "README.md",
        FULL_INFRA_DRAWIO,
        FULL_INFRA_GUIDE,
        ROOT / "terraform" / "asis" / "validate-spec.ps1",
        ROOT / "src" / "runtime" / "ASIS_RUNTIME_SPEC.md",
        ROOT / "src" / "runtime" / "VERIFICATION.md",
        ROOT / "src" / "runtime" / "contracts" / "mentor_feedback_2026_08_28.json",
        ROOT / "src" / "runtime" / "tests" / "mentor_feedback_contract.py",
    }
    scoped = {
        path
        for base in roots
        if base.exists()
        for path in base.rglob("*")
        if path.is_file() and not is_forbidden_artifact(path)
    }
    scoped.update(path for path in explicit if path.is_file())
    scoped.discard(REPORT)
    return sorted(scoped)


def relative_name(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def is_forbidden_artifact(path: Path) -> bool:
    parts = {part.lower() for part in path.relative_to(ROOT).parts}
    name = path.name.lower()
    return (
        ".terraform" in parts
        or "__pycache__" in parts
        or name.endswith((".pyc", ".tfstate", ".tfplan", ".tfvars"))
        or ".tfstate." in name
        or name.endswith(".tfvars.json")
        or name == ".env"
        or (name.startswith(".env.") and name != ".env.example")
        or name in GENERATED_RESULT_NAMES
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    if is_hash_text_artifact(path):
        normalized = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        digest.update(normalized)
    else:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def check_pdf_source_binding(errors: list[str]) -> None:
    try:
        value = PDF.read_bytes()
    except OSError as exc:
        errors.append(f"MLOps PDF is unreadable: {exc}")
        return
    if not value.startswith(b"%PDF-"):
        errors.append("MLOps PDF header is invalid")
        return
    marker = re.search(
        rb"\n% JCAREER_HTML_SOURCE: ([^\r\n]+)\r?\n"
        rb"% JCAREER_HTML_SHA256: ([0-9a-f]{64})\r?\n?$",
        value[-512:],
    )
    if marker is None:
        errors.append("MLOps PDF does not carry its HTML source marker")
        return
    source_name = marker.group(1).decode("ascii", errors="replace")
    recorded_hash = marker.group(2).decode("ascii")
    if source_name != relative_name(PAGE) or recorded_hash != file_sha256(PAGE):
        errors.append("MLOps PDF source marker does not match mlops/index.html")
    page_objects = len(re.findall(rb"/Type\s*/Page\b", value))
    if page_objects != 10:
        errors.append(f"unexpected MLOps PDF page objects: {page_objects}")
    if re.search(rb"/URI\s*\(http://127\.0\.0\.1:", value):
        errors.append("MLOps PDF contains loopback links")


def check_evidence_report(errors: list[str]) -> None:
    try:
        report = json.loads(REPORT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"verification evidence is unreadable: {exc}")
        return

    if report.get("schema_version") != 2:
        errors.append("unexpected verification evidence schema")
    verified_at = str(report.get("verified_at"))
    verified_datetime: datetime | None = None
    try:
        verified_datetime = datetime.fromisoformat(verified_at)
    except ValueError:
        pass
    if (
        not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+09:00", verified_at)
        or verified_datetime is None
        or verified_datetime.utcoffset() != timedelta(hours=9)
    ):
        errors.append("verification evidence timestamp is missing or malformed")
    elif f"{verified_datetime.date().isoformat()} 기준 검사 결과" not in PAGE.read_text(encoding="utf-8"):
        errors.append("verification evidence date does not match the public MLOps page")
    if report.get("aws_api_calls") != 0 or report.get("terraform_apply_destroy") is not False:
        errors.append("verification evidence violates the AWS-free boundary")

    environment = report.get("environment")
    if (
        not isinstance(environment, dict)
        or set(environment) != {"python", "terraform", "node", "chrome"}
        or any(
            not re.fullmatch(r"\d+\.\d+\.\d+(?:\.\d+)?", str(version))
            for version in environment.values()
        )
    ):
        errors.append("verification evidence environment contract does not match")

    expected_results = {
        "terraform_fmt_check": "PASS",
        "terraform_validate": "PASS",
        "terraform_mock_stages": "3/3 PASS",
        "disabled_plan_resources": 0,
        "terraform_boundary_tests": "19/19 PASS",
        "synthetic_pipeline_tests": "22/22 PASS",
        "public_ui": "9/9 routes, 8/8 stage states, 5 pages at 390/1440px, motion 8/8 PASS",
        "pdf_source_binding": "PASS",
        "public_integrity": "PASS",
    }
    if report.get("results") != expected_results:
        errors.append("verification evidence result contract does not match")
    if report.get("commands") != EXPECTED_COMMANDS:
        errors.append("verification evidence command contract does not match")
    if report.get("notes") != EXPECTED_NOTES:
        errors.append("verification evidence note contract does not match")

    expected_evidence = {
        "public_ui": {
            "checker": "scripts/check_public_ui.mjs",
            "landing_routes": 9,
            "stage_states": 8,
            "viewports_css_px": [390, 1440],
            "page_viewport_checks": 10,
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
            "source": relative_name(PAGE),
            "output": relative_name(PDF),
            "source_sha256": file_sha256(PAGE),
        },
        "animated_architecture": {
            "spec": relative_name(PLATFORM_SPEC),
            "spec_sha256": file_sha256(PLATFORM_SPEC),
            "svg": relative_name(PLATFORM_SVG),
            "svg_sha256": file_sha256(PLATFORM_SVG),
            "png": relative_name(PLATFORM_PNG),
            "png_sha256": file_sha256(PLATFORM_PNG),
            "canvas_css_px": [1480, 820],
            "nodes": 15,
            "edges": 11,
            "motion_dots": 17,
            "visual_review": "PASS",
        },
        "full_infrastructure_architecture": {
            "spec": relative_name(FULL_INFRA_SPEC),
            "spec_sha256": file_sha256(FULL_INFRA_SPEC),
            "svg": relative_name(FULL_INFRA_SVG),
            "svg_sha256": file_sha256(FULL_INFRA_SVG),
            "png": relative_name(FULL_INFRA_PNG),
            "png_sha256": file_sha256(FULL_INFRA_PNG),
            "drawio": relative_name(FULL_INFRA_DRAWIO),
            "drawio_sha256": file_sha256(FULL_INFRA_DRAWIO),
            "canvas_css_px": [1780, 1160],
            "nodes": 27,
            "edges": 21,
            "motion_dots": 21,
            "visual_review": "PASS",
        },
    }
    if report.get("evidence") != expected_evidence:
        errors.append("verification evidence path and source-binding contract does not match")

    recorded = report.get("files")
    if not isinstance(recorded, dict):
        errors.append("verification evidence file hashes are missing")
        return
    expected_paths = {relative_name(path) for path in evidence_scope_files()}
    if set(recorded) != expected_paths:
        errors.append("verification evidence file set does not match the public MLOps scope")
        return
    mismatches = [
        name
        for name, expected_hash in recorded.items()
        if not re.fullmatch(r"[0-9a-f]{64}", str(expected_hash))
        or file_sha256(ROOT / Path(name)) != expected_hash
    ]
    if mismatches:
        errors.append(f"verification evidence hash mismatch: {len(mismatches)}")


def check() -> list[str]:
    errors: list[str] = []
    required = [
        ROOT / "index.html",
        PAGE,
        PDF,
        ROOT / "terraform" / "lab" / "index.html",
        ASIS_PAGE,
        ASIS_ARCHITECTURE,
        PLATFORM_SVG,
        PLATFORM_PNG,
        PLATFORM_SPEC,
        FULL_INFRA_SVG,
        FULL_INFRA_PNG,
        FULL_INFRA_SPEC,
        FULL_INFRA_DRAWIO,
        FULL_INFRA_GUIDE,
        DRAWIO,
        SVG,
        PNG,
        REPORT,
        ROOT / "scripts" / "browser_support.mjs",
        ROOT / "scripts" / "check_public_ui.mjs",
        ROOT / "scripts" / "render_spec_pdf.mjs",
        ROOT / "src" / "mlops" / "lambda_handler.py",
        ROOT / "src" / "mlops" / "run_snapshot_pipeline.py",
        ROOT / "terraform" / "serverless-mlops" / "main.tf",
        ROOT / "tests" / "test_serverless_mlops_static.py",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        errors.append("missing public MLOps files: " + ", ".join(missing))
        return errors

    public_urls = {
        ROOT / "index.html": "https://kshield-junior-17th-proj.github.io/jcareer-spec/",
        PAGE: "https://kshield-junior-17th-proj.github.io/jcareer-spec/mlops/",
        ROOT / "terraform" / "lab" / "index.html": "https://kshield-junior-17th-proj.github.io/jcareer-spec/terraform/lab/",
        ASIS_PAGE: "https://kshield-junior-17th-proj.github.io/jcareer-spec/terraform/asis/",
        ASIS_ARCHITECTURE: "https://kshield-junior-17th-proj.github.io/jcareer-spec/terraform/asis/architecture.html",
    }
    public_pages = tuple(public_urls)
    parsers: dict[Path, PageParser] = {}
    for public_page in public_pages:
        parser = PageParser()
        parser.feed(public_page.read_text(encoding="utf-8"))
        parsers[public_page] = parser
        duplicates = sorted({item for item in parser.ids if parser.ids.count(item) > 1})
        if duplicates:
            errors.append(
                f"duplicate HTML ids in {relative_name(public_page)}: "
                + ", ".join(duplicates)
            )

    parser = parsers[PAGE]
    text = PAGE.read_text(encoding="utf-8")
    if parser.stage_tabs != 8 or parser.stage_items != 7:
        errors.append(
            f"unexpected interactive stages: tabs={parser.stage_tabs}, items={parser.stage_items}"
        )

    public_texts = {
        public_page: public_page.read_text(encoding="utf-8")
        for public_page in public_pages
    }
    for public_page, public_text in public_texts.items():
        expected_url = public_urls[public_page]
        if not re.search(r'<meta name="theme-color" content="#[0-9a-fA-F]{6}">', public_text):
            errors.append(f"missing theme color: {relative_name(public_page)}")
        metadata_contract = (
            '<meta property="og:type" content="website">' in public_text
            and '<meta property="og:title"' in public_text
            and f'<meta property="og:url" content="{expected_url}">' in public_text
            and '<meta property="og:image" content="https://' in public_text
            and '<meta property="og:image:alt"' in public_text
            and '<meta name="twitter:image:alt"' in public_text
            and f'<link rel="canonical" href="{expected_url}">' in public_text
        )
        if not metadata_contract:
            errors.append(f"incomplete canonical or social metadata: {relative_name(public_page)}")

    if text.count('aria-controls="stage-list"') != 8 or 'id="stage-list"' not in text:
        errors.append("MLOps stage controls are not bound to the stage list")

    app_text = (ROOT / "mlops" / "app.js").read_text(encoding="utf-8")
    app_contract = (
        "URLSearchParams",
        "history.replaceState",
        "popstate",
        "validStages",
        "address.searchParams.set('stage', value)",
    )
    if any(token not in app_text for token in app_contract):
        errors.append("MLOps stage URL state contract is incomplete")

    asis_text = ASIS_PAGE.read_text(encoding="utf-8")
    architecture_text = ASIS_ARCHITECTURE.read_text(encoding="utf-8")
    asis_mlops_contract = (
        'id="mlops-overview"' in asis_text
        and asis_text.count('data-mlops-stage="') == 7
        and all(f'data-mlops-plan="{count}"' in asis_text for count in (0, 13, 14))
        and "기준 110개와 분리한 별도 계획이며 수치를 합산하지 않습니다" in asis_text
        and 'data-flow-button="mlops"' in architecture_text
        and 'data-flow-layer="mlops"' in architecture_text
        and "MLOps를 선택하면 빈 표식 대신 전용 7단계 도면으로 전환됩니다" in architecture_text
        and 'data-flow-media="mlops"' in architecture_text
        and "JCAREER_MLOPS_FLOW.svg" in architecture_text
        and "feature-only S3" in architecture_text
        and "TRAINED_PENDING_HUMAN_REVIEW" in architecture_text
        and "history.replaceState" in architecture_text
    )
    if not asis_mlops_contract:
        errors.append("AS-IS pages do not preserve the separate MLOps 0/13/14 and seven-stage boundary")

    source_readme = (ROOT / "src" / "mlops" / "README.md").read_text(encoding="utf-8")
    flow_readme = (
        ROOT / "terraform" / "serverless-mlops" / "JCAREER_MLOPS_FLOW.md"
    ).read_text(encoding="utf-8")
    source_file_contract = (
        "필수 3개 파일의 존재 여부와 크기, 해시, 허용 필드" in source_readme
        and "같은 prefix 아래에 다른 객체가 더 있는지는 확인하지 않으며 이를 거부하는 기능도 없다" in source_readme
        and "필수 3개 파일이 모두 있는지 확인합니다" in flow_readme
        and "파일 크기와 해시, 허용 항목도 검사" in flow_readme
        and "다른 객체까지 찾아 차단하지는 않습니다" in flow_readme
        and "정확한 파일 집합" not in source_readme
        and "정확한 파일 집합" not in flow_readme
    )
    if not source_file_contract:
        errors.append("MLOps source-file validation scope is overstated or incomplete")

    broken: list[str] = []
    for public_page, public_parser in parsers.items():
        for link in public_parser.links:
            target = local_target(public_page, link)
            if target is not None and not target.exists():
                broken.append(f"{relative_name(public_page)} -> {link}")
    if broken:
        errors.append("broken local links: " + ", ".join(sorted(set(broken))))

    required_phrases = (
        "사람 검토가 끝나지 않으면 추천 서비스와 연결하지 않음",
        "합성 데이터 전용 · 담당자 수동 실행 · 검토 전 서비스 반영 차단",
        "PostgreSQL 서비스 1개",
        "점수와 정렬 순위에는 사용하지 않습니다",
        "위 데이터 확장안은 아래 검사 범위에 포함되지 않습니다",
        "문맥 이해 범위",
        "AWS 배포 검증",
        "아주 이른 단계의 오류",
    )
    for phrase in required_phrases:
        if phrase not in text:
            errors.append(f"missing boundary phrase: {phrase}")

    landing_text = (ROOT / "index.html").read_text(encoding="utf-8")
    landing_phrases = (
        "구직자와 기업을 연결하는 채용 플랫폼",
        "Terraform 기준 설계 항목",
        "데이터 아키텍처 확장안",
        "논리 데이터베이스 3개",
        "구조 정의 완료 · API 참고 정보 연계 · 화면 연계 검토 중 · AWS 실행 결과는 별도 상태표에서 관리",
    )
    for phrase in landing_phrases:
        if phrase not in landing_text:
            errors.append(f"missing landing context phrase: {phrase}")

    flow_links = (
        "terraform/asis/architecture.html",
        "terraform/asis/architecture.html?flow=candidate",
        "terraform/asis/architecture.html?flow=recruiter",
        "terraform/asis/architecture.html?flow=explanation",
        "terraform/asis/architecture.html?flow=mlops",
        "terraform/asis/architecture.html?flow=workplace",
        "terraform/asis/architecture.html?flow=trace",
        "terraform/asis/architecture.html?flow=integrations",
        "terraform/asis/architecture.html?flow=operations",
    )
    if landing_text.count('class="flow-shortcuts"') != 1 or any(
        f'href="{href}"' not in landing_text for href in flow_links
    ):
        errors.append("landing service-to-infrastructure shortcuts are incomplete")
    architecture_image = re.search(
        r'<img[^>]+src="assets/JCAREER_PLATFORM_ANIMATED\.svg"[^>]*>',
        landing_text,
    )
    if architecture_image is None or 'loading="lazy"' not in architecture_image.group(0):
        errors.append("landing architecture image is missing lazy loading")

    blunt_public_phrases = (
        "운영 서비스 아님",
        "실제 운영 서비스 아님",
        "배포 확인 자료 아님",
        "가짜 회원",
        "가짜 기업",
        "가짜 자료",
    )
    for public_page in public_pages:
        public_text = public_page.read_text(encoding="utf-8")
        for phrase in blunt_public_phrases:
            if phrase in public_text:
                errors.append(
                    f"blunt public disclaimer in {relative_name(public_page)}: {phrase}"
                )

    platform_tree: ET.ElementTree | None = None
    try:
        ET.parse(DRAWIO)
        ET.parse(SVG)
        platform_tree = ET.parse(PLATFORM_SVG)
    except ET.ParseError as exc:
        errors.append(f"diagram XML parse failed: {exc}")
    try:
        if png_size(PNG) != (2400, 1400):
            errors.append(f"unexpected PNG size: {png_size(PNG)}")
    except (OSError, ValueError, struct.error) as exc:
        errors.append(f"PNG validation failed: {exc}")

    platform_svg_text = PLATFORM_SVG.read_text(encoding="utf-8")
    try:
        platform_spec = json.loads(PLATFORM_SPEC.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"animated architecture specification is unreadable: {exc}")
        platform_spec = {}
    platform_ids = (
        [element.attrib["id"] for element in platform_tree.iter() if "id" in element.attrib]
        if platform_tree is not None
        else []
    )
    if len(platform_ids) != len(set(platform_ids)):
        errors.append("animated architecture contains duplicate SVG IDs")
    canvas = platform_spec.get("canvas", {})
    nodes = platform_spec.get("nodes", [])
    edges = platform_spec.get("edges", [])
    journeys = platform_spec.get("journeys", [])
    expected_motion_count = sum(len(journey.get("hops", [])) for journey in journeys)
    expected_text = [
        platform_spec.get("title", ""),
        platform_spec.get("subtitle", ""),
        platform_spec.get("footer", ""),
        *(node.get("label", "") for node in nodes),
        *(node.get("sub", "") for node in nodes),
        *(group.get("label", "") for group in platform_spec.get("groups", [])),
    ]
    svg_visible_text = "".join(platform_tree.getroot().itertext()) if platform_tree else ""
    spec_ids = {node.get("id") for node in nodes}
    edge_endpoints_valid = all(
        edge.get("from") in spec_ids and edge.get("to") in spec_ids for edge in edges
    )
    if (
        canvas != {"w": 1480, "h": 820}
        or len(nodes) != 15
        or len(edges) != 11
        or expected_motion_count != 17
        or platform_svg_text.count('<path class="flow"') != len(edges)
        or any(value and value not in svg_visible_text for value in expected_text)
        or not edge_endpoints_valid
        or f'data-spec-sha256="{file_sha256(PLATFORM_SPEC)}"'
        not in platform_svg_text
    ):
        errors.append("animated architecture spec-to-SVG contract is out of sync")
    motion_count = platform_svg_text.count("<animateMotion ")
    guarded_motion_count = len(
        re.findall(r'<circle class="motion-dot"[^>]*><animateMotion ', platform_svg_text)
    )
    if (
        motion_count != expected_motion_count
        or guarded_motion_count != motion_count
        or "@media (prefers-reduced-motion: reduce){.motion-dot{display:none}}"
        not in platform_svg_text
    ):
        errors.append("animated architecture reduced-motion contract is incomplete")
    try:
        if png_size(PLATFORM_PNG) != (1480, 820):
            errors.append(f"unexpected animated architecture PNG size: {png_size(PLATFORM_PNG)}")
    except (OSError, ValueError, struct.error) as exc:
        errors.append(f"animated architecture PNG validation failed: {exc}")

    full_tree: ET.ElementTree | None = None
    full_drawio_tree: ET.ElementTree | None = None
    try:
        full_tree = ET.parse(FULL_INFRA_SVG)
        full_drawio_tree = ET.parse(FULL_INFRA_DRAWIO)
    except ET.ParseError as exc:
        errors.append(f"full infrastructure diagram XML parse failed: {exc}")
    try:
        full_spec = json.loads(FULL_INFRA_SPEC.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"full infrastructure specification is unreadable: {exc}")
        full_spec = {}
    full_svg_text = FULL_INFRA_SVG.read_text(encoding="utf-8")
    full_ids = (
        [element.attrib["id"] for element in full_tree.iter() if "id" in element.attrib]
        if full_tree is not None
        else []
    )
    full_nodes = full_spec.get("nodes", [])
    full_edges = full_spec.get("edges", [])
    full_journeys = full_spec.get("journeys", [])
    full_motion_count = sum(len(journey.get("hops", [])) for journey in full_journeys)
    full_spec_ids = {node.get("id") for node in full_nodes}
    full_expected_text = [
        full_spec.get("title", ""),
        full_spec.get("subtitle", ""),
        full_spec.get("footer", ""),
        *(node.get("label", "") for node in full_nodes),
        *(node.get("sub", "") for node in full_nodes),
        *(group.get("label", "") for group in full_spec.get("groups", [])),
    ]
    full_visible_text = "".join(full_tree.getroot().itertext()) if full_tree else ""
    full_boundary_text = " ".join(str(value) for value in full_expected_text)
    if (
        full_spec.get("canvas") != {"w": 1780, "h": 1160}
        or len(full_nodes) != 27
        or len(full_edges) != 21
        or full_motion_count != 21
        or len(full_ids) != len(set(full_ids))
        or full_svg_text.count('<path class="flow"')
        != sum(not edge.get("static", False) for edge in full_edges)
        or any(value and value not in full_visible_text for value in full_expected_text)
        or not all(
            edge.get("from") in full_spec_ids and edge.get("to") in full_spec_ids
            for edge in full_edges
        )
        or f'data-spec-sha256="{file_sha256(FULL_INFRA_SPEC)}"'
        not in full_svg_text
        or "GitHub Actions CI" not in full_boundary_text
        or "CI / AWS 경계" not in full_boundary_text
        or "업무망 PC 180대" not in full_boundary_text
        or "TRAINED_PENDING_HUMAN_REVIEW" not in full_boundary_text
        or "자동 배포 없음" not in full_boundary_text
    ):
        errors.append("full infrastructure spec-to-SVG contract is out of sync")
    full_guarded_motion_count = len(
        re.findall(r'<circle class="motion-dot"[^>]*><animateMotion ', full_svg_text)
    )
    if (
        full_svg_text.count("<animateMotion ") != full_motion_count
        or full_guarded_motion_count != full_motion_count
        or "@media (prefers-reduced-motion: reduce){.motion-dot{display:none}}"
        not in full_svg_text
    ):
        errors.append("full infrastructure reduced-motion contract is incomplete")
    if full_drawio_tree is not None:
        full_cells = list(full_drawio_tree.iter("mxCell"))
        full_cell_ids = {cell.attrib.get("id") for cell in full_cells}
        full_drawio_edges = [cell for cell in full_cells if cell.attrib.get("edge") == "1"]
        full_drawio_bound = all(
            edge.attrib.get("source") in full_cell_ids
            and edge.attrib.get("target") in full_cell_ids
            for edge in full_drawio_edges
        )
        if (
            len(full_cell_ids) != len(full_cells)
            or not full_drawio_edges
            or not full_drawio_bound
            or "mxgraph.aws4" not in FULL_INFRA_DRAWIO.read_text(encoding="utf-8")
        ):
            errors.append("full infrastructure draw.io topology contract is incomplete")
    try:
        if png_size(FULL_INFRA_PNG) != (1780, 1160):
            errors.append(
                f"unexpected full infrastructure PNG size: {png_size(FULL_INFRA_PNG)}"
            )
    except (OSError, ValueError, struct.error) as exc:
        errors.append(f"full infrastructure PNG validation failed: {exc}")

    all_files = workspace_files()
    forbidden_artifacts = [path for path in all_files if is_forbidden_artifact(path)]
    if forbidden_artifacts:
        errors.append(f"forbidden generated artifacts: {len(set(forbidden_artifacts))}")

    secret_patterns = (
        re.compile(rb"AKIA[0-9A-Z]{16}"),
        re.compile(rb"ASIA[0-9A-Z]{16}"),
        re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(rb"gh[pousr]_[A-Za-z0-9_]{20,}"),
        re.compile(rb"xox[baprs]-[A-Za-z0-9-]{20,}"),
    )
    secret_hits = 0
    for path in all_files:
        value = path.read_bytes()
        secret_hits += sum(len(pattern.findall(value)) for pattern in secret_patterns)
    if secret_hits:
        errors.append(f"credential-like patterns found: {secret_hits}")

    identifier_patterns = (
        re.compile(r"arn:(?:aws|aws-cn|aws-us-gov):[^\s<>'\"]*:\d{12}(?::|/|\b)"),
        re.compile(r"\b\d{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com\b"),
        re.compile(r"(?:account[_ -]?id|계정\s*식별자)[\s\"'=:\-]{1,12}\d{12}\b", re.IGNORECASE),
    )
    identifier_hits = 0
    for path in all_files:
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        value = path.read_text(encoding="utf-8", errors="ignore")
        identifier_hits += sum(len(pattern.findall(value)) for pattern in identifier_patterns)
        if path.name != ".terraform.lock.hcl":
            identifier_hits += len(
                re.findall(r"(?<![A-Za-z0-9])\d{12}(?![A-Za-z0-9])", value)
            )
    if identifier_hits:
        errors.append(f"account-identifier-like patterns found in repository: {identifier_hits}")

    check_pdf_source_binding(errors)
    check_evidence_report(errors)

    return errors


def main() -> int:
    errors = check()
    if errors:
        for error in errors:
            print(f"::error::{error}")
        return 1
    print("public MLOps specification: PASS")
    print("interactive stages: 7, PNG: 2400x1400, local links: PASS")
    print("forbidden artifacts: 0, credential/account-identifier-like patterns: 0")
    print("verification evidence hashes and PDF source binding: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
