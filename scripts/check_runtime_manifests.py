#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("::error::PyYAML이 필요함")
    raise SystemExit(2)


ENDPOINT_PATH = Path("src/runtime/contracts/endpoint_test_sample.yaml")
ARTIFACT_PATH = Path("src/runtime/contracts/application_artifacts.yaml")
ASIS_OUTPUTS_PATH = Path("terraform/asis/outputs.tf")
ASIS_COMPUTE_LOCALS_PATH = Path("terraform/asis/compute/locals.tf")
ASIS_COMPUTE_MAIN_PATH = Path("terraform/asis/compute/main.tf")

ENDPOINT_TOP_KEYS = {
    "schema_version", "execution_status", "synthetic_only", "terraform_managed",
    "fleet_inventory", "test_sample", "profiles",
}
FLEET_KEYS = {"boundary", "windows", "macos", "source_ref"}
SAMPLE_KEYS = {"representative_of_fleet", "windows", "macos"}
PROFILE_KEYS = {
    "profile_id", "os_family", "os_version", "browser_name", "browser_version",
    "synthetic_persona", "allowed_flow_ids", "image_source_ref",
    "image_approval_ref", "evidence_ref",
}
ARTIFACT_TOP_KEYS = {
    "schema_version", "synthetic_only", "terraform_layer", "artifacts",
}
ARTIFACT_KEYS = {
    "service_id", "source_dir", "dockerfile_path", "terraform_model_ref",
    "build_status", "publish_status", "intended_source_revision",
    "build_context_sha256", "image_digest", "published_image_ref",
    "base_image_source_ref", "image_approval_ref", "build_evidence_ref",
    "publish_evidence_ref",
}
EXPECTED_PROFILES = {
    "WIN-01": ("windows", "candidate", ["candidate-journey"]),
    "WIN-02": ("windows", "recruiter", ["recruiter-journey"]),
    "WIN-03": ("windows", "administrator", ["admin-audit-read"]),
    "MAC-01": ("macos", "candidate", ["candidate-journey"]),
    "MAC-02": ("macos", "recruiter", ["recruiter-journey"]),
    "MAC-03": ("macos", "administrator", ["admin-audit-read"]),
}
EXPECTED_ARTIFACTS = {
    "web": (
        "src/runtime/web",
        "src/runtime/web/Dockerfile",
        "terraform/asis/compute/locals.tf::default_container_images.web",
    ),
    "api": (
        "src/runtime/api",
        "src/runtime/api/Dockerfile",
        "terraform/asis/compute/locals.tf::default_container_images.api",
    ),
    "agent": (
        "src/runtime/agent",
        "src/runtime/agent/Dockerfile",
        "terraform/asis/compute/locals.tf::default_container_images.agent",
    ),
    "llm-gateway": (
        "src/runtime/llm_gateway",
        "src/runtime/llm_gateway/Dockerfile",
        "terraform/asis/compute/locals.tf::default_container_images.llm-gateway",
    ),
}
EMPTY_UNBUILT_FIELDS = {
    "intended_source_revision", "build_context_sha256", "image_digest",
    "published_image_ref", "build_evidence_ref", "publish_evidence_ref",
}


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[object, object]:
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "duplicate mapping key",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def parse_yaml_text(text: str, label: str, errors: list[str]) -> dict[str, Any]:
    try:
        document = yaml.load(text, Loader=UniqueKeyLoader)
    except (yaml.YAMLError, TypeError):
        errors.append(f"{label}: YAML parse 또는 중복 key 오류")
        return {}
    if not isinstance(document, dict):
        errors.append(f"{label}: 최상위 mapping 필요")
        return {}
    return document


def load_yaml(path: Path, label: str, errors: list[str]) -> dict[str, Any]:
    try:
        return parse_yaml_text(path.read_text(encoding="utf-8"), label, errors)
    except OSError:
        errors.append(f"{label}: 파일을 읽을 수 없음")
        return {}


