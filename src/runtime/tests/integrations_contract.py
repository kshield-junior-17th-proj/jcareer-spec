from __future__ import annotations

import asyncio
import json
import sys
import time
import unittest
import warnings
from pathlib import Path
from types import SimpleNamespace

import httpx
from pydantic import ValidationError


API_ROOT = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(API_ROOT))

from app.integrations.adapters import (  # noqa: E402
    DeliveryError,
    SmtpTlsAdapter,
)
from app.integrations.config import IntegrationSettings  # noqa: E402
from app.integrations.contracts import (  # noqa: E402
    ConfigurationState,
    DeliveryProvider,
    DeliveryState,
    FailureCode,
    IntegrationEvent,
    ProviderStatus,
)
from app.integrations.redaction import redact_text, redact_value  # noqa: E402
from app.integrations.service import IntegrationService  # noqa: E402


SYNTHETIC_EVENT = IntegrationEvent(
    event_id="evt_0123456789abcdef01234567",
    summary="J-Career synthetic integration connectivity probe",
)


def enabled_environment(*, tls_mode: str = "implicit") -> dict[str, str]:
    return {
        "INTEGRATIONS_ENABLED": "true",
        "INTEGRATION_TIMEOUT_SECONDS": "0.25",
        "SLACK_WEBHOOK_ENABLED": "true",
        "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/T000/B000/synthetic-secret",
        "SLACK_ALLOWED_HOSTS": "hooks.slack.com",
        "NOTION_API_ENABLED": "true",
        "NOTION_API_BASE_URL": "https://api.notion.com",
        "NOTION_API_TOKEN": "secret_synthetic-notion-token",
        "NOTION_PARENT_PAGE_ID": "0123456789abcdef0123456789abcdef",
        "NOTION_ALLOWED_HOSTS": "api.notion.com",
        "SMTP_TLS_ENABLED": "true",
        "SMTP_HOST": "smtp.example.test",
        "SMTP_PORT": "465" if tls_mode == "implicit" else "587",
        "SMTP_TLS_MODE": tls_mode,
        "SMTP_USERNAME": "synthetic-user",
        "SMTP_PASSWORD": "smtp-synthetic-password",
        "SMTP_FROM_ADDRESS": "sender@example.test",
        "SMTP_TO_ADDRESS": "recipient@example.test",
        "SMTP_ALLOWED_HOSTS": "smtp.example.test",
    }


class FakeSmtp:
    def __init__(self, calls: list[tuple[str, object]]) -> None:
        self.calls = calls

    def __enter__(self):
        self.calls.append(("enter", True))
        return self

    def __exit__(self, *_args) -> None:
        self.calls.append(("exit", True))

    def ehlo(self) -> None:
        self.calls.append(("ehlo", True))

    def starttls(self, *, context) -> None:
        self.calls.append(("starttls", context is not None))

    def login(self, username: str, password: str) -> None:
        self.calls.append(("login", (username, password)))

    def send_message(self, message) -> None:
        self.calls.append(("send_message", message))


class StubAdapter:
    def __init__(
        self,
        provider: DeliveryProvider,
        action,
        *,
        timeout_seconds: float = 0.05,
    ) -> None:
        self.provider = provider
        self.action = action
        self.timeout_seconds = timeout_seconds
        self.calls = 0

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            provider=self.provider,
            enabled=True,
            configuration_state=ConfigurationState.READY,
            endpoint_configured=True,
            credential_configured=True,
            allowlist_configured=True,
            target_host_allowed=True,
            timeout_seconds=self.timeout_seconds,
        )

    async def deliver(self, event: IntegrationEvent) -> None:
        self.calls += 1
        await self.action(event)


