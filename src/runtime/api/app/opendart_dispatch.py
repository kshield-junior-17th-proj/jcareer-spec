from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Callable


MESSAGE_SCHEMA_VERSION = "jcareer-opendart-refresh-request-v1"


class OpenDartDispatchError(RuntimeError):
    """Safe queue-dispatch failure without SDK request or credential details."""


def build_refresh_message(
    *,
    company_id: str,
    corp_code: str,
    requested_at: datetime | None = None,
    request_id: str | None = None,
) -> dict[str, str]:
    moment = (requested_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return {
        "schema_version": MESSAGE_SCHEMA_VERSION,
        "request_id": request_id or str(uuid.uuid4()),
        "company_id": company_id,
        "corp_code": corp_code,
        "requested_at": moment.isoformat(),
    }


def enqueue_refresh(
    message: dict[str, str],
    *,
    sender_factory: Callable[[], object] | None = None,
) -> dict[str, str]:
    queue_url = os.getenv("OPENDART_REFRESH_QUEUE_URL", "").strip()
    if not queue_url:
        raise OpenDartDispatchError("OpenDART serverless queue 설정을 확인해 주세요")
    canonical = json.dumps(
        message, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    company_group = hashlib.sha256(message["company_id"].encode("utf-8")).hexdigest()
    # SQS FIFO should collapse retries of the same request, not distinct user
    # requests for the same company made within one minute.
    deduplication_id = hashlib.sha256(
        f"{message['schema_version']}:{message['request_id']}".encode("utf-8")
    ).hexdigest()
    try:
        if sender_factory is None:
            import boto3

            sender = boto3.client(
                "sqs", region_name=os.getenv("AWS_REGION", "ap-northeast-2")
            )
        else:
            sender = sender_factory()
        result = sender.send_message(
            QueueUrl=queue_url,
            MessageBody=canonical,
            MessageGroupId=company_group,
            MessageDeduplicationId=deduplication_id,
        )
    except Exception:
        raise OpenDartDispatchError(
            "OpenDART 갱신 요청을 큐에 등록하지 못했습니다"
        ) from None
    message_id = result.get("MessageId") if isinstance(result, dict) else None
    if not isinstance(message_id, str) or not message_id:
        raise OpenDartDispatchError(
            "OpenDART 갱신 요청의 큐 응답을 확인할 수 없습니다"
        )
    return {
        "request_id": message["request_id"],
        "queue_message_id": message_id,
        "deduplication_id": deduplication_id,
    }
