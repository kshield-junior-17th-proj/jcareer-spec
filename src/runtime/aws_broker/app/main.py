from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import socket
import stat
import struct
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("jcareer.aws_capability_broker")

MODE = os.getenv("BROKER_MODE", "").strip()
REGION = os.getenv("BROKER_REGION", "ap-northeast-2").strip()
SOCKET_PATH = Path(os.getenv("BROKER_SOCKET_PATH", "/run/jcareer-aws/broker.sock"))
EXPECTED_PEER_UID = int(os.getenv("BROKER_EXPECTED_PEER_UID", "-1"))
MAX_BODY_BYTES = 256_000
MAX_HEADER_BYTES = 8_192
MESSAGE_SCHEMA = "jcareer-opendart-refresh-request-v2"
RESULT_MAX_BYTES = 220_000
CORP_CODE = re.compile(r"^[0-9]{8}$")
SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,79}$")
SAFE_FIFO_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{2,74}\.fifo$")
BEDROCK_MODEL_ID = "apac.amazon.nova-lite-v1:0"
FORBIDDEN_CREDENTIAL_ENV = {
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_CONTAINER_CREDENTIALS_FULL_URI",
    "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
    "AWS_WEB_IDENTITY_TOKEN_FILE",
    "AWS_ROLE_ARN",
    "AWS_SHARED_CREDENTIALS_FILE",
    "AWS_PROFILE",
}


class BrokerRequestError(RuntimeError):
    def __init__(self, status: int, category: str):
        super().__init__(category)
        self.status = status
        self.category = category


