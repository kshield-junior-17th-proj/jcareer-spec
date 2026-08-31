"""Environment parsing and SSRF-resistant endpoint validation."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from os import environ as process_environment
from urllib.parse import urlsplit

from pydantic import SecretStr


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
_HOST_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
_ADDRESS_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
)
_PAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def _read_bool(
    values: Mapping[str, str], name: str, *, fallback: str | None = None
) -> tuple[bool, bool]:
    raw = values.get(name)
    if raw is None and fallback is not None:
        raw = values.get(fallback)
    if raw is None or not raw.strip():
        return False, True
    normalised = raw.strip().lower()
    if normalised in _TRUE_VALUES:
        return True, True
    if normalised in _FALSE_VALUES:
        return False, True
    return False, False


def _read_float(
    values: Mapping[str, str],
    name: str,
    *,
    default: float,
    minimum: float,
    maximum: float,
) -> tuple[float, bool]:
    try:
        result = float(values.get(name, str(default)).strip())
    except (TypeError, ValueError):
        return default, False
    if not minimum <= result <= maximum:
        return default, False
    return result, True


def _read_int(
    values: Mapping[str, str], name: str, *, default: int, minimum: int, maximum: int
) -> tuple[int, bool]:
    try:
        result = int(values.get(name, str(default)).strip())
    except (TypeError, ValueError):
        return default, False
    if not minimum <= result <= maximum:
        return default, False
    return result, True


def _normalise_hostname(value: str) -> str | None:
    hostname = value.strip().rstrip(".").lower()
    if not hostname or "*" in hostname or not _HOST_PATTERN.fullmatch(hostname):
        return None
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return hostname
    return None


def _parse_allowlist(raw: str) -> tuple[frozenset[str], bool]:
    if not raw.strip():
        return frozenset(), True
    hosts: set[str] = set()
    valid = True
    for item in raw.split(","):
        host = _normalise_hostname(item)
        if host is None:
            valid = False
        else:
            hosts.add(host)
    return frozenset(hosts), valid


def _https_target(raw: str, *, root_only: bool) -> tuple[str | None, bool]:
    if not raw:
        return None, False
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError:
        return None, False
    hostname = _normalise_hostname(parsed.hostname or "")
    valid = (
        parsed.scheme.lower() == "https"
        and hostname is not None
        and parsed.username is None
        and parsed.password is None
        and port in {None, 443}
        and not parsed.query
        and not parsed.fragment
    )
    if root_only and parsed.path not in {"", "/"}:
        valid = False
    return hostname, valid


def _valid_mailbox(raw: str) -> bool:
    return (
        3 <= len(raw) <= 254
        and "\r" not in raw
        and "\n" not in raw
        and _ADDRESS_PATTERN.fullmatch(raw) is not None
    )


@dataclass(frozen=True)
class CommonSettings:
    global_enabled: bool
    global_flag_valid: bool
    timeout_seconds: float
    timeout_valid: bool
    idempotency_ttl_seconds: int
    idempotency_max_entries: int


@dataclass(frozen=True)
class SlackSettings:
    requested_enabled: bool
    flag_valid: bool
    webhook_url: SecretStr | None = field(repr=False)
    allowed_hosts: frozenset[str]
    allowlist_valid: bool
    target_host: str | None
    target_valid: bool
    target_host_allowed: bool
    configured: bool
    effective_enabled: bool
    valid: bool
    timeout_seconds: float


@dataclass(frozen=True)
class NotionSettings:
    requested_enabled: bool
    flag_valid: bool
    base_url: str
    api_token: SecretStr | None = field(repr=False)
    parent_page_id: SecretStr | None = field(repr=False)
    allowed_hosts: frozenset[str]
    allowlist_valid: bool
    target_host: str | None
    target_valid: bool
    target_host_allowed: bool
    configured: bool
    effective_enabled: bool
    valid: bool
    timeout_seconds: float


@dataclass(frozen=True)
class SmtpSettings:
    requested_enabled: bool
    flag_valid: bool
    host: str
    port: int
    tls_mode: str
    username: SecretStr | None = field(repr=False)
    password: SecretStr | None = field(repr=False)
    from_address: SecretStr | None = field(repr=False)
    to_address: SecretStr | None = field(repr=False)
    allowed_hosts: frozenset[str]
    allowlist_valid: bool
    target_host: str | None
    target_host_allowed: bool
    configured: bool
    effective_enabled: bool
    valid: bool
    timeout_seconds: float


@dataclass(frozen=True)
class IntegrationSettings:
    common: CommonSettings
    slack: SlackSettings
    notion: NotionSettings
    smtp: SmtpSettings

    @classmethod
    def from_environment(
        cls, values: Mapping[str, str] | None = None
    ) -> "IntegrationSettings":
        source = process_environment if values is None else values
        global_enabled, global_flag_valid = _read_bool(
            source, "INTEGRATIONS_ENABLED", fallback="FLAG_INTEGRATIONS"
        )
        timeout_seconds, timeout_valid = _read_float(
            source,
            "INTEGRATION_TIMEOUT_SECONDS",
            default=3.0,
            minimum=0.05,
            maximum=30.0,
        )
        idempotency_ttl, _ = _read_int(
            source,
            "INTEGRATION_IDEMPOTENCY_TTL_SECONDS",
            default=900,
            minimum=60,
            maximum=86_400,
        )
        idempotency_max_entries, _ = _read_int(
            source,
            "INTEGRATION_IDEMPOTENCY_MAX_ENTRIES",
            default=1_000,
            minimum=10,
            maximum=10_000,
        )
        common = CommonSettings(
            global_enabled=global_enabled,
            global_flag_valid=global_flag_valid,
            timeout_seconds=timeout_seconds,
            timeout_valid=timeout_valid,
            idempotency_ttl_seconds=idempotency_ttl,
            idempotency_max_entries=idempotency_max_entries,
        )

        slack_requested, slack_flag_valid = _read_bool(source, "SLACK_WEBHOOK_ENABLED")
        slack_raw_url = source.get("SLACK_WEBHOOK_URL", "").strip()
        slack_hosts, slack_allowlist_valid = _parse_allowlist(
            source.get("SLACK_ALLOWED_HOSTS", "hooks.slack.com")
        )
        slack_host, slack_target_valid = _https_target(slack_raw_url, root_only=False)
        slack_path_valid = False
        if slack_raw_url:
            try:
                slack_path_valid = urlsplit(slack_raw_url).path.startswith("/services/")
            except ValueError:
                slack_path_valid = False
        slack_configured = bool(slack_raw_url)
        slack_effective = global_enabled and slack_requested
        slack_host_allowed = slack_host is not None and slack_host in slack_hosts
        slack_valid = all(
            (
                global_flag_valid,
                slack_flag_valid,
                timeout_valid,
                slack_configured,
                slack_allowlist_valid,
                slack_target_valid,
                slack_path_valid,
                slack_host_allowed,
            )
        )
        slack = SlackSettings(
            requested_enabled=slack_requested,
            flag_valid=slack_flag_valid and global_flag_valid,
            webhook_url=SecretStr(slack_raw_url) if slack_raw_url else None,
            allowed_hosts=slack_hosts,
            allowlist_valid=slack_allowlist_valid,
            target_host=slack_host,
            target_valid=slack_target_valid and slack_path_valid,
            target_host_allowed=slack_host_allowed,
            configured=slack_configured,
            effective_enabled=slack_effective,
            valid=slack_valid,
            timeout_seconds=timeout_seconds,
        )

        notion_requested, notion_flag_valid = _read_bool(source, "NOTION_API_ENABLED")
        notion_base_url = source.get(
            "NOTION_API_BASE_URL", "https://api.notion.com"
        ).strip()
        notion_token = source.get("NOTION_API_TOKEN", "").strip()
        notion_parent = source.get("NOTION_PARENT_PAGE_ID", "").strip()
        notion_hosts, notion_allowlist_valid = _parse_allowlist(
            source.get("NOTION_ALLOWED_HOSTS", "api.notion.com")
        )
        notion_host, notion_target_valid = _https_target(
            notion_base_url, root_only=True
        )
        notion_configured = bool(
            notion_token and notion_parent and _PAGE_ID_PATTERN.fullmatch(notion_parent)
        )
        notion_effective = global_enabled and notion_requested
        notion_host_allowed = notion_host is not None and notion_host in notion_hosts
        notion_valid = all(
            (
                global_flag_valid,
                notion_flag_valid,
                timeout_valid,
                notion_configured,
                notion_allowlist_valid,
                notion_target_valid,
                notion_host_allowed,
            )
        )
        notion = NotionSettings(
            requested_enabled=notion_requested,
            flag_valid=notion_flag_valid and global_flag_valid,
            base_url=notion_base_url,
            api_token=SecretStr(notion_token) if notion_token else None,
            parent_page_id=SecretStr(notion_parent) if notion_parent else None,
            allowed_hosts=notion_hosts,
            allowlist_valid=notion_allowlist_valid,
            target_host=notion_host,
            target_valid=notion_target_valid,
            target_host_allowed=notion_host_allowed,
            configured=notion_configured,
            effective_enabled=notion_effective,
            valid=notion_valid,
            timeout_seconds=timeout_seconds,
        )

        smtp_requested, smtp_flag_valid = _read_bool(
            source, "SMTP_TLS_ENABLED", fallback="FLAG_MAIL"
        )
        smtp_raw_host = source.get("SMTP_HOST", "").strip()
        smtp_host = _normalise_hostname(smtp_raw_host)
        smtp_port, smtp_port_valid = _read_int(
            source, "SMTP_PORT", default=465, minimum=1, maximum=65_535
        )
        smtp_tls_mode = source.get("SMTP_TLS_MODE", "implicit").strip().lower()
        smtp_mode_valid = smtp_tls_mode in {"implicit", "starttls"}
        smtp_username = source.get("SMTP_USERNAME", "").strip()
        smtp_password = source.get("SMTP_PASSWORD", "")
        smtp_from = source.get("SMTP_FROM_ADDRESS", "").strip()
        smtp_to = source.get("SMTP_TO_ADDRESS", "").strip()
        smtp_hosts, smtp_allowlist_valid = _parse_allowlist(
            source.get("SMTP_ALLOWED_HOSTS", "")
        )
        smtp_host_allowed = smtp_host is not None and smtp_host in smtp_hosts
        smtp_auth_valid = bool(smtp_username) == bool(smtp_password)
        smtp_configured = bool(
            smtp_host
            and _valid_mailbox(smtp_from)
            and _valid_mailbox(smtp_to)
            and smtp_auth_valid
        )
        smtp_effective = global_enabled and smtp_requested
        smtp_valid = all(
            (
                global_flag_valid,
                smtp_flag_valid,
                timeout_valid,
                smtp_port_valid,
                smtp_mode_valid,
                smtp_allowlist_valid,
                smtp_host_allowed,
                smtp_configured,
            )
        )
        smtp = SmtpSettings(
            requested_enabled=smtp_requested,
            flag_valid=smtp_flag_valid and global_flag_valid,
            host=smtp_raw_host,
            port=smtp_port,
            tls_mode=smtp_tls_mode,
            username=SecretStr(smtp_username) if smtp_username else None,
            password=SecretStr(smtp_password) if smtp_password else None,
            from_address=SecretStr(smtp_from) if smtp_from else None,
            to_address=SecretStr(smtp_to) if smtp_to else None,
            allowed_hosts=smtp_hosts,
            allowlist_valid=smtp_allowlist_valid,
            target_host=smtp_host,
            target_host_allowed=smtp_host_allowed,
            configured=smtp_configured,
            effective_enabled=smtp_effective,
            valid=smtp_valid,
            timeout_seconds=timeout_seconds,
        )
        return cls(common=common, slack=slack, notion=notion, smtp=smtp)
