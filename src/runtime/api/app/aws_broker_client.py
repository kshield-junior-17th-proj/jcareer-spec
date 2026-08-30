from __future__ import annotations

import json
import os
from typing import Any

import httpx


class AwsBrokerClientError(RuntimeError):
    """Safe local broker error; never includes AWS SDK or credential details."""

    def __init__(self, category: str = "BROKER_UNAVAILABLE") -> None:
        super().__init__(category)
        self.category = category


class BrokerConditionalCheckFailed(AwsBrokerClientError):
    response = {"Error": {"Code": "ConditionalCheckFailedException"}}


def _socket_path() -> str:
    value = os.getenv("OPENDART_AWS_BROKER_SOCKET", "").strip()
    if value != "/run/jcareer-opendart/broker.sock":
        raise AwsBrokerClientError("BROKER_SOCKET_NOT_CONFIGURED")
    return value


def _post(path: str, payload: dict[str, object]) -> dict[str, Any]:
    try:
        transport = httpx.HTTPTransport(uds=_socket_path(), retries=0)
        with httpx.Client(
            transport=transport,
            base_url="http://jcareer-opendart-broker",
            timeout=httpx.Timeout(15.0, connect=2.0),
            trust_env=False,
        ) as client:
            response = client.post(path, json=payload)
    except (httpx.HTTPError, OSError):
        raise AwsBrokerClientError() from None
    try:
        body = response.json()
    except json.JSONDecodeError:
        raise AwsBrokerClientError("BROKER_RESPONSE_INVALID") from None
    if not isinstance(body, dict):
        raise AwsBrokerClientError("BROKER_RESPONSE_INVALID")
    if response.status_code == 403 and body.get("category") == "RESULT_OWNERSHIP_MISMATCH":
        raise BrokerConditionalCheckFailed("RESULT_OWNERSHIP_MISMATCH")
    if response.status_code != 200:
        category = body.get("category")
        raise AwsBrokerClientError(
            str(category) if isinstance(category, str) else "BROKER_UNAVAILABLE"
        )
    return body


class OpenDartBrokerSqsClient:
    def send_message(self, **kwargs: object) -> dict[str, str]:
        expected = {
            "QueueUrl",
            "MessageBody",
            "MessageGroupId",
            "MessageDeduplicationId",
        }
        if set(kwargs) != expected or kwargs.get("QueueUrl") != "broker://configured-opendart-refresh":
            raise AwsBrokerClientError("BROKER_CALL_SHAPE_INVALID")
        try:
            message = json.loads(str(kwargs["MessageBody"]))
        except (json.JSONDecodeError, KeyError):
            raise AwsBrokerClientError("BROKER_CALL_SHAPE_INVALID") from None
        body = _post("/v1/opendart/refresh", message)
        if (
            body.get("status") != "QUEUED"
            or body.get("request_id") != message.get("request_id")
            or body.get("deduplication_id") != kwargs.get("MessageDeduplicationId")
            or not isinstance(body.get("message_id"), str)
        ):
            raise AwsBrokerClientError("BROKER_RESPONSE_INVALID")
        return {"MessageId": str(body["message_id"])}


class OpenDartBrokerDynamoClient:
    def get_item(self, **kwargs: object) -> dict[str, object]:
        expected = {
            "TableName",
            "Key",
            "ConsistentRead",
            "ProjectionExpression",
            "ExpressionAttributeNames",
        }
        if set(kwargs) != expected or kwargs.get("TableName") != "broker-configured-opendart-results":
            raise AwsBrokerClientError("BROKER_CALL_SHAPE_INVALID")
        key = kwargs.get("Key")
        request_id = (
            key.get("request_id", {}).get("S")
            if isinstance(key, dict) and isinstance(key.get("request_id"), dict)
            else None
        )
        if not isinstance(request_id, str):
            raise AwsBrokerClientError("BROKER_CALL_SHAPE_INVALID")
        body = _post("/v1/opendart/result/get", {"request_id": request_id})
        if body.get("status") == "NOT_FOUND":
            return {}
        item = body.get("item")
        if body.get("status") != "FOUND" or not isinstance(item, dict) or set(item) != {
            "request_id",
            "company_id",
            "payload",
            "expires_at",
        }:
            raise AwsBrokerClientError("BROKER_RESPONSE_INVALID")
        return {
            "Item": {
                "request_id": {"S": str(item["request_id"])},
                "company_id": {"S": str(item["company_id"])},
                "payload": {"S": str(item["payload"])},
                "expires_at": {"N": str(item["expires_at"])},
            }
        }

    def delete_item(self, **kwargs: object) -> dict[str, object]:
        expected = {
            "TableName",
            "Key",
            "ConditionExpression",
            "ExpressionAttributeValues",
        }
        if set(kwargs) != expected or kwargs.get("TableName") != "broker-configured-opendart-results":
            raise AwsBrokerClientError("BROKER_CALL_SHAPE_INVALID")
        key = kwargs.get("Key")
        values = kwargs.get("ExpressionAttributeValues")
        request_id = (
            key.get("request_id", {}).get("S")
            if isinstance(key, dict) and isinstance(key.get("request_id"), dict)
            else None
        )
        company_id = (
            values.get(":company_id", {}).get("S")
            if isinstance(values, dict) and isinstance(values.get(":company_id"), dict)
            else None
        )
        if not isinstance(request_id, str) or not isinstance(company_id, str):
            raise AwsBrokerClientError("BROKER_CALL_SHAPE_INVALID")
        body = _post(
            "/v1/opendart/result/delete",
            {"request_id": request_id, "company_id": company_id},
        )
        if body != {"status": "DELETED"}:
            raise AwsBrokerClientError("BROKER_RESPONSE_INVALID")
        return {}