class IntegrationConfigurationTests(unittest.TestCase):
    def test_defaults_are_disabled_and_configuration_only(self) -> None:
        service = IntegrationService.from_environment({})
        status = service.status()
        self.assertFalse(status.global_enabled)
        self.assertEqual(
            status.observation_scope, "CONFIGURATION_ONLY_NO_NETWORK_PROBE"
        )
        self.assertEqual(len(status.providers), 3)
        self.assertTrue(
            all(
                item.configuration_state == ConfigurationState.DISABLED
                and not item.enabled
                and not item.network_probe_performed
                for item in status.providers
            )
        )

    def test_configured_secrets_are_not_exposed_by_repr(self) -> None:
        values = enabled_environment()
        settings = IntegrationSettings.from_environment(values)
        rendered = repr(settings)
        for secret in (
            values["SLACK_WEBHOOK_URL"],
            values["NOTION_API_TOKEN"],
            values["NOTION_PARENT_PAGE_ID"],
            values["SMTP_PASSWORD"],
            values["SMTP_FROM_ADDRESS"],
            values["SMTP_TO_ADDRESS"],
        ):
            self.assertNotIn(secret, rendered)

    def test_event_contract_rejects_obvious_pii_and_credentials(self) -> None:
        for unsafe in (
            "Contact candidate@example.test",
            "Call 010-1234-5678",
            "Authorization: Bearer abcdefghijklmnop",
            "secret_abcdefghijklmnopqrstuvwxyz",
        ):
            with self.subTest(unsafe=unsafe), self.assertRaises(ValidationError):
                IntegrationEvent(event_id="evt_safe123", summary=unsafe)

    def test_redaction_is_recursive_and_covers_configured_secrets(self) -> None:
        webhook = "https://hooks.slack.com/services/T/B/private-value"
        password = "smtp-password-value"
        value = {
            "message": f"failed at {webhook}",
            "nested": [
                "Bearer abcdefghijklmnop",
                "candidate@example.test",
                "010-1234-5678",
                password,
            ],
        }
        rendered = json.dumps(
            redact_value(value, secrets=(webhook, password)), ensure_ascii=False
        )
        for secret in (webhook, password, "candidate@example.test", "010-1234-5678"):
            self.assertNotIn(secret, rendered)
        self.assertNotIn("abcdefghijklmnop", redact_text(value["nested"][0]))


class IntegrationDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_off_never_touches_any_transport(self) -> None:
        calls: list[str] = []

        def forbidden_http(_request: httpx.Request) -> httpx.Response:
            calls.append("http")
            raise AssertionError("disabled adapter attempted HTTP")

        def forbidden_smtp(*_args, **_kwargs):
            calls.append("smtp")
            raise AssertionError("disabled adapter attempted SMTP")

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(forbidden_http)
        ) as client:
            service = IntegrationService.from_environment(
                {},
                slack_client=client,
                notion_client=client,
                smtp_factory=forbidden_smtp,
                smtp_ssl_factory=forbidden_smtp,
            )
            response = await service.synthetic_send(
                providers=list(DeliveryProvider),
                idempotency_key="disabled-probe-001",
            )
        self.assertEqual(calls, [])
        self.assertEqual(response.overall_state, "NO_DELIVERY")
        self.assertTrue(
            all(
                receipt.state == DeliveryState.DISABLED
                and not receipt.attempted
                and receipt.failure_code == FailureCode.PROVIDER_DISABLED
                for receipt in response.receipts
            )
        )

    async def test_successful_adapters_are_idempotent_and_receipts_are_redacted(
        self,
    ) -> None:
        values = enabled_environment()
        http_calls: list[tuple[str, object]] = []
        smtp_calls: list[tuple[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            http_calls.append((request.url.host or "", body))
            if request.url.host == "hooks.slack.com":
                self.assertEqual(request.url.path.split("/")[1], "services")
                self.assertNotIn("Authorization", request.headers)
                self.assertEqual(set(body), {"text"})
                self.assertNotIn("@", body["text"])
                return httpx.Response(200, text="ok")
            if request.url.host == "api.notion.com":
                self.assertEqual(request.url.path, "/v1/pages")
                self.assertEqual(
                    request.headers["Authorization"],
                    f"Bearer {values['NOTION_API_TOKEN']}",
                )
                self.assertEqual(
                    body["parent"]["page_id"], values["NOTION_PARENT_PAGE_ID"]
                )
                return httpx.Response(200, json={"id": "provider-id-not-retained"})
            raise AssertionError("unexpected HTTP target")

        def smtp_ssl_factory(*args, **kwargs):
            smtp_calls.append(
                ("factory", (args[:2], kwargs.get("timeout"), "context" in kwargs))
            )
            return FakeSmtp(smtp_calls)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = IntegrationService.from_environment(
                values,
                slack_client=client,
                notion_client=client,
                smtp_ssl_factory=smtp_ssl_factory,
                ssl_context_factory=lambda: object(),
            )
            first = await service.synthetic_send(
                providers=list(DeliveryProvider),
                idempotency_key="success-probe-001",
            )
            second = await service.synthetic_send(
                providers=list(DeliveryProvider),
                idempotency_key="success-probe-001",
            )

        self.assertEqual(first.overall_state, "ALL_DELIVERED")
        self.assertTrue(
            all(item.state == DeliveryState.DELIVERED for item in first.receipts)
        )
        self.assertTrue(all(not item.replayed for item in first.receipts))
        self.assertTrue(all(item.replayed for item in second.receipts))
        self.assertEqual(len(http_calls), 2)
        self.assertEqual(sum(name == "factory" for name, _ in smtp_calls), 1)
        self.assertEqual(sum(name == "send_message" for name, _ in smtp_calls), 1)
        rendered_receipts = first.model_dump_json()
        for secret in (
            values["SLACK_WEBHOOK_URL"],
            values["NOTION_API_TOKEN"],
            values["NOTION_PARENT_PAGE_ID"],
            values["SMTP_PASSWORD"],
            values["SMTP_FROM_ADDRESS"],
            values["SMTP_TO_ADDRESS"],
            "success-probe-001",
            "provider-id-not-retained",
        ):
            self.assertNotIn(secret, rendered_receipts)

    async def test_starttls_is_mandatory_before_smtp_send(self) -> None:
        values = enabled_environment(tls_mode="starttls")
        settings = IntegrationSettings.from_environment(values)
        calls: list[tuple[str, object]] = []

        def smtp_factory(*args, **kwargs):
            calls.append(("factory", (args[:2], kwargs.get("timeout"))))
            return FakeSmtp(calls)

        adapter = SmtpTlsAdapter(
            settings.smtp,
            smtp_factory=smtp_factory,
            ssl_context_factory=lambda: object(),
        )
        await adapter.deliver(SYNTHETIC_EVENT)
        names = [name for name, _ in calls]
        self.assertLess(names.index("starttls"), names.index("login"))
        self.assertLess(names.index("login"), names.index("send_message"))

    async def test_allowlist_rejection_happens_before_http(self) -> None:
        values = enabled_environment()
        values["SLACK_WEBHOOK_URL"] = "https://attacker.example/services/T/B/value"
        calls = 0

        def forbidden(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            raise AssertionError("disallowed host reached transport")

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(forbidden)
        ) as client:
            service = IntegrationService.from_environment(
                values, slack_client=client, notion_client=client
            )
            response = await service.synthetic_send(
                providers=[DeliveryProvider.SLACK_WEBHOOK],
                idempotency_key="allowlist-probe-001",
            )
        self.assertEqual(calls, 0)
        receipt = response.receipts[0]
        self.assertEqual(receipt.state, DeliveryState.FAILED)
        self.assertFalse(receipt.attempted)
        self.assertEqual(receipt.failure_code, FailureCode.HOST_NOT_ALLOWED)

    async def test_provider_failures_and_timeout_are_isolated(self) -> None:
        async def succeeds(_event: IntegrationEvent) -> None:
            return None

        async def fails(_event: IntegrationEvent) -> None:
            raise DeliveryError(FailureCode.TRANSPORT_ERROR)

        async def stalls(_event: IntegrationEvent) -> None:
            await asyncio.sleep(0.5)

        adapters = [
            StubAdapter(DeliveryProvider.SLACK_WEBHOOK, succeeds),
            StubAdapter(DeliveryProvider.NOTION_API, fails),
            StubAdapter(DeliveryProvider.SMTP_TLS, stalls),
        ]
        service = IntegrationService(IntegrationSettings.from_environment({}), adapters)
        started = time.monotonic()
        response = await service.synthetic_send(
            providers=list(DeliveryProvider),
            idempotency_key="isolation-probe-001",
        )
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 0.3)
        self.assertEqual(response.overall_state, "PARTIAL_DELIVERY")
        by_provider = {item.provider: item for item in response.receipts}
        self.assertEqual(
            by_provider[DeliveryProvider.SLACK_WEBHOOK].state,
            DeliveryState.DELIVERED,
        )
        self.assertEqual(
            by_provider[DeliveryProvider.NOTION_API].failure_code,
            FailureCode.TRANSPORT_ERROR,
        )
        self.assertEqual(
            by_provider[DeliveryProvider.SMTP_TLS].failure_code,
            FailureCode.TIMEOUT,
        )

    async def test_concurrent_retries_share_one_provider_attempt(self) -> None:
        async def succeeds_after_yield(_event: IntegrationEvent) -> None:
            await asyncio.sleep(0.02)

        slack = StubAdapter(DeliveryProvider.SLACK_WEBHOOK, succeeds_after_yield)
        notion = StubAdapter(DeliveryProvider.NOTION_API, succeeds_after_yield)
        smtp = StubAdapter(DeliveryProvider.SMTP_TLS, succeeds_after_yield)
        service = IntegrationService(
            IntegrationSettings.from_environment({}), [slack, notion, smtp]
        )
        first, second = await asyncio.gather(
            service.synthetic_send(
                providers=[DeliveryProvider.SLACK_WEBHOOK],
                idempotency_key="concurrent-probe-001",
            ),
            service.synthetic_send(
                providers=[DeliveryProvider.SLACK_WEBHOOK],
                idempotency_key="concurrent-probe-001",
            ),
        )
        self.assertEqual(slack.calls, 1)
        self.assertEqual(
            sorted((first.receipts[0].replayed, second.receipts[0].replayed)),
            [False, True],
        )


class IntegrationRouteTests(unittest.TestCase):
    def test_admin_routes_are_registered_without_changing_recommendations(self) -> None:
        import app.main as api_main

        paths = api_main.app.openapi()["paths"]
        self.assertIn("/api/v1/admin/integrations/status", paths)
        self.assertIn("/api/v1/admin/integrations/synthetic-send", paths)
        self.assertIn("/api/v1/candidates/me/recommendations", paths)
        self.assertIn("/api/v1/recruiter/jobs/{job_id}/recommendations", paths)

    def test_admin_api_is_role_gated_and_default_send_is_network_free(self) -> None:
        import app.main as api_main
        from app.database import get_db
        from app.integrations.router import get_integration_service
        from app.security import current_user

        class FakeSession:
            def add(self, _value) -> None:
                return None

            def commit(self) -> None:
                return None

            def rollback(self) -> None:
                return None

        fake_db = FakeSession()
        disabled_service = IntegrationService.from_environment({})
        api_main.app.dependency_overrides[get_db] = lambda: fake_db
        api_main.app.dependency_overrides[get_integration_service] = lambda: (
            disabled_service
        )
        api_main.app.dependency_overrides[current_user] = lambda: SimpleNamespace(
            id="candidate-test", role="candidate", company_id=None
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from fastapi.testclient import TestClient

            client = TestClient(api_main.app)
        try:
            denied = client.get("/api/v1/admin/integrations/status")
            self.assertEqual(denied.status_code, 403)

            api_main.app.dependency_overrides[current_user] = lambda: SimpleNamespace(
                id="admin-test", role="admin", company_id=None
            )
            status_response = client.get("/api/v1/admin/integrations/status")
            self.assertEqual(status_response.status_code, 200)
            self.assertEqual(
                status_response.headers["cache-control"], "no-store, private"
            )
            self.assertFalse(status_response.json()["global_enabled"])

            send_response = client.post(
                "/api/v1/admin/integrations/synthetic-send",
                headers={"Idempotency-Key": "api-probe-001"},
                json={},
            )
            self.assertEqual(send_response.status_code, 200)
            self.assertTrue(
                all(
                    item["state"] == "DISABLED"
                    for item in send_response.json()["receipts"]
                )
            )
            self.assertNotIn("api-probe-001", send_response.text)
            self.assertEqual(
                client.post(
                    "/api/v1/admin/integrations/synthetic-send", json={}
                ).status_code,
                422,
            )
        finally:
            api_main.app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main(verbosity=2)