def _exact_object(value: object, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise BrokerRequestError(400, "INVALID_REQUEST_SCHEMA")
    return value


def _exact_upstream_object(value: object, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise RuntimeError("upstream response violated the reviewed schema")
    return value


def _uuid(value: object) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError):
        raise BrokerRequestError(400, "INVALID_REQUEST_ID") from None


def _utc_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise BrokerRequestError(400, "INVALID_REQUEST_TIME")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise BrokerRequestError(400, "INVALID_REQUEST_TIME") from None
    if parsed.tzinfo is None:
        raise BrokerRequestError(400, "INVALID_REQUEST_TIME")
    moment = parsed.astimezone(timezone.utc)
    if abs((datetime.now(timezone.utc) - moment).total_seconds()) > 600:
        raise BrokerRequestError(400, "STALE_REQUEST_TIME")
    return moment


def _json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _safe_response(status: int, payload: object) -> bytes:
    body = _json_bytes(payload)
    reason = {
        200: "OK",
        400: "Bad Request",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        413: "Payload Too Large",
        415: "Unsupported Media Type",
        503: "Service Unavailable",
    }.get(status, "Error")
    return (
        f"HTTP/1.1 {status} {reason}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "Cache-Control: no-store\r\n\r\n"
    ).encode("ascii") + body


class AwsCapabilities:
    def __init__(self) -> None:
        if MODE not in {"opendart", "bedrock"} or REGION != "ap-northeast-2":
            raise RuntimeError("broker mode or region is outside the reviewed boundary")
        present = sorted(name for name in FORBIDDEN_CREDENTIAL_ENV if os.getenv(name))
        if present:
            raise RuntimeError("broker refuses static, container, profile, or web-identity credentials")
        session = boto3.Session(region_name=REGION)
        credentials = session.get_credentials()
        if credentials is None or credentials.method != "iam-role":
            raise RuntimeError("broker requires EC2 instance-role credentials from IMDSv2")
        config = Config(
            connect_timeout=2,
            read_timeout=12,
            retries={"max_attempts": 1, "mode": "standard"},
            user_agent_extra="jcareer-fixed-capability-broker/1",
        )
        self.queue_url = ""
        self.table_name = ""
        self.sqs = None
        self.dynamodb = None
        self.bedrock = None
        if MODE == "opendart":
            queue_name = os.getenv("OPENDART_REFRESH_QUEUE_NAME", "").strip()
            table_name = os.getenv("OPENDART_RESULT_TABLE_NAME", "").strip()
            if not SAFE_FIFO_NAME.fullmatch(queue_name):
                raise RuntimeError("OpenDART queue name is invalid")
            if not SAFE_NAME.fullmatch(table_name):
                raise RuntimeError("OpenDART table name is invalid")
            self.sqs = session.client("sqs", config=config)
            self.dynamodb = session.client("dynamodb", config=config)
            queue = self.sqs.get_queue_url(QueueName=queue_name)
            self.queue_url = str(queue.get("QueueUrl", ""))
            if not self.queue_url.startswith("https://sqs.ap-northeast-2.amazonaws.com/"):
                raise RuntimeError("OpenDART queue lookup did not return the expected regional URL")
            self.table_name = table_name
        else:
            if os.getenv("BEDROCK_MODEL_ID", BEDROCK_MODEL_ID) != BEDROCK_MODEL_ID:
                raise RuntimeError("Bedrock model is outside the reviewed allowlist")
            self.bedrock = session.client("bedrock-runtime", config=config)

    def opendart_refresh(self, request: object) -> dict[str, object]:
        row = _exact_object(
            request,
            {
                "schema_version",
                "request_id",
                "company_id",
                "expected_company_name",
                "corp_code",
                "requested_at",
            },
        )
        if row.get("schema_version") != MESSAGE_SCHEMA:
            raise BrokerRequestError(400, "INVALID_MESSAGE_SCHEMA")
        request_id = _uuid(row.get("request_id"))
        company_id = _uuid(row.get("company_id"))
        company_name = " ".join(str(row.get("expected_company_name", "")).split())
        corp_code = str(row.get("corp_code", ""))
        requested_at = _utc_time(row.get("requested_at")).isoformat()
        if not company_name or len(company_name) > 120 or not CORP_CODE.fullmatch(corp_code):
            raise BrokerRequestError(400, "INVALID_COMPANY_BINDING")
        message = {
            "schema_version": MESSAGE_SCHEMA,
            "request_id": request_id,
            "company_id": company_id,
            "expected_company_name": company_name,
            "corp_code": corp_code,
            "requested_at": requested_at,
        }
        group_id = hashlib.sha256(company_id.encode()).hexdigest()
        deduplication_id = hashlib.sha256(
            f"{MESSAGE_SCHEMA}:{request_id}".encode()
        ).hexdigest()
        assert self.sqs is not None
        response = self.sqs.send_message(
            QueueUrl=self.queue_url,
            MessageBody=_json_bytes(message).decode("utf-8"),
            MessageGroupId=group_id,
            MessageDeduplicationId=deduplication_id,
        )
        message_id = response.get("MessageId")
        if not isinstance(message_id, str) or not message_id:
            raise RuntimeError("SQS response omitted its message identifier")
        return {
            "status": "QUEUED",
            "request_id": request_id,
            "message_id": message_id,
            "deduplication_id": deduplication_id,
        }

    def opendart_result_get(self, request: object) -> dict[str, object]:
        row = _exact_object(request, {"request_id"})
        request_id = _uuid(row.get("request_id"))
        assert self.dynamodb is not None
        response = self.dynamodb.get_item(
            TableName=self.table_name,
            Key={"request_id": {"S": request_id}},
            ConsistentRead=True,
            ProjectionExpression="#request_id, #company_id, #payload, #expires_at",
            ExpressionAttributeNames={
                "#request_id": "request_id",
                "#company_id": "company_id",
                "#payload": "payload",
                "#expires_at": "expires_at",
            },
        )
        item = response.get("Item")
        if not isinstance(item, dict):
            return {"status": "NOT_FOUND"}
        try:
            payload = str(item["payload"]["S"])
            company_id = _uuid(item["company_id"]["S"])
            expires_at = str(item["expires_at"]["N"])
        except (KeyError, TypeError, BrokerRequestError):
            raise RuntimeError("DynamoDB item violated the result boundary") from None
        if len(payload.encode("utf-8")) > RESULT_MAX_BYTES or not re.fullmatch(r"[0-9]{1,20}", expires_at):
            raise RuntimeError("DynamoDB item exceeded the result boundary")
        return {
            "status": "FOUND",
            "item": {
                "request_id": request_id,
                "company_id": company_id,
                "payload": payload,
                "expires_at": expires_at,
            },
        }

    def opendart_result_delete(self, request: object) -> dict[str, object]:
        row = _exact_object(request, {"request_id", "company_id"})
        request_id = _uuid(row.get("request_id"))
        company_id = _uuid(row.get("company_id"))
        assert self.dynamodb is not None
        try:
            self.dynamodb.delete_item(
                TableName=self.table_name,
                Key={"request_id": {"S": request_id}},
                ConditionExpression="company_id = :company_id",
                ExpressionAttributeValues={":company_id": {"S": company_id}},
            )
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if code == "ConditionalCheckFailedException":
                raise BrokerRequestError(403, "RESULT_OWNERSHIP_MISMATCH") from None
            raise
        return {"status": "DELETED"}

    def bedrock_explanations(self, request: object) -> dict[str, object]:
        row = _exact_object(request, {"contract_version", "items"})
        if row.get("contract_version") != "score-explanation-v1":
            raise BrokerRequestError(400, "INVALID_EXPLANATION_CONTRACT")
        items = row.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 20:
            raise BrokerRequestError(400, "INVALID_EXPLANATION_BATCH")
        subject_refs: set[str] = set()
        for item in items:
            if not isinstance(item, dict) or set(item) != {
                "subject_ref",
                "score",
                "score_breakdown",
                "matched_feature_labels",
                "candidate_context",
                "company_context",
            }:
                raise BrokerRequestError(400, "INVALID_EXPLANATION_ITEM")
            subject_ref = str(item.get("subject_ref", ""))
            if not subject_ref or len(subject_ref) > 128 or subject_ref in subject_refs:
                raise BrokerRequestError(400, "INVALID_EXPLANATION_SUBJECT")
            subject_refs.add(subject_ref)
        system_text = (
            "You generate short Korean explanations for precomputed recruiting scores. "
            "Never alter scores or ranking, infer protected traits, or claim hiring outcomes. "
            "Use only supplied candidate materials and company-declared profile. Return only "
            "JSON {\"items\":[{\"subject_ref\":\"...\",\"text\":\"...\"}]} with one item per subject."
        )
        assert self.bedrock is not None
        response = self.bedrock.converse(
            modelId=BEDROCK_MODEL_ID,
            system=[{"text": system_text}],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "text": json.dumps(
                                {
                                    "contract_version": row["contract_version"],
                                    "items": items,
                                },
                                ensure_ascii=False,
                                sort_keys=True,
                            )
                        }
                    ],
                }
            ],
            inferenceConfig={"maxTokens": 1200, "temperature": 0.0, "topP": 0.1},
        )
        content = response.get("output", {}).get("message", {}).get("content", [])
        rendered = "".join(
            str(block.get("text", ""))
            for block in content
            if isinstance(block, dict)
        ).strip()
        if rendered.startswith("```"):
            rendered = rendered.removeprefix("```json").removeprefix("```")
            rendered = rendered.removesuffix("```").strip()
        try:
            parsed = json.loads(rendered)
        except json.JSONDecodeError:
            raise RuntimeError("Bedrock response schema is invalid") from None
        parsed = _exact_upstream_object(parsed, {"items"})
        returned = parsed.get("items")
        if not isinstance(returned, list) or len(returned) != len(subject_refs):
            raise RuntimeError("Bedrock response batch is invalid")
        safe_items: list[dict[str, str]] = []
        returned_refs: set[str] = set()
        for item in returned:
            item = _exact_upstream_object(item, {"subject_ref", "text"})
            subject_ref = str(item.get("subject_ref", ""))
            text = str(item.get("text", "")).strip()
            if subject_ref not in subject_refs or subject_ref in returned_refs or not text or len(text) > 1000:
                raise RuntimeError("Bedrock response item is invalid")
            returned_refs.add(subject_ref)
            safe_items.append({"subject_ref": subject_ref, "text": text})
        if returned_refs != subject_refs:
            raise RuntimeError("Bedrock response subjects are incomplete")
        usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
        return {
            "status": "AVAILABLE",
            "items": safe_items,
            "usage": {
                "input_tokens": int(usage.get("inputTokens", 0)),
                "output_tokens": int(usage.get("outputTokens", 0)),
            },
        }