def require_exact_keys(
    value: object, expected: set[str], label: str, errors: list[str]
) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{label}: mapping 필요")
        return False
    actual = set(value)
    if actual != expected:
        errors.append(
            f"{label}: field 집합 불일치 "
            f"(missing={len(expected - actual)}, unknown={len(actual - expected)})"
        )
        return False
    return True


def require_value(
    value: object, expected: object, label: str, errors: list[str]
) -> None:
    if value != expected or type(value) is not type(expected):
        errors.append(f"{label}: 고정 계약값 불일치")


def require_internal_path(
    root: Path,
    raw: object,
    expected: str,
    kind: str,
    label: str,
    errors: list[str],
) -> None:
    if raw != expected or not isinstance(raw, str):
        errors.append(f"{label}: 고정 저장소 경로 불일치")
        return
    root_resolved = root.resolve()
    candidate = (root_resolved / raw).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        errors.append(f"{label}: 저장소 밖 경로 금지")
        return
    exists = candidate.is_dir() if kind == "dir" else candidate.is_file()
    if not exists:
        errors.append(f"{label}: 참조 대상이 없음")


def require_optional_approved_ref_pair(
    root: Path,
    source_ref: object,
    approval_ref: object,
    label: str,
    errors: list[str],
) -> None:
    if source_ref is None and approval_ref is None:
        return
    if not isinstance(source_ref, str) or not source_ref.strip():
        errors.append(f"{label}: source와 사람 승인 ref를 함께 기록해야 함")
        return
    if not isinstance(approval_ref, str) or not approval_ref.startswith("docs/current/"):
        errors.append(f"{label}: 사람 소유 docs/current 승인 ref 필요")
        return
    if "#" not in approval_ref:
        errors.append(f"{label}: 승인 ref에는 anchor 필요")
        return
    approval_path, approval_anchor = approval_ref.split("#", 1)
    path_parts = Path(approval_path).parts
    if ".." in path_parts or not approval_anchor.strip():
        errors.append(f"{label}: 승인 ref 경로와 anchor 형식 오류")
        return
    root_resolved = root.resolve()
    candidate = (root_resolved / approval_path).resolve()
    try:
        candidate.relative_to(root_resolved / "docs" / "current")
    except ValueError:
        errors.append(f"{label}: 승인 ref는 docs/current 내부 파일이어야 함")
        return
    try:
        text = candidate.read_text(encoding="utf-8")
    except OSError:
        errors.append(f"{label}: 승인 ref 파일이 없음")
        return
    headings = _markdown_heading_anchors(text)
    if approval_anchor not in headings:
        errors.append(f"{label}: 승인 ref anchor가 문서 heading과 일치하지 않음")
    banner = "\n".join(text.splitlines()[:30])
    required_patterns = {
        "status": r"(?m)^status:\s*approved\s*$",
        "approved_by": r"(?m)^approved_by:\s*(?!<)[^\s].+\s*$",
        "approved_at": r"(?m)^approved_at:\s*(\d{4}-\d{2}-\d{2})\s*$",
        "source_sha256": r"(?m)^source_sha256:\s*([0-9a-f]{64})\s*$",
        "approved_source_ref": r"(?m)^approved_source_ref:\s*(\S(?:.*\S)?)\s*$",
    }
    matches = {name: re.search(pattern, banner) for name, pattern in required_patterns.items()}
    missing = [name for name, match in matches.items() if match is None]
    if missing:
        errors.append(f"{label}: 승인 문두 배너 field 누락 ({', '.join(missing)})")
        return
    try:
        dt.date.fromisoformat(matches["approved_at"].group(1))  # type: ignore[union-attr]
    except ValueError:
        errors.append(f"{label}: approved_at 날짜 형식 오류")
    source_hash = matches["source_sha256"].group(1)  # type: ignore[union-attr]
    if source_hash == "0" * 64:
        errors.append(f"{label}: source_sha256 placeholder 금지")
    approved_source_ref = matches["approved_source_ref"].group(1)  # type: ignore[union-attr]
    if approved_source_ref != source_ref:
        errors.append(f"{label}: 승인 문서 approved_source_ref와 manifest source 불일치")


