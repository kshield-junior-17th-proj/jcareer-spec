"""Failure-isolated delivery orchestration with bounded in-memory idempotency."""

from __future__ import annotations

import asyncio
import hashlib
import json
import ssl
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from .adapters import (
    DeliveryError,
    IntegrationAdapter,
    NotionApiAdapter,
    SlackWebhookAdapter,
    SmtpFactory,
    SmtpTlsAdapter,
)
from .config import IntegrationSettings
from .contracts import (
    ConfigurationState,
    DeliveryProvider,
    DeliveryReceipt,
    DeliveryState,
    FailureCode,
    IntegrationEvent,
    IntegrationStatusResponse,
    SyntheticSendResponse,
    normalise_idempotency_key,
)


class IdempotencyConflict(ValueError):
    pass


class IdempotencyCapacityError(RuntimeError):
    pass


@dataclass
class _IdempotencyEntry:
    event_fingerprint: str
    expires_at: float
    task: asyncio.Task[DeliveryReceipt]


@dataclass(frozen=True)
class _IdempotencyOperation:
    provider: DeliveryProvider
    idempotency_key: str
    event_fingerprint: str
    operation: Callable[[], Awaitable[DeliveryReceipt]]


class IdempotencyStore:
    def __init__(self, *, ttl_seconds: int, max_entries: int) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._entries: dict[tuple[DeliveryProvider, str], _IdempotencyEntry] = {}
        self._lock = asyncio.Lock()

    async def execute(
        self,
        *,
        provider: DeliveryProvider,
        idempotency_key: str,
        event_fingerprint: str,
        operation: Callable[[], Awaitable[DeliveryReceipt]],
    ) -> DeliveryReceipt:
        receipts = await self.execute_batch(
            [
                _IdempotencyOperation(
                    provider=provider,
                    idempotency_key=idempotency_key,
                    event_fingerprint=event_fingerprint,
                    operation=operation,
                )
            ]
        )
        return receipts[0]

    async def execute_batch(
        self, operations: list[_IdempotencyOperation]
    ) -> list[DeliveryReceipt]:
        """Atomically reserve a provider batch before starting any side effect."""

        if not operations:
            return []
        now = time.monotonic()
        plans: list[
            tuple[
                asyncio.Task[DeliveryReceipt] | None,
                bool,
                _IdempotencyOperation,
                tuple[DeliveryProvider, str],
            ]
        ] = []
        async with self._lock:
            self._prune(now)
            scopes: set[tuple[DeliveryProvider, str]] = set()
            new_entries = 0
            for operation_spec in operations:
                key_hash = hashlib.sha256(
                    operation_spec.idempotency_key.encode("utf-8")
                ).hexdigest()
                scope = (operation_spec.provider, key_hash)
                if scope in scopes:
                    raise ValueError("idempotency batch scopes must be unique")
                scopes.add(scope)
                entry = self._entries.get(scope)
                if entry is not None and (
                    entry.event_fingerprint != operation_spec.event_fingerprint
                ):
                    raise IdempotencyConflict(
                        "idempotency key was already used for another event"
                    )
                if entry is None:
                    new_entries += 1
                    plans.append((None, False, operation_spec, scope))
                else:
                    plans.append((entry.task, True, operation_spec, scope))

            self._make_capacity(required=new_entries)
            materialised: list[tuple[asyncio.Task[DeliveryReceipt], bool]] = []
            for task, replayed, operation_spec, scope in plans:
                if task is None:
                    task = asyncio.create_task(operation_spec.operation())
                    self._entries[scope] = _IdempotencyEntry(
                        event_fingerprint=operation_spec.event_fingerprint,
                        expires_at=now + self.ttl_seconds,
                        task=task,
                    )
                materialised.append((task, replayed))

        receipts: list[DeliveryReceipt] = []
        for task, replayed in materialised:
            receipt = await asyncio.shield(task)
            receipts.append(receipt.model_copy(update={"replayed": replayed}))
        return receipts

    def _prune(self, now: float) -> None:
        expired = [
            key
            for key, entry in self._entries.items()
            if entry.expires_at <= now and entry.task.done()
        ]
        for key in expired:
            self._entries.pop(key, None)

    def _make_capacity(self, *, required: int = 1) -> None:
        if len(self._entries) + required > self.max_entries:
            raise IdempotencyCapacityError("idempotency store is at capacity")


