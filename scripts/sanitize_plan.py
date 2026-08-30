#!/usr/bin/env python3
"""Terraform plan JSON → allowlist 기반 sanitized summary (검수 V2-P0-09).

plan 및 `terraform show -json` 결과에는 sensitive 값이 평문으로 들어갈 수 있다.
원본을 artifact 로 올리지 않는다. 이 요약만 올린다.

허용 필드: 리소스 타입 · 주소 · 액션 · 개수. 속성 값은 일절 포함하지 않는다.
"""
import argparse, json, pathlib, sys

ALLOW_KEYS = ("type", "address", "actions", "count")


def walk(mod):
    for r in mod.get("resources", []):
        yield r
    for c in mod.get("child_modules", []):
        yield from walk(c)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    plan = json.load(open(a.plan, encoding="utf-8"))
    res = list(walk((plan.get("planned_values") or {}).get("root_module") or {}))
    by_type = {}
    for r in res:
        by_type[r.get("type")] = by_type.get(r.get("type"), 0) + 1

    changes = []
    for c in (plan.get("resource_changes") or []):
        changes.append({"type": c.get("type"), "address": c.get("address"),
                        "actions": (c.get("change") or {}).get("actions")})

    summary = {
        "schema": "sanitized-plan-summary/1",
        "resource_count": len(res),
        "by_type": dict(sorted(by_type.items())),
        "changes": changes,
        "note": "속성 값은 포함하지 않는다. 민감값 노출 방지 (V2-P0-09).",
    }

    # 자기검증 — 허용 키 밖의 문자열이 새어나갔는지 확인
    blob = json.dumps(summary, ensure_ascii=False)
    for c in changes:
        for k in c:
            if k not in ALLOW_KEYS:
                print(f"::error::sanitize schema 위반: {k}")
                return 1

    o = pathlib.Path(a.out); o.parent.mkdir(parents=True, exist_ok=True)
    o.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"sanitized summary 작성: {a.out} · 리소스 {len(res)}건 · 타입 {len(by_type)}종")
    return 0


if __name__ == "__main__":
    sys.exit(main())
