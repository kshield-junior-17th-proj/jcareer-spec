from __future__ import annotations

import json


def parse_bedrock_explanations(
    rendered: str, expected_refs: set[str]
) -> dict[str, str]:
    """Parse the bounded JSON contract returned by the optional Bedrock provider."""

    if not isinstance(rendered, str) or not rendered.strip() or len(rendered) > 200_000:
        raise ValueError("Bedrock explanation response text is invalid")
    try:
        payload = json.loads(rendered)
    except json.JSONDecodeError as exc:
        raise ValueError("Bedrock explanation response is not JSON") from exc
    if not isinstance(payload, dict) or set(payload) != {"items"}:
        raise ValueError("Bedrock explanation response object is invalid")
    output_items = payload["items"]
    if not isinstance(output_items, list) or len(output_items) != len(expected_refs):
        raise ValueError("Bedrock explanation response items are invalid")

    mapped: dict[str, str] = {}
    for item in output_items:
        if not isinstance(item, dict) or set(item) != {"subject_ref", "text"}:
            raise ValueError("Bedrock explanation response item is invalid")
        subject_ref = item["subject_ref"]
        text = item["text"]
        if not isinstance(subject_ref, str) or subject_ref not in expected_refs:
            raise ValueError("Bedrock explanation response subject is invalid")
        if subject_ref in mapped:
            raise ValueError("Bedrock explanation response subject is duplicated")
        if not isinstance(text, str) or not text.strip() or len(text) > 4_000:
            raise ValueError("Bedrock explanation response text is invalid")
        mapped[subject_ref] = text.strip()

    if set(mapped) != expected_refs:
        raise ValueError("Bedrock explanation response references do not match the request")
    return mapped