class IntegrationService:
    def __init__(
        self,
        settings: IntegrationSettings,
        adapters: list[IntegrationAdapter],
        *,
        idempotency_store: IdempotencyStore | None = None,
    ) -> None:
        self.settings = settings
        self.adapters = {adapter.provider: adapter for adapter in adapters}
        expected = set(DeliveryProvider)
        if set(self.adapters) != expected:
            raise ValueError(
                "exactly one adapter for every integration provider is required"
            )
        self.idempotency_store = idempotency_store or IdempotencyStore(
            ttl_seconds=settings.common.idempotency_ttl_seconds,
            max_entries=settings.common.idempotency_max_entries,
        )

    @classmethod
    def from_environment(
        cls,
        values=None,
        *,
        slack_client: httpx.AsyncClient | None = None,
        notion_client: httpx.AsyncClient | None = None,
        smtp_factory: SmtpFactory | None = None,
        smtp_ssl_factory: SmtpFactory | None = None,
        ssl_context_factory: Callable[[], ssl.SSLContext] | None = None,
    ) -> "IntegrationService":
        settings = IntegrationSettings.from_environment(values)
        smtp_kwargs = {}
        if smtp_factory is not None:
            smtp_kwargs["smtp_factory"] = smtp_factory
        if smtp_ssl_factory is not None:
            smtp_kwargs["smtp_ssl_factory"] = smtp_ssl_factory
        if ssl_context_factory is not None:
            smtp_kwargs["ssl_context_factory"] = ssl_context_factory
        adapters: list[IntegrationAdapter] = [
            SlackWebhookAdapter(settings.slack, client=slack_client),
            NotionApiAdapter(settings.notion, client=notion_client),
            SmtpTlsAdapter(settings.smtp, **smtp_kwargs),
        ]
        return cls(settings, adapters)

    def status(self) -> IntegrationStatusResponse:
        return IntegrationStatusResponse(
            captured_at=datetime.now(timezone.utc),
            global_enabled=self.settings.common.global_enabled,
            providers=[
                self.adapters[provider].status() for provider in DeliveryProvider
            ],
            idempotency_ttl_seconds=self.settings.common.idempotency_ttl_seconds,
        )

    async def synthetic_send(
        self,
        *,
        providers: list[DeliveryProvider],
        idempotency_key: str,
    ) -> SyntheticSendResponse:
        idempotency_key = normalise_idempotency_key(idempotency_key)
        if not providers or len(providers) > len(DeliveryProvider):
            raise ValueError("one to three providers are required")
        if len(set(providers)) != len(providers):
            raise ValueError("providers must be unique")
        event = synthetic_event(idempotency_key)
        fingerprint = _event_fingerprint(event)
        receipts = await self.idempotency_store.execute_batch(
            [
                _IdempotencyOperation(
                    provider=provider,
                    idempotency_key=idempotency_key,
                    event_fingerprint=fingerprint,
                    operation=lambda adapter=self.adapters[provider]: self._attempt(
                        adapter, event, idempotency_key
                    ),
                )
                for provider in providers
            ]
        )
        delivered = sum(
            receipt.state == DeliveryState.DELIVERED for receipt in receipts
        )
        if delivered == len(receipts):
            overall_state = "ALL_DELIVERED"
        elif delivered:
            overall_state = "PARTIAL_DELIVERY"
        else:
            overall_state = "NO_DELIVERY"
        return SyntheticSendResponse(
            event=event,
            overall_state=overall_state,
            receipts=receipts,
        )

    async def _attempt(
        self,
        adapter: IntegrationAdapter,
        event: IntegrationEvent,
        idempotency_key: str,
    ) -> DeliveryReceipt:
        status = adapter.status()
        started_at = datetime.now(timezone.utc)
        started = time.monotonic()
        attempted = False
        failure_code: FailureCode | None = None
        state = DeliveryState.FAILED
        if status.configuration_state == ConfigurationState.DISABLED:
            state = DeliveryState.DISABLED
            failure_code = FailureCode.PROVIDER_DISABLED
        elif status.configuration_state == ConfigurationState.INVALID:
            failure_code = (
                FailureCode.HOST_NOT_ALLOWED
                if status.endpoint_configured and not status.target_host_allowed
                else FailureCode.CONFIGURATION_INVALID
            )
        else:
            attempted = True
            try:
                if isinstance(adapter, SmtpTlsAdapter):
                    # smtplib owns the socket timeout. Cancelling its worker thread
                    # would allow a late send after a TIMEOUT receipt was returned.
                    await adapter.deliver(event)
                else:
                    await asyncio.wait_for(
                        adapter.deliver(event), timeout=status.timeout_seconds
                    )
                state = DeliveryState.DELIVERED
            except asyncio.TimeoutError:
                failure_code = FailureCode.TIMEOUT
            except DeliveryError as exc:
                failure_code = exc.code
            except Exception:
                failure_code = FailureCode.INTERNAL_ERROR
        completed_at = datetime.now(timezone.utc)
        duration_ms = max(0, int((time.monotonic() - started) * 1_000))
        key_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        return DeliveryReceipt(
            provider=adapter.provider,
            event_id=event.event_id,
            idempotency_ref=f"idem_{key_hash[:20]}",
            state=state,
            attempted=attempted,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            failure_code=failure_code,
        )


def synthetic_event(idempotency_key: str) -> IntegrationEvent:
    digest = hashlib.sha256(
        f"jcareer/synthetic-integration/{idempotency_key}".encode("utf-8")
    ).hexdigest()
    return IntegrationEvent(
        event_id=f"evt_{digest[:24]}",
        summary="J-Career synthetic integration connectivity probe",
    )


def _event_fingerprint(event: IntegrationEvent) -> str:
    canonical = json.dumps(
        event.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
