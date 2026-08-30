from __future__ import annotations

import json
import os

import httpx

from .bedrock_response import parse_bedrock_explanations


class BedrockBrokerError(RuntimeError):
    """Safe local capability-broker failure without provider details."""


def generate_explanations(
    *, contract_version: str, items: list[dict[str, object]]
) -> dict[str, str]:
    socket_path = os.getenv("BEDROCK_AWS_BROKER_SOCKET", "").strip()
    if socket_path != "/run/jcareer-bedrock/broker.sock":
        raise BedrockBrokerError("Bedrock capability broker is not configured")
    try:
        transport = httpx.HTTPTransport(uds=socket_path, retries=0)
        with httpx.Client(
            transport=transport,
            base_url="http://jcareer-bedrock-broker",
            timeout=httpx.Timeout(20.0, connect=2.0),
            trust_env=False,
        ) as client:
            response = client.post(
                "/v1/bedrock/explanations",
                json={"contract_version": contract_version, "items": items},
            )
    except (httpx.HTTPError, OSError):
        raise BedrockBrokerError("Bedrock capability broker is unavailable") from None
    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError):
        raise BedrockBrokerError("Bedrock capability broker response is invalid") from None
    if response.status_code != 200 or not isinstance(payload, dict):
        raise BedrockBrokerError("Bedrock capability broker rejected the request")
    returned = payload.get("items")
    if payload.get("status") != "AVAILABLE" or not isinstance(returned, list):
        raise BedrockBrokerError("Bedrock capability broker response is invalid")
    expected = {str(item["subject_ref"]) for item in items}
    try:
        return parse_bedrock_explanations(
            json.dumps(
                {"items": returned},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            expected,
        )
    except ValueError:
        raise BedrockBrokerError("Bedrock capability broker response is invalid") from None
