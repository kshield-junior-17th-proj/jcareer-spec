from __future__ import annotations

import json
import sys
from pathlib import Path


GATEWAY_ROOT = Path(__file__).resolve().parents[1] / "llm_gateway"
sys.path.insert(0, str(GATEWAY_ROOT))

from app.bedrock_response import parse_bedrock_explanations  # noqa: E402


def rejected(payload: object, expected: set[str] | None = None) -> None:
    rendered = payload if isinstance(payload, str) else json.dumps(payload)
    try:
        parse_bedrock_explanations(rendered, expected or {"subject-1"})
    except ValueError:
        return
    raise AssertionError(f"invalid Bedrock response was accepted: {rendered}")


def main() -> None:
    assert parse_bedrock_explanations(
        json.dumps(
            {
                "items": [
                    {"subject_ref": "subject-1", "text": " 합성 설명 1 "},
                    {"subject_ref": "subject-2", "text": "합성 설명 2"},
                ]
            },
            ensure_ascii=False,
        ),
        {"subject-1", "subject-2"},
    ) == {"subject-1": "합성 설명 1", "subject-2": "합성 설명 2"}

    for payload in (
        "not-json",
        [],
        {"items": {}},
        {"items": [None]},
        {"items": [{"subject_ref": 1, "text": "설명"}]},
        {"items": [{"subject_ref": "subject-1", "text": 1}]},
        {"items": [{"subject_ref": "subject-1", "text": ""}]},
        {"items": [{"subject_ref": "subject-1", "text": "가" * 1_001}]},
        {"items": [{"subject_ref": "other", "text": "설명"}]},
        {"items": [{"subject_ref": "subject-1", "text": "설명", "extra": True}]},
    ):
        rejected(payload)

    rejected(
        {
            "items": [
                {"subject_ref": "subject-1", "text": "설명 1"},
                {"subject_ref": "subject-1", "text": "설명 2"},
            ]
        },
        {"subject-1", "subject-2"},
    )

    print("J-Career Bedrock response parser contract: PASS")


if __name__ == "__main__":
    main()
