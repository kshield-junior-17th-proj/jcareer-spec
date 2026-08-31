"""Slack webhook, Notion API, and TLS-only SMTP delivery adapters."""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from collections.abc import Callable
from email.message import EmailMessage
from typing import Protocol

import httpx

from .config import NotionSettings, SlackSettings, SmtpSettings
from .contracts import (
    ConfigurationState,
    DeliveryProvider,
    FailureCode,
    IntegrationEvent,
    ProviderStatus,
)


class DeliveryError(RuntimeError):
    """An adapter failure whose public representation is a bounded code only."""

    def __init__(self, code: FailureCode):
        self.code = code
        super().__init__(code.value)


class IntegrationAdapter(Protocol):
    provider: DeliveryProvider

    def status(self) -> ProviderStatus: ...

    async def deliver(self, event: IntegrationEvent) -> None: ...


def _configuration_state(
    *, enabled: bool, valid: bool, activation_flag_valid: bool
) -> ConfigurationState:
    if not activation_flag_valid:
        return ConfigurationState.INVALID
    if not enabled:
        return ConfigurationState.DISABLED
    return ConfigurationState.READY if valid else ConfigurationState.INVALID


def _assert_ready(status: ProviderStatus) -> None:
    if status.configuration_state == ConfigurationState.DISABLED:
        raise DeliveryError(FailureCode.PROVIDER_DISABLED)
    if status.configuration_state != ConfigurationState.READY:
        code = (
            FailureCode.HOST_NOT_ALLOWED
            if status.endpoint_configured and not status.target_host_allowed
            else FailureCode.CONFIGURATION_INVALID
        )
        raise DeliveryError(code)


class SlackWebhookAdapter:
    provider = DeliveryProvider.SLACK_WEBHOOK

    def __init__(
        self, settings: SlackSettings, *, client: httpx.AsyncClient | None = None
    ) -> None:
        self.settings = settings
        self._client = client

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            provider=self.provider,
            enabled=self.settings.effective_enabled,
            configuration_state=_configuration_state(
                enabled=self.settings.effective_enabled,
                valid=self.settings.valid,
                activation_flag_valid=self.settings.flag_valid,
            ),
            endpoint_configured=self.settings.configured,
            credential_configured=self.settings.webhook_url is not None,
            allowlist_configured=bool(self.settings.allowed_hosts)
            and self.settings.allowlist_valid,
            target_host_allowed=self.settings.target_host_allowed,
            timeout_seconds=self.settings.timeout_seconds,
        )

    async def deliver(self, event: IntegrationEvent) -> None:
        _assert_ready(self.status())
        if self.settings.webhook_url is None:
            raise DeliveryError(FailureCode.CONFIGURATION_INVALID)
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=httpx.Timeout(self.settings.timeout_seconds),
            follow_redirects=False,
            trust_env=False,
        )
        try:
            response = await client.post(
                self.settings.webhook_url.get_secret_value(),
                json={
                    "text": (
                        f"[SYNTHETIC] {event.summary} "
                        f"(event={event.event_id}, subject={event.subject_ref})"
                    )
                },
                headers={"Content-Type": "application/json"},
            )
            if response.status_code == 429:
                raise DeliveryError(FailureCode.RATE_LIMITED)
            if not 200 <= response.status_code < 300:
                raise DeliveryError(FailureCode.PROVIDER_REJECTED)
        except httpx.TimeoutException as exc:
            raise DeliveryError(FailureCode.TIMEOUT) from exc
        except httpx.HTTPError as exc:
            raise DeliveryError(FailureCode.TRANSPORT_ERROR) from exc
        finally:
            if owns_client:
                await client.aclose()


class NotionApiAdapter:
    provider = DeliveryProvider.NOTION_API
    notion_version = "2022-06-28"

    def __init__(
        self, settings: NotionSettings, *, client: httpx.AsyncClient | None = None
    ) -> None:
        self.settings = settings
        self._client = client

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            provider=self.provider,
            enabled=self.settings.effective_enabled,
            configuration_state=_configuration_state(
                enabled=self.settings.effective_enabled,
                valid=self.settings.valid,
                activation_flag_valid=self.settings.flag_valid,
            ),
            endpoint_configured=bool(self.settings.base_url),
            credential_configured=self.settings.api_token is not None
            and self.settings.parent_page_id is not None,
            allowlist_configured=bool(self.settings.allowed_hosts)
            and self.settings.allowlist_valid,
            target_host_allowed=self.settings.target_host_allowed,
            timeout_seconds=self.settings.timeout_seconds,
        )

    async def deliver(self, event: IntegrationEvent) -> None:
        _assert_ready(self.status())
        if self.settings.api_token is None or self.settings.parent_page_id is None:
            raise DeliveryError(FailureCode.CONFIGURATION_INVALID)
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=httpx.Timeout(self.settings.timeout_seconds),
            follow_redirects=False,
            trust_env=False,
        )
        token = self.settings.api_token.get_secret_value()
        parent_page_id = self.settings.parent_page_id.get_secret_value()
        try:
            response = await client.post(
                f"{self.settings.base_url.rstrip('/')}/v1/pages",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Notion-Version": self.notion_version,
                },
                json={
                    "parent": {"type": "page_id", "page_id": parent_page_id},
                    "properties": {
                        "title": {
                            "type": "title",
                            "title": [
                                {
                                    "type": "text",
                                    "text": {"content": event.summary},
                                }
                            ],
                        }
                    },
                    "children": [
                        {
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {
                                            "content": (
                                                f"Synthetic event {event.event_id}; "
                                                f"subject {event.subject_ref}; no personal data."
                                            )
                                        },
                                    }
                                ]
                            },
                        }
                    ],
                },
            )
            if response.status_code == 429:
                raise DeliveryError(FailureCode.RATE_LIMITED)
            if not 200 <= response.status_code < 300:
                raise DeliveryError(FailureCode.PROVIDER_REJECTED)
        except httpx.TimeoutException as exc:
            raise DeliveryError(FailureCode.TIMEOUT) from exc
        except httpx.HTTPError as exc:
            raise DeliveryError(FailureCode.TRANSPORT_ERROR) from exc
        finally:
            if owns_client:
                await client.aclose()