def _markdown_heading_anchors(text: str) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    for raw_heading in re.findall(r"(?m)^#{1,6}\s+(.+?)\s*#*\s*$", text):
        heading = re.sub(r"<[^>]+>", "", raw_heading).strip().lower()
        slug = "".join(
            character
            for character in heading
            if character.isalnum() or character in {" ", "-", "_"}
        )
        slug = re.sub(r"\s+", "-", slug).strip("-")
        if not slug:
            continue
        duplicate_index = counts.get(slug, 0)
        counts[slug] = duplicate_index + 1
        anchors.add(slug if duplicate_index == 0 else f"{slug}-{duplicate_index}")
    return anchors


def check_endpoint_document(document: dict[str, Any], root: Path) -> list[str]:
    errors: list[str] = []
    if not require_exact_keys(document, ENDPOINT_TOP_KEYS, "endpoint manifest", errors):
        return errors
    require_value(
        document.get("schema_version"),
        "jcareer-endpoint-test-sample-v1",
        "endpoint schema_version",
        errors,
    )
    require_value(
        document.get("execution_status"), "NOT_EXECUTED", "endpoint 실행 상태", errors
    )
    require_value(document.get("synthetic_only"), True, "endpoint 합성 전용", errors)
    require_value(
        document.get("terraform_managed"), False, "endpoint Terraform 비관리", errors
    )

    fleet = document.get("fleet_inventory")
    if require_exact_keys(fleet, FLEET_KEYS, "fleet inventory", errors):
        require_value(fleet.get("boundary"), "scenario-document-only", "fleet 경계", errors)
        require_value(fleet.get("windows"), 100, "fleet Windows 수", errors)
        require_value(fleet.get("macos"), 80, "fleet macOS 수", errors)
        require_value(
            fleet.get("source_ref"),
            "fleet/README.md#시나리오-inventory--구축하지-않는다",
            "fleet 출처",
            errors,
        )

    sample = document.get("test_sample")
    if require_exact_keys(sample, SAMPLE_KEYS, "endpoint test sample", errors):
        require_value(
            sample.get("representative_of_fleet"), False, "표본 대표성", errors
        )
        require_value(sample.get("windows"), 3, "표본 Windows 수", errors)
        require_value(sample.get("macos"), 3, "표본 macOS 수", errors)

    profiles = document.get("profiles")
    if not isinstance(profiles, list):
        errors.append("endpoint profiles: list 필요")
        return errors
    if len(profiles) != 6:
        errors.append("endpoint profiles: 정확히 6개 필요")
    seen: set[str] = set()
    for index, profile in enumerate(profiles):
        label = f"endpoint profile[{index}]"
        if not require_exact_keys(profile, PROFILE_KEYS, label, errors):
            continue
        profile_id = profile.get("profile_id")
        if not isinstance(profile_id, str) or profile_id not in EXPECTED_PROFILES:
            errors.append(f"{label}: 허용 profile_id 불일치")
            continue
        if profile_id in seen:
            errors.append(f"{label}: profile_id 중복")
        seen.add(profile_id)
        family, persona, flows = EXPECTED_PROFILES[profile_id]
        require_value(profile.get("os_family"), family, f"{label} OS family", errors)
        require_value(
            profile.get("synthetic_persona"), persona, f"{label} 합성 persona", errors
        )
        require_value(profile.get("allowed_flow_ids"), flows, f"{label} 허용 flow", errors)
        for planned_field in ("os_version", "browser_name", "browser_version"):
            planned = profile.get(planned_field)
            if planned is not None and (
                not isinstance(planned, str) or not planned.strip()
            ):
                errors.append(
                    f"{label}: {planned_field}는 null 또는 비어 있지 않은 문자열"
                )
        require_optional_approved_ref_pair(
            root,
            profile.get("image_source_ref"),
            profile.get("image_approval_ref"),
            f"{label} image",
            errors,
        )
        if profile.get("evidence_ref") is not None:
            errors.append(f"{label}: NOT_EXECUTED 상태에는 evidence_ref 금지")
    if seen != set(EXPECTED_PROFILES):
        errors.append("endpoint profiles: 고정 3 Windows/3 macOS ID 집합 불일치")
    return errors