def _peer_uid(writer: asyncio.StreamWriter) -> int:
    raw_socket = writer.get_extra_info("socket")
    if raw_socket is None or not hasattr(socket, "SO_PEERCRED"):
        raise BrokerRequestError(403, "PEER_IDENTITY_UNAVAILABLE")
    credentials = raw_socket.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
    _, uid, _ = struct.unpack("3i", credentials)
    return uid


async def _read_request(reader: asyncio.StreamReader) -> tuple[str, str, object]:
    try:
        header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=3)
    except (asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
        raise BrokerRequestError(400, "INVALID_HTTP_REQUEST") from None
    if len(header) > MAX_HEADER_BYTES:
        raise BrokerRequestError(413, "HEADERS_TOO_LARGE")
    try:
        lines = header.decode("ascii").split("\r\n")
        method, path, version = lines[0].split(" ")
    except (UnicodeDecodeError, ValueError):
        raise BrokerRequestError(400, "INVALID_HTTP_REQUEST") from None
    if version != "HTTP/1.1" or method not in {"GET", "POST"}:
        raise BrokerRequestError(405, "METHOD_NOT_ALLOWED")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            continue
        if ":" not in line:
            raise BrokerRequestError(400, "INVALID_HTTP_HEADERS")
        key, value = line.split(":", 1)
        key = key.strip().lower()
        if key in headers:
            raise BrokerRequestError(400, "DUPLICATE_HTTP_HEADER")
        headers[key] = value.strip()
    if method == "GET":
        if path != "/health":
            raise BrokerRequestError(404, "ROUTE_NOT_FOUND")
        return method, path, {}
    if headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
        raise BrokerRequestError(415, "JSON_REQUIRED")
    if "transfer-encoding" in headers:
        raise BrokerRequestError(400, "CHUNKED_REQUEST_FORBIDDEN")
    try:
        content_length = int(headers.get("content-length", ""))
    except ValueError:
        raise BrokerRequestError(400, "CONTENT_LENGTH_REQUIRED") from None
    if content_length < 2 or content_length > MAX_BODY_BYTES:
        raise BrokerRequestError(413, "BODY_SIZE_INVALID")
    try:
        body = await asyncio.wait_for(reader.readexactly(content_length), timeout=3)
        parsed = json.loads(body)
    except (asyncio.TimeoutError, asyncio.IncompleteReadError, json.JSONDecodeError):
        raise BrokerRequestError(400, "INVALID_JSON") from None
    return method, path, parsed


async def _dispatch(capabilities: AwsCapabilities, path: str, body: object) -> object:
    routes = {
        ("opendart", "/v1/opendart/refresh"): capabilities.opendart_refresh,
        ("opendart", "/v1/opendart/result/get"): capabilities.opendart_result_get,
        ("opendart", "/v1/opendart/result/delete"): capabilities.opendart_result_delete,
        ("bedrock", "/v1/bedrock/explanations"): capabilities.bedrock_explanations,
    }
    operation = routes.get((MODE, path))
    if operation is None:
        raise BrokerRequestError(404, "ROUTE_NOT_FOUND")
    return await asyncio.wait_for(asyncio.to_thread(operation, body), timeout=20)


async def _handle(
    capabilities: AwsCapabilities,
    semaphore: asyncio.Semaphore,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    status = 503
    payload: object = {"status": "ERROR", "category": "BROKER_UNAVAILABLE"}
    try:
        if _peer_uid(writer) != EXPECTED_PEER_UID:
            raise BrokerRequestError(403, "PEER_NOT_ALLOWED")
        async with semaphore:
            method, path, body = await _read_request(reader)
            if method == "GET":
                status, payload = 200, {"status": "ok", "mode": MODE}
            else:
                payload = await _dispatch(capabilities, path, body)
                status = 200
        logger.info("broker_operation status=success mode=%s", MODE)
    except BrokerRequestError as exc:
        status = exc.status
        payload = {"status": "ERROR", "category": exc.category}
        logger.warning("broker_operation status=rejected mode=%s category=%s", MODE, exc.category)
    except asyncio.TimeoutError:
        status = 503
        payload = {"status": "ERROR", "category": "OPERATION_TIMEOUT"}
        logger.error("broker_operation status=timeout mode=%s", MODE)
    except Exception as exc:
        status = 503
        payload = {"status": "ERROR", "category": "UPSTREAM_UNAVAILABLE"}
        logger.error("broker_operation status=failed mode=%s exception=%s", MODE, type(exc).__name__)
    try:
        writer.write(_safe_response(status, payload))
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def run() -> None:
    if EXPECTED_PEER_UID < 10000 or os.geteuid() != EXPECTED_PEER_UID:
        raise RuntimeError("broker and its sole client must use the reviewed fixed non-root UID")
    SOCKET_PATH.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    if SOCKET_PATH.exists() or SOCKET_PATH.is_symlink():
        info = SOCKET_PATH.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid():
            raise RuntimeError("refusing to replace an unowned or non-socket broker path")
        SOCKET_PATH.unlink()
    capabilities = await asyncio.to_thread(AwsCapabilities)
    previous_umask = os.umask(0o117)
    try:
        semaphore = asyncio.Semaphore(4 if MODE == "opendart" else 1)
        server = await asyncio.start_unix_server(
            lambda reader, writer: _handle(capabilities, semaphore, reader, writer),
            path=str(SOCKET_PATH),
            limit=MAX_HEADER_BYTES,
        )
        os.chmod(SOCKET_PATH, 0o660)
    finally:
        os.umask(previous_umask)
    logger.info("broker_started mode=%s socket_transport=unix", MODE)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(run())