SmtpFactory = Callable[..., smtplib.SMTP]


class SmtpTlsAdapter:
    provider = DeliveryProvider.SMTP_TLS

    def __init__(
        self,
        settings: SmtpSettings,
        *,
        smtp_factory: SmtpFactory = smtplib.SMTP,
        smtp_ssl_factory: SmtpFactory = smtplib.SMTP_SSL,
        ssl_context_factory: Callable[[], ssl.SSLContext] = ssl.create_default_context,
    ) -> None:
        self.settings = settings
        self._smtp_factory = smtp_factory
        self._smtp_ssl_factory = smtp_ssl_factory
        self._ssl_context_factory = ssl_context_factory

    def status(self) -> ProviderStatus:
        credential_configured = (
            self.settings.username is not None and self.settings.password is not None
        )
        return ProviderStatus(
            provider=self.provider,
            enabled=self.settings.effective_enabled,
            configuration_state=_configuration_state(
                enabled=self.settings.effective_enabled,
                valid=self.settings.valid,
                activation_flag_valid=self.settings.flag_valid,
            ),
            endpoint_configured=bool(self.settings.host),
            credential_configured=credential_configured,
            allowlist_configured=bool(self.settings.allowed_hosts)
            and self.settings.allowlist_valid,
            target_host_allowed=self.settings.target_host_allowed,
            timeout_seconds=self.settings.timeout_seconds,
        )

    async def deliver(self, event: IntegrationEvent) -> None:
        _assert_ready(self.status())
        await asyncio.to_thread(self._deliver_sync, event)

    def _deliver_sync(self, event: IntegrationEvent) -> None:
        if self.settings.from_address is None or self.settings.to_address is None:
            raise DeliveryError(FailureCode.CONFIGURATION_INVALID)
        message = EmailMessage()
        message["Subject"] = "[J-Career synthetic] Integration connectivity probe"
        message["From"] = self.settings.from_address.get_secret_value()
        message["To"] = self.settings.to_address.get_secret_value()
        message.set_content(
            f"{event.summary}\n\n"
            f"Event: {event.event_id}\n"
            f"Subject: {event.subject_ref}\n"
            "Data classification: SYNTHETIC_NON_PERSONAL\n"
        )
        context = self._ssl_context_factory()
        try:
            if self.settings.tls_mode == "implicit":
                client_context = self._smtp_ssl_factory(
                    self.settings.host,
                    self.settings.port,
                    timeout=self.settings.timeout_seconds,
                    context=context,
                )
                with client_context as client:
                    self._authenticate_and_send(client, message)
            elif self.settings.tls_mode == "starttls":
                client_context = self._smtp_factory(
                    self.settings.host,
                    self.settings.port,
                    timeout=self.settings.timeout_seconds,
                )
                with client_context as client:
                    client.ehlo()
                    client.starttls(context=context)
                    client.ehlo()
                    self._authenticate_and_send(client, message)
            else:
                raise DeliveryError(FailureCode.CONFIGURATION_INVALID)
        except DeliveryError:
            raise
        except (TimeoutError, smtplib.SMTPServerDisconnected) as exc:
            raise DeliveryError(FailureCode.TIMEOUT) from exc
        except smtplib.SMTPResponseException as exc:
            if exc.smtp_code in {421, 429, 450, 451, 452}:
                raise DeliveryError(FailureCode.RATE_LIMITED) from exc
            raise DeliveryError(FailureCode.PROVIDER_REJECTED) from exc
        except (OSError, smtplib.SMTPException) as exc:
            raise DeliveryError(FailureCode.TRANSPORT_ERROR) from exc

    def _authenticate_and_send(
        self, client: smtplib.SMTP, message: EmailMessage
    ) -> None:
        if self.settings.username is not None and self.settings.password is not None:
            client.login(
                self.settings.username.get_secret_value(),
                self.settings.password.get_secret_value(),
            )
        client.send_message(message)