def check_artifact_document(
    document: dict[str, Any], root: Path, outputs_text: str
) -> list[str]:
    errors: list[str] = []
    if not require_exact_keys(document, ARTIFACT_TOP_KEYS, "artifact manifest", errors):
        return errors
    require_value(
        document.get("schema_version"),
        "jcareer-application-artifacts-v1",
        "artifact schema_version",
        errors,
    )
    require_value(document.get("synthetic_only"), True, "artifact 합성 전용", errors)
    require_value(
        document.get("terraform_layer"), "asis-model-only", "artifact Terraform 경계", errors
    )
    output_contracts = (
        "model-only-runtime-images-not-provisioned",
        "evidence_present                 = false",
        'evidence_interpretation          = "source-state-declarations-only"',
        'application_artifact_state    = "UNBUILT_UNPUBLISHED"',
        'endpoint_test_sample_state    = "NOT_EXECUTED_NOT_TERRAFORM_MANAGED"',
    )
    if any(fragment not in outputs_text for fragment in output_contracts):
        errors.append("terraform/asis outputs: 미실행 runtime 계약 선언 누락")

    artifacts = document.get("artifacts")
    if not isinstance(artifacts, list):
        errors.append("artifacts: list 필요")
        return errors
    if len(artifacts) != 4:
        errors.append("artifacts: 정확히 네 앱 필요")
    seen: set[str] = set()
    for index, artifact in enumerate(artifacts):
        label = f"artifact[{index}]"
        if not require_exact_keys(artifact, ARTIFACT_KEYS, label, errors):
            continue
        service_id = artifact.get("service_id")
        if not isinstance(service_id, str) or service_id not in EXPECTED_ARTIFACTS:
            errors.append(f"{label}: 허용 service_id 불일치")
            continue
        if service_id in seen:
            errors.append(f"{label}: service_id 중복")
        seen.add(service_id)
        source_dir, dockerfile_path, model_ref = EXPECTED_ARTIFACTS[service_id]
        require_internal_path(
            root, artifact.get("source_dir"), source_dir, "dir", f"{label} source", errors
        )
        require_internal_path(
            root,
            artifact.get("dockerfile_path"),
            dockerfile_path,
            "file",
            f"{label} Dockerfile",
            errors,
        )
        require_value(
            artifact.get("terraform_model_ref"), model_ref, f"{label} Terraform ref", errors
        )
        require_value(
            artifact.get("build_status"), "UNBUILT", f"{label} build 상태", errors
        )
        require_value(
            artifact.get("publish_status"),
            "UNPUBLISHED",
            f"{label} publish 상태",
            errors,
        )
        for field in EMPTY_UNBUILT_FIELDS:
            if artifact.get(field) is not None:
                errors.append(
                    f"{label}: UNBUILT/UNPUBLISHED 상태에는 {field} 금지"
                )
        require_optional_approved_ref_pair(
            root,
            artifact.get("base_image_source_ref"),
            artifact.get("image_approval_ref"),
            f"{label} base image",
            errors,
        )
    if seen != set(EXPECTED_ARTIFACTS):
        errors.append("artifacts: 고정 네 서비스 ID 집합 불일치")
    _check_terraform_image_linkage(root, errors)
    return errors


