#!/usr/bin/env python3
"""fleet 합성 endpoint review pack 의 fail-closed 정적 검사.

AWS·Docker·네트워크 호출을 하지 않는다. 파일이 없거나 파싱되지 않으면 통과가 아니라
실패다. 이 검사는 통제 충족 여부·적합성·잔여위험을 판정하지 않으며, 판정 어휘가
데이터에 섞여 들어오는 것을 오히려 거부한다.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("::error::PyYAML이 필요함")
    raise SystemExit(2)


PACK_PATH = Path("fleet/inventory/endpoint_review_pack.yaml")
INVENTORY_PATH = Path("fleet/inventory/ENDPOINT_REVIEW_INVENTORY.md")
UPSTREAM_PATH = Path("src/runtime/contracts/endpoint_test_sample.yaml")

ASSET_ID_NAMESPACE = "jcareer-fleet-endpoint-review-v1"
OS_SHORT = {"windows": "WIN", "macos": "MAC"}

PACK_TOP_KEYS = {
    "schema_version", "pack_status", "synthetic_only", "devices_exist",
    "procurement_status", "terraform_managed", "aws_managed",
    "asset_id_namespace", "asset_id_recipe", "upstream_contract_ref",
    "scenario_source_refs", "fleet_inventory", "review_sample",
    "posture_items", "scenario_declared_posture", "devices",
}
FLEET_KEYS = {"boundary", "windows", "macos"}
SAMPLE_KEYS = {"representative_of_fleet", "windows", "macos"}
DEVICE_KEYS = {
    "profile_id", "asset_id", "os_family", "synthetic_persona",
    "allowed_flow_ids", "posture",
}
POSTURE_ITEM_KEYS = {"observation_state", "recorded_value", "method_ref"}
POSTURE_ITEMS = ["os", "browser", "edr", "vpn"]

SCENARIO_POSTURE_KEYS = {"statement_kind", "windows", "macos"}
SCENARIO_DECLARED = {
    "windows": {
        "os": "AD_JOINED", "browser": "NOT_DECLARED",
        "edr": "NOT_ADOPTED", "vpn": "MFA_VPN_DECLARED",
    },
    "macos": {
        "os": "NOT_AD_JOINED_LOCAL_ACCOUNT", "browser": "NOT_DECLARED",
        "edr": "NOT_ADOPTED", "vpn": "MFA_VPN_DECLARED",
    },
}

EXPECTED_PROFILE_IDS = ["WIN-01", "WIN-02", "WIN-03", "MAC-01", "MAC-02", "MAC-03"]

REQUIRED_SCENARIO_REFS = [
    "fleet/README.md#시나리오-inventory--구축하지-않는다",
    "context/raw/SCENARIO_FACTS-가상고객사J사.md#9.3",
]

# 실물 AWS 자원을 가리키는 모양. 산문에서의 단어 "AWS" 자체는 막지 않는다.
AWS_RESOURCE_PATTERNS = [
    (r"arn:aws", "AWS ARN"),
    (r"\bami-[0-9a-f]{6,}", "AMI 식별자"),
    (r"\bi-[0-9a-f]{8,}", "EC2 instance 식별자"),
    (r"amazonaws\.com", "AWS endpoint"),
    (r"\bs3://", "S3 URI"),
    (
        r"\b(?:us|eu|ap|sa|ca|me|af)-"
        r"(?:north|south|east|west|central|northeast|northwest|southeast|southwest)-\d\b",
        "AWS region 식별자",
    ),
    (r"resource\s+\"aws_", "Terraform AWS resource"),
]

# 실제 단말·사람을 특정하는 모양.
REAL_IDENTIFIER_PATTERNS = [
    (r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b", "MAC 주소 모양"),
    (r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "IPv4 주소 모양"),
    (
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
        r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
        "UUID 모양",
    ),
    (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "이메일 모양"),
]

# 데이터에 들어오면 안 되는 판정 어휘. 산문 설명이 아니라 값·표 행에만 적용한다.
VERDICT_TOKENS = [
    "충족", "미충족", "적합", "부적합", "잔여위험",
    "COMPLIANT", "NON_COMPLIANT", "PASS", "FAIL",
]


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


def parse_yaml_text(text: str, label: str) -> dict[str, Any]:
    try:
        document = yaml.load(text, Loader=UniqueKeyLoader)
    except (yaml.YAMLError, TypeError) as exc:
        raise ValueError(f"{label}: YAML 파싱 또는 중복 key 오류") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{label}: 최상위 mapping 필요")
    return document


def expected_asset_id(profile_id: str, os_family: str) -> str:
    digest = hashlib.sha256(
        f"{ASSET_ID_NAMESPACE}|{profile_id}".encode("utf-8")
    ).hexdigest()[:12].upper()
    return f"JC-EP-{OS_SHORT[os_family]}-{digest}"


def load_sources(root: Path) -> dict[str, Any]:
    """세 파일이 모두 있고 파싱돼야 한다. 하나라도 없으면 실패다."""
    missing = [
        rel.as_posix()
        for rel in (PACK_PATH, INVENTORY_PATH, UPSTREAM_PATH)
        if not (root / rel).is_file()
    ]
    if missing:
        raise FileNotFoundError("missing fleet review source: " + ", ".join(missing))

    pack_text = (root / PACK_PATH).read_text(encoding="utf-8")
    upstream_text = (root / UPSTREAM_PATH).read_text(encoding="utf-8")
    inventory_text = (root / INVENTORY_PATH).read_text(encoding="utf-8")
    return {
        "pack": parse_yaml_text(pack_text, "fleet review pack"),
        "upstream": parse_yaml_text(upstream_text, "upstream endpoint 계약"),
        "pack_text": pack_text,
        "inventory_text": inventory_text,
    }


def _exact_keys(value: object, expected: set[str], label: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{label}: mapping 필요")
        return False
    actual = set(value)
    if actual != expected:
        errors.append(
            f"{label}: field 집합 불일치 "
            f"(missing={sorted(expected - actual)}, unknown={sorted(actual - expected)})"
        )
        return False
    return True


def _fixed(value: object, expected: object, label: str, errors: list[str]) -> None:
    if value != expected or type(value) is not type(expected):
        errors.append(f"{label}: 고정 계약값 불일치 (기대 {expected!r}, 관측 {value!r})")


def _yaml_scalars(node: object, out: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            out.append(str(key))
            _yaml_scalars(value, out)
    elif isinstance(node, list):
        for item in node:
            _yaml_scalars(item, out)
    elif isinstance(node, str):
        out.append(node)


def audit_documents(
    pack: object, upstream: object, inventory_text: str, pack_text: str
) -> list[str]:
    errors: list[str] = []

    if not _exact_keys(pack, PACK_TOP_KEYS, "review pack", errors):
        return errors
    assert isinstance(pack, dict)
    if not isinstance(upstream, dict):
        errors.append("upstream endpoint 계약: mapping 필요")
        return errors

    # --- 존재하지 않음·합성·비AWS 고정 계약 -------------------------------
    _fixed(pack.get("schema_version"), "jcareer-fleet-endpoint-review-v1",
           "pack schema_version", errors)
    _fixed(pack.get("pack_status"), "NOT_EXECUTED", "pack 실행 상태", errors)
    _fixed(pack.get("synthetic_only"), True, "pack 합성 전용", errors)
    _fixed(pack.get("devices_exist"), False, "pack 실물 단말 부존재", errors)
    _fixed(pack.get("procurement_status"), "NOT_PROCURED", "pack 조달 상태", errors)
    _fixed(pack.get("terraform_managed"), False, "pack Terraform 비관리", errors)
    _fixed(pack.get("aws_managed"), False, "pack AWS 비관리", errors)
    _fixed(pack.get("asset_id_namespace"), ASSET_ID_NAMESPACE,
           "pack asset_id namespace", errors)
    _fixed(pack.get("upstream_contract_ref"), UPSTREAM_PATH.as_posix(),
           "pack 상류 계약 참조", errors)

    if pack.get("scenario_source_refs") != REQUIRED_SCENARIO_REFS:
        errors.append("pack scenario_source_refs: 승인된 근거 앵커 집합과 불일치")

    if pack.get("posture_items") != POSTURE_ITEMS:
        errors.append("pack posture_items: os/browser/edr/vpn 고정 순서 집합 필요")

    # --- 모집단 / 표본 계층 분리 -----------------------------------------
    fleet = pack.get("fleet_inventory")
    if _exact_keys(fleet, FLEET_KEYS, "pack fleet_inventory", errors):
        assert isinstance(fleet, dict)
        _fixed(fleet.get("boundary"), "scenario-document-only",
               "fleet_inventory boundary", errors)
        _fixed(fleet.get("windows"), 100, "fleet_inventory windows", errors)
        _fixed(fleet.get("macos"), 80, "fleet_inventory macos", errors)

    sample = pack.get("review_sample")
    if _exact_keys(sample, SAMPLE_KEYS, "pack review_sample", errors):
        assert isinstance(sample, dict)
        _fixed(sample.get("representative_of_fleet"), False,
               "review_sample 모집단 대표성 부인", errors)
        _fixed(sample.get("windows"), 3, "review_sample windows", errors)
        _fixed(sample.get("macos"), 3, "review_sample macos", errors)

    # --- 시나리오 선언 posture 는 측정값과 분리된 채 고정 ------------------
    scenario = pack.get("scenario_declared_posture")
    if _exact_keys(scenario, SCENARIO_POSTURE_KEYS, "scenario_declared_posture", errors):
        assert isinstance(scenario, dict)
        _fixed(scenario.get("statement_kind"), "DOCUMENT_DECLARED_NOT_MEASURED",
               "scenario_declared_posture 성격", errors)
        for family, expected_map in SCENARIO_DECLARED.items():
            observed = scenario.get(family)
            if not _exact_keys(observed, set(POSTURE_ITEMS),
                               f"scenario_declared_posture[{family}]", errors):
                continue
            assert isinstance(observed, dict)
            for item, expected_value in expected_map.items():
                _fixed(observed.get(item), expected_value,
                       f"scenario_declared_posture[{family}].{item}", errors)

    # --- 단말 6대 ---------------------------------------------------------
    devices = pack.get("devices")
    if not isinstance(devices, list):
        errors.append("pack devices: list 필요")
        return errors
    if len(devices) != 6:
        errors.append(f"pack devices: 정확히 6개 필요 (관측 {len(devices)})")

    upstream_profiles: dict[str, dict[str, Any]] = {}
    raw_upstream = upstream.get("profiles")
    if isinstance(raw_upstream, list):
        for entry in raw_upstream:
            if isinstance(entry, dict) and isinstance(entry.get("profile_id"), str):
                upstream_profiles[entry["profile_id"]] = entry
    if not upstream_profiles:
        errors.append("upstream endpoint 계약: profiles 를 읽을 수 없음")

    seen_ids: list[str] = []
    seen_assets: list[str] = []
    for index, device in enumerate(devices):
        label = f"pack devices[{index}]"
        if not _exact_keys(device, DEVICE_KEYS, label, errors):
            continue
        assert isinstance(device, dict)
        profile_id = device.get("profile_id")
        os_family = device.get("os_family")
        if not isinstance(profile_id, str) or profile_id not in EXPECTED_PROFILE_IDS:
            errors.append(f"{label}: 승인되지 않은 profile_id")
            continue
        seen_ids.append(profile_id)
        label = f"pack devices[{profile_id}]"

        if os_family not in OS_SHORT:
            errors.append(f"{label}: os_family 는 windows/macos 만 허용")
            continue

        # 상류 계약과의 교차 결속 — 여기서 갈라지면 두 파일 중 하나가 표류한 것이다.
        upstream_entry = upstream_profiles.get(profile_id)
        if upstream_entry is None:
            errors.append(f"{label}: 상류 endpoint 계약에 없는 profile_id")
        else:
            if upstream_entry.get("os_family") != os_family:
                errors.append(f"{label}: os_family 가 상류 계약과 불일치")
            if upstream_entry.get("synthetic_persona") != device.get("synthetic_persona"):
                errors.append(f"{label}: synthetic_persona 가 상류 계약과 불일치")
            if upstream_entry.get("allowed_flow_ids") != device.get("allowed_flow_ids"):
                errors.append(f"{label}: allowed_flow_ids 가 상류 계약과 불일치")

        asset_id = device.get("asset_id")
        wanted = expected_asset_id(profile_id, os_family)
        if asset_id != wanted:
            errors.append(f"{label}: asset_id 가 namespace 재계산 값과 불일치")
        if isinstance(asset_id, str):
            seen_assets.append(asset_id)

        posture = device.get("posture")
        if not _exact_keys(posture, set(POSTURE_ITEMS), f"{label} posture", errors):
            continue
        assert isinstance(posture, dict)
        for item in POSTURE_ITEMS:
            entry = posture.get(item)
            item_label = f"{label} posture.{item}"
            if not _exact_keys(entry, POSTURE_ITEM_KEYS, item_label, errors):
                continue
            assert isinstance(entry, dict)
            # pack_status 가 NOT_EXECUTED 인 동안 관찰 주장은 나올 수 없다.
            _fixed(entry.get("observation_state"), "NOT_OBSERVED",
                   f"{item_label} 관찰 상태", errors)
            if entry.get("recorded_value") is not None:
                errors.append(f"{item_label}: 미실행 상태에서 recorded_value 를 채울 수 없음")
            if entry.get("method_ref") is not None:
                errors.append(f"{item_label}: 미실행 상태에서 method_ref 를 채울 수 없음")

    if sorted(seen_ids) != sorted(EXPECTED_PROFILE_IDS):
        errors.append("pack devices: 고정 3 Windows/3 macOS profile_id 집합 불일치")
    if len(set(seen_assets)) != len(seen_assets):
        errors.append("pack devices: asset_id 중복")

    # --- 금지 모양 스캔 ---------------------------------------------------
    scalars: list[str] = []
    _yaml_scalars(pack, scalars)
    joined_values = "\n".join(scalars)

    for text, where in ((pack_text, PACK_PATH.as_posix()),
                        (inventory_text, INVENTORY_PATH.as_posix())):
        for pattern, name in AWS_RESOURCE_PATTERNS:
            if re.search(pattern, text):
                errors.append(f"{where}: AWS 자원 참조 금지 ({name})")
        for pattern, name in REAL_IDENTIFIER_PATTERNS:
            if re.search(pattern, text):
                errors.append(f"{where}: 실단말·실인물 식별자 금지 ({name})")

    for token in VERDICT_TOKENS:
        if token in joined_values:
            errors.append(
                f"{PACK_PATH.as_posix()}: 판정 어휘를 데이터에 넣지 않는다 ({token})"
            )

    table_rows = [
        line for line in inventory_text.splitlines() if line.lstrip().startswith("|")
    ]
    joined_rows = "\n".join(table_rows)
    for token in VERDICT_TOKENS:
        if token in joined_rows:
            errors.append(
                f"{INVENTORY_PATH.as_posix()}: 대장 표에 판정 어휘를 넣지 않는다 ({token})"
            )

    # --- 대장 ↔ 기계판독 원본 동기화 --------------------------------------
    for phrase in (
        "devices_exist: false",
        "NOT_EXECUTED",
        "NOT_PROCURED",
        PACK_PATH.as_posix(),
        "scripts/check_fleet_endpoint_review.py",
    ):
        if phrase not in inventory_text:
            errors.append(f"{INVENTORY_PATH.as_posix()}: 필수 선언 문구 누락 ({phrase})")

    documented_assets = set(re.findall(r"JC-EP-(?:WIN|MAC)-[0-9A-F]{12}", inventory_text))
    if documented_assets != set(seen_assets):
        errors.append(
            f"{INVENTORY_PATH.as_posix()}: 대장의 asset_id 집합이 pack 과 불일치"
        )

    for device in devices:
        if not isinstance(device, dict):
            continue
        asset_id = device.get("asset_id")
        if not isinstance(asset_id, str):
            continue
        row = next((r for r in table_rows if asset_id in r), None)
        if row is None:
            errors.append(f"{INVENTORY_PATH.as_posix()}: {asset_id} 행 없음")
            continue
        for field in (device.get("profile_id"), device.get("os_family"),
                      device.get("synthetic_persona")):
            if isinstance(field, str) and field not in row:
                errors.append(
                    f"{INVENTORY_PATH.as_posix()}: {asset_id} 행이 pack 값과 불일치 ({field})"
                )
        if row.count("NOT_OBSERVED") != len(POSTURE_ITEMS):
            errors.append(
                f"{INVENTORY_PATH.as_posix()}: {asset_id} 행의 posture 열이 4개 미관찰이 아님"
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="fleet 합성 endpoint review pack fail-closed 정적 검사"
    )
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1],
        help="repository root",
    )
    args = parser.parse_args()
    root = args.root.resolve()

    try:
        sources = load_sources(root)
    except (OSError, UnicodeError, FileNotFoundError, ValueError) as exc:
        print(f"::error::{exc}")
        return 1
    except yaml.YAMLError as exc:
        print(f"::error::YAML 파싱 실패: {exc}")
        return 1

    errors = audit_documents(
        sources["pack"], sources["upstream"],
        sources["inventory_text"], sources["pack_text"],
    )
    print(
        "fleet endpoint review pack: Windows 3 + macOS 3, NOT_EXECUTED, "
        "실물·AWS 자원 없음, posture 전량 NOT_OBSERVED"
    )
    for error in errors:
        print(f"::error::{error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
