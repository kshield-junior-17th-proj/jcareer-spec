from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker


MEMBER_DATABASE_URL = os.getenv(
    "MEMBER_DATABASE_URL", "sqlite:///./jcareer-member-runtime.db"
)
COMPANY_DATABASE_URL = os.getenv(
    "COMPANY_DATABASE_URL", "sqlite:///./jcareer-company-runtime.db"
)


def database_target(database_url: str) -> tuple[str, str, int | None, str]:
    """Return the physical database target without credentials or query options."""

    parsed = make_url(database_url)
    backend = parsed.get_backend_name()
    if backend == "sqlite":
        database = parsed.database or ":memory:"
        if database != ":memory:":
            database = str(Path(database).expanduser().resolve())
        return backend, "", None, database
    default_ports = {"postgresql": 5432, "mysql": 3306, "mariadb": 3306}
    return (
        backend,
        (parsed.host or "").lower(),
        parsed.port or default_ports.get(backend),
        parsed.database or "",
    )


if database_target(MEMBER_DATABASE_URL) == database_target(COMPANY_DATABASE_URL):
    raise RuntimeError("MEMBER_DATABASE_URL and COMPANY_DATABASE_URL must be different")


def _engine(database_url: str):
    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)


member_engine = _engine(MEMBER_DATABASE_URL)
company_engine = _engine(COMPANY_DATABASE_URL)


class MemberBase(DeclarativeBase):
    pass


class CompanyBase(DeclarativeBase):
    pass


# One unit-of-work facade routes each mapped class to its owning database. There
# are deliberately no ORM relationships or database foreign keys across the two
# stores. A commit that touches both stores is not atomic. That AS-IS boundary is
# declared as an unexecuted consulting scenario; partial commit fault injection
# is not claimed by this source.
SessionLocal = sessionmaker(
    bind=member_engine,
    binds={CompanyBase: company_engine},
    autoflush=False,
    expire_on_commit=False,
)


def ensure_runtime_schema() -> None:
    """Apply additive compatibility columns for the synthetic runtime.

    This keeps existing synthetic volumes usable. It is not a substitute for the
    deployment migration workflow that remains outside this runtime's scope.
    """

    columns = {
        column["name"] for column in inspect(company_engine).get_columns("companies")
    }
    additions = {
        "direction_statement": "TEXT NOT NULL DEFAULT ''",
        "declared_values": "JSON NOT NULL DEFAULT '[]'",
        "profile_version": "VARCHAR(80) NOT NULL DEFAULT 'company-profile-unset'",
        "opendart_corp_code": "VARCHAR(8)",
        "opendart_snapshot": "JSON NOT NULL DEFAULT '{}'",
        "opendart_sync_state": "VARCHAR(40) NOT NULL DEFAULT 'NOT_LINKED'",
        "opendart_snapshot_version": (
            "VARCHAR(80) NOT NULL DEFAULT 'opendart-snapshot-unset'"
        ),
        "opendart_synced_at": "TIMESTAMP",
        "opendart_last_attempt_at": "TIMESTAMP",
        "opendart_pending_request_id": "VARCHAR(36)",
        "opendart_pending_requested_at": "TIMESTAMP",
    }
    with company_engine.begin() as connection:
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE companies ADD COLUMN {name} {definition}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