def _check_terraform_image_linkage(root: Path, errors: list[str]) -> None:
    try:
        locals_text = (root / ASIS_COMPUTE_LOCALS_PATH).read_text(encoding="utf-8")
        main_text = (root / ASIS_COMPUTE_MAIN_PATH).read_text(encoding="utf-8")
    except OSError:
        errors.append("terraform/asis compute: image 연결 소스를 읽을 수 없음")
        return
    locals_without_comments = _strip_hcl_comments(locals_text)
    main_without_comments = _strip_hcl_comments(main_text)
    match = re.search(
        r"(?ms)^\s*services\s*=\s*\{(?P<body>.*?)^\s*\}\s*\n\s*ecr_repository_names\s*=",
        locals_without_comments,
    )
    if not match:
        errors.append("terraform/asis compute: services map 구조를 확인할 수 없음")
        return
    service_keys = set(re.findall(r"(?m)^\s{4}([a-z0-9-]+)\s*=\s*\{", match.group("body")))
    if service_keys != set(EXPECTED_ARTIFACTS):
        errors.append("terraform/asis compute: 네 service key 집합 불일치")
    locals_fragments = (
        "for service_name, _ in local.services :",
        "for service_name, repository_name in local.ecr_repository_names :",
    )
    container_image_assignments = re.findall(
        r"(?m)^\s*container_images\s*=\s*([^\r\n]+)", locals_without_comments
    )
    if (
        any(fragment not in locals_without_comments for fragment in locals_fragments)
        or [value.strip() for value in container_image_assignments]
        != ["merge(local.default_container_images, var.container_images)"]
    ):
        errors.append("terraform/asis compute: image map 연결 구조 불일치")
    task_block = _extract_hcl_block(
        main_without_comments, 'resource "aws_ecs_task_definition" "service"'
    )
    if task_block is None:
        errors.append("terraform/asis compute: ECS task image 연결 구조 불일치")
        return
    for_each_assignments = re.findall(
        r"(?m)^\s*for_each\s*=\s*([^\r\n]+)", task_block
    )
    image_assignments = re.findall(r"(?m)^\s*image\s*=\s*([^\r\n]+)", task_block)
    if (
        [value.strip() for value in for_each_assignments] != ["local.services"]
        or [value.strip() for value in image_assignments]
        != ["local.container_images[each.key]"]
    ):
        errors.append("terraform/asis compute: ECS task image 연결 구조 불일치")


def _strip_hcl_comments(text: str) -> str:
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(text):
        character = text[index]
        following = text[index + 1] if index + 1 < len(text) else ""
        if in_string:
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
            output.append(character)
            index += 1
            continue
        if character == "#" or (character == "/" and following == "/"):
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue
        if character == "/" and following == "*":
            index += 2
            while index + 1 < len(text) and text[index : index + 2] != "*/":
                if text[index] in "\r\n":
                    output.append(text[index])
                index += 1
            index = min(index + 2, len(text))
            continue
        output.append(character)
        index += 1
    return "".join(output)


def _extract_hcl_block(text: str, header: str) -> str | None:
    start = text.find(header)
    if start < 0:
        return None
    opening = text.find("{", start + len(header))
    if opening < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(opening, len(text)):
        character = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return text[opening + 1 : index]
    return None


def check(root: Path) -> list[str]:
    parse_errors: list[str] = []
    endpoint = load_yaml(root / ENDPOINT_PATH, str(ENDPOINT_PATH), parse_errors)
    artifacts = load_yaml(root / ARTIFACT_PATH, str(ARTIFACT_PATH), parse_errors)
    try:
        outputs = (root / ASIS_OUTPUTS_PATH).read_text(encoding="utf-8")
    except OSError:
        outputs = ""
        parse_errors.append(f"{ASIS_OUTPUTS_PATH}: 파일을 읽을 수 없음")
    return (
        parse_errors
        + check_endpoint_document(endpoint, root)
        + check_artifact_document(artifacts, root, outputs)
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="J-Career 미실행 endpoint/app artifact manifest 정적 검사"
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    errors = check(args.root)
    if errors:
        for error in errors:
            print(f"::error::{error}")
        return 1
    print("J-Career runtime manifest source check (판정 아님)")
    print("endpoint sample: Windows 3 + macOS 3, NOT_EXECUTED")
    print("application artifacts: 4 services, UNBUILT + UNPUBLISHED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
