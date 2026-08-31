"""Provider-neutral event, status, and delivery receipt contracts."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .redaction import contains_sensitive_text


IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")


class DeliveryProvider(StrEnum):
    SLACK_WEBHOOK = "slack_webhook"
    NOTION_API = "notion_api"
    SMTP_TLS = "smtp_tls"


class DeliveryState(StrEnum):
    DELIVERED = "DELIVERED"
    DISABLED = "DISABLED"
    FAILED = "FAILED"


class ConfigurationState(StrEnum):
    DISABLED = "DISABLED"
    READY = "READY"
    INVALID = "INVALID"


class FailureCode(StrEnum):
    PROVIDER_DISABLED = "PROVIDER_DISABLED"
    CONFIGURATION_INVALID = "CONFIGURATION_INVALID"
    HOST_NOT_ALLOWED = "HOST_NOT_ALLOWED"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_REJECTED = "PROVIDER_REJECTED"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IntegrationEvent(StrictContract):
    """A deliberately small event that cannot carry candidate or company records."""

    contract_version: Literal["jcareer-integration-event-v1"] = (
        "jcareer-integration-event-v1"
    )
    event_id: str = Field(
        min_length=8, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]+$"
    )
    event_type: Literal["synthetic.connectivity_probe"] = "synthetic.connectivity_probe"
    subject_ref: Literal["synthetic:integration-probe"] = "synthetic:integration-probe"
    summary: str = Field(min_length=1, max_length=160)
    data_classification: Literal["SYNTHETIC_NON_PERSONAL"] = "SYNTHETIC_NON_PERSONAL"

    @field_validator("summary")
    @classmethod
    def reject_direct_identifiers_and_credentials(cls, value: str) -> str:
        normalised = " ".join(value.split())
        if contains_sensitive_text(normalised):
            raise ValueError(
                "integration event text must not contain direct identifiers or credentials"
            )
        return normalised


class ProviderStatus(StrictContract):
    provider: DeliveryProvider
    enabled: bool
    configuration_state: ConfigurationState
    endpoint_configured: bool
    credential_configured: bool
    allowlist_configured: bool
    target_host_allowed: bool
    timeout_seconds: float = Field(gt=0, le=30)
    network_probe_performed: Literal[False] = False


class IntegrationStatusResponse(StrictContract):
    contract_version: Literal["jcareer-integration-status-v1"] = (
        "jcareer-integration-status-v1"
    )
    captured_at: datetime
    global_enabled: bool
    default_state: Literal["DISABLED_UNTIL_EXPLICITLY_CONFIGURED"] = (
        "DISABLED_UNTIL_EXPLICITLY_CONFIGURED"
    )
    observation_scope: Literal["CONFIGURATION_ONLY_NO_NETWORK_PROBE"] = (
        "CONFIGURATION_ONLY_NO_NETWORK_PROBE"
    )
    event_data_policy: Literal["SYNTHETIC_NON_PERSONAL_ONLY"] = (
        "SYNTHETIC_NON_PERSONAL_ONLY"
    )
    providers: list[ProviderStatus] = Field(min_length=3, max_length=3)
    idempotency_ttl_seconds: int = Field(ge=60, le=86_400)


class DeliveryReceipt(StrictContract):
    contract_version: Literal["jcareer-integration-receipt-v1"] = (
        "jcareer-integration-receipt-v1"
    )
    provider: DeliveryProvider
    event_id: str
    idempotency_ref: str = Field(pattern=r"^idem_[a-f0-9]{20}$")
    state: DeliveryState
    attempted: bool
    replayed: bool = False
    started_at: datetime
    completed_at: datetime
    duration_ms: int = Field(ge=0)
    failure_code: FailureCode | None = None
    provider_response_body_retained: Literal[False] = False
    secrets_retained: Literal[False] = False


class SyntheticSendRequest(StrictContract):
    providers: list[DeliveryProvider] = Field(
        default_factory=lambda: list(DeliveryProvider), min_length=1, max_length=3
    )
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)

    @field_validator("providers")
    @classmethod
    def providers_are_unique(
        cls, value: list[DeliveryProvider]
    ) -> list[DeliveryProvider]:
        if len(set(value)) != len(value):
            raise ValueError("providers must be unique")
        return value

    @field_validator("idempotency_key")
    @classmethod
    def safe_body_idempotency_key(cls, value: str | None) -> str | None:
        return normalise_idempotency_key(value) if value is not None else None


class SyntheticSendResponse(StrictContract):
    contract_version: Literal["jcareer-synthetic-integration-send-v1"] = (
        "jcareer-synthetic-integration-send-v1"
    )
    event: IntegrationEvent
    overall_state: Literal["ALL_DELIVERED", "PARTIAL_DELIVERY", "NO_DELIVERY"]
    failure_isolated: Literal[True] = True
    receipts: list[DeliveryReceipt] = Field(min_length=1, max_length=3)


def normalise_idempotency_key(value: str | None) -> str:
    if value is None:
        raise ValueError("an idempotency key is required")
    normalised = value.strip()
    if not IDEMPOTENCY_KEY_PATTERN.fullmatch(normalised):
        raise ValueError("idempotency key has an invalid format")
    if contains_sensitive_text(normalised):
        raise ValueError(
            "idempotency key must not contain direct identifiers or credentials"
        )
    return normalised
