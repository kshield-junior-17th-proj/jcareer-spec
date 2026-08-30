#!/usr/bin/env python3
"""Validate an allowlisted delete-only Terraform saved plan without applying it."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from check_serverless_opendart_static import EXPECTED_PLAN_ADDRESSES as OPENDART
from check_workplace_endpoints_static import EXPECTED_PLAN_ADDRESSES as ENDPOINTS
from check_workplace_images_static import EXPECTED_PLAN_ADDRESSES as IMAGES


EXACT_ADDRESS_SETS = {
    "serverless-opendart-teardown": (
        OPENDART["bootstrap"],
        OPENDART["runtime"],
    ),
    "workplace-windows-image-teardown": (IMAGES["definition"],),
    "workplace-windows-endpoints-teardown": (ENDPOINTS["windows_three"],),
}
RECOVERY_ALLOWED_ADDRESSES = {
    "serverless-opendart-recovery-teardown": OPENDART["runtime"],
    "workplace-windows-image-recovery-teardown": IMAGES["definition"],
    "workplace-windows-endpoints-recovery-teardown": ENDPOINTS["windows_three"],
}
# Compatibility/export for tests and reviewers: the normal deployed superset per scope.
ALLOWED_ADDRESSES = {
    scope: max(address_sets, key=len) for scope, address_sets in EXACT_ADDRESS_SETS.items()
}


def audit_teardown_plan(plan: object, scope: str) -> list[str]:
    if scope not in EXACT_ADDRESS_SETS and scope not in RECOVERY_ALLOWED_ADDRESSES:
        return ["teardown scope is not allowlisted"]
    if not isinstance(plan, dict):
        return ["teardown plan must be a JSON object"]
    changes = plan.get("resource_changes")
    if not isinstance(changes, list):
        return ["teardown plan resource_changes must be an array"]
    errors: list[str] = []
    exact_sets = EXACT_ADDRESS_SETS.get(scope)
    allowed = (
        set().union(*exact_sets)
        if exact_sets is not None
        else RECOVERY_ALLOWED_ADDRESSES[scope]
    )
    seen: set[str] = set()
    for row in changes:
        if not isinstance(row, dict):
            errors.append("teardown resource change must be an object")
            continue
        address = row.get("address")
        mode = row.get("mode")
        actions = (row.get("change") or {}).get("actions")
        if not isinstance(address, str) or address in seen:
            errors.append("teardown resource address is missing or duplicated")
            continue
        seen.add(address)
        if address not in allowed:
            errors.append(f"teardown plan contains an unapproved address: {address}")
        if mode != "managed":
            errors.append(f"teardown plan contains a non-managed address: {address}")
        if actions != ["delete"]:
            errors.append(f"teardown action is not delete-only: {address}")
    if exact_sets is not None and not any(seen == expected for expected in exact_sets):
        expected_sizes = "/".join(str(len(expected)) for expected in exact_sets)
        errors.append(
            "teardown plan must contain an exact stage-bound deployed address set: "
            f"expected={expected_sizes} observed={len(seen)}"
        )
    elif exact_sets is None and not seen:
        errors.append("recovery teardown plan must contain at least one managed delete")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--scope", required=True)
    args = parser.parse_args()
    try:
        payload = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        errors = audit_teardown_plan(payload, args.scope)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"teardown plan check failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    for error in errors:
        print(f"teardown plan check failed: {error}", file=sys.stderr)
    if not errors:
        print("Terraform teardown plan: PASS (allowlisted delete-only plan, not applied)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
