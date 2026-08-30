from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import CompanyBase, MemberBase


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Company(CompanyBase):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    address: Mapped[str] = mapped_column(String(240), default="")
    direction_statement: Mapped[str] = mapped_column(Text, default="")
    declared_values: Mapped[list[str]] = mapped_column(JSON, default=list)
    profile_version: Mapped[str] = mapped_column(String(80), default="company-profile-unset")
    opendart_corp_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    opendart_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    opendart_sync_state: Mapped[str] = mapped_column(String(40), default="NOT_LINKED")
    opendart_snapshot_version: Mapped[str] = mapped_column(
        String(80), default="opendart-snapshot-unset"
    )
    opendart_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    opendart_last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    opendart_pending_request_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    opendart_pending_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), default="approved")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(MemberBase):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    display_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), index=True)
    # Logical reference into the separate company database. Cross-database
    # foreign keys are intentionally impossible, so the API validates ownership.
    company_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)



class ConsentEvent(MemberBase):
    __tablename__ = "consent_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    consent_type: Mapped[str] = mapped_column(String(50), default="privacy_core")
    action: Mapped[str] = mapped_column(String(20))
    policy_version: Mapped[str] = mapped_column(String(40), default="2026-05")
    collected_items: Mapped[list[str]] = mapped_column(JSON, default=list)
    purposes: Mapped[list[str]] = mapped_column(JSON, default=list)
    legal_basis: Mapped[str] = mapped_column(String(80), default="consent")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Resume(MemberBase):
    __tablename__ = "resumes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(40), default="")
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    address_region: Mapped[str] = mapped_column(String(120), default="")
    education: Mapped[str] = mapped_column(String(180), default="")
    desired_role: Mapped[str] = mapped_column(String(120), default="")
    years_experience: Mapped[int] = mapped_column(Integer, default=0)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    certificates: Mapped[list[str]] = mapped_column(JSON, default=list)
    self_intro: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Job(CompanyBase):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    title: Mapped[str] = mapped_column(String(180), index=True)
    summary: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(120), index=True)
    employment_type: Mapped[str] = mapped_column(String(40), default="정규직")
    required_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    min_experience: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    company: Mapped[Company] = relationship()


class Application(MemberBase):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("job_id", "candidate_id", name="uq_application_job_candidate"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # Logical reference into the separate company database.
    job_id: Mapped[str] = mapped_column(String(36), index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="applied", index=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    candidate: Mapped[User] = relationship()


class AuditEvent(MemberBase):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    actor_role: Mapped[str] = mapped_column(String(30), default="system")
    company_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    target_type: Mapped[str] = mapped_column(String(50), default="")
    target_ref: Mapped[str] = mapped_column(String(100), default="")
    purpose: Mapped[str] = mapped_column(String(120), default="service_operation")
    action: Mapped[str] = mapped_column(String(80), default="")
    result: Mapped[str] = mapped_column(String(40), default="success")
    correlation_id: Mapped[str] = mapped_column(String(36), default=new_id, index=True)
    retention_class: Mapped[str] = mapped_column(String(50), default="asis_default")
    detail: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
