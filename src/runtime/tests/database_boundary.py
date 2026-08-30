from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

from smoke import request, wait_ready


RUNTIME_ROOT = Path(__file__).resolve().parents[1]


def psql(role: str, database: str, sql: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            role,
            "-d",
            database,
            "-tAc",
            sql,
        ],
        cwd=RUNTIME_ROOT,
        check=False,
        text=True,
        encoding="utf-8",
        errors="strict",
        capture_output=True,
    )


def table_names(role: str, database: str) -> set[str]:
    result = psql(
        role,
        database,
        "select tablename from pg_tables where schemaname='public' order by tablename;",
    )
    assert result.returncode == 0, result.stderr
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def main() -> None:
    wait_ready()
    member_tables = table_names("jcareer_member_app", "jcareer_member")
    company_tables = table_names("jcareer_company_app", "jcareer_company")

    assert member_tables == {
        "applications",
        "audit_events",
        "consent_events",
        "resumes",
        "users",
    }, member_tables
    assert company_tables == {"companies", "jobs"}, company_tables
    assert member_tables.isdisjoint(company_tables)

    member_to_company = psql("jcareer_member_app", "jcareer_company", "select 1;")
    company_to_member = psql("jcareer_company_app", "jcareer_member", "select 1;")
    assert member_to_company.returncode != 0
    assert company_to_member.returncode != 0
    assert "permission denied for database" in member_to_company.stderr.lower()
    assert "permission denied for database" in company_to_member.stderr.lower()

    suffix = uuid.uuid4().hex[:10]
    company_name = f"합성 경계기업 {suffix}"
    email = f"db-boundary-{suffix}@example.invalid"
    try:
        status, signup = request(
            "/api/v1/auth/signup/recruiter",
            method="POST",
            body={
                "email": email,
                "password": "Demo123!",
                "display_name": f"합성 담당자 {suffix}",
                "company_name": company_name,
                "company_address": "합성 주소",
            },
        )
        assert status == 201, signup
        signup_user_id = str(uuid.UUID(str(signup["user"]["id"])))
        signup_company_id = str(uuid.UUID(str(signup["user"]["company_id"])))
        assert signup["user"]["company_name"] == company_name
        status, company_profile = request(
            "/api/v1/recruiter/company-profile",
            token=signup["access_token"],
        )
        assert status == 200, company_profile
        assert company_profile["source"] == "unset"
        assert company_profile["company_id"] == signup_company_id

        member_row = psql(
            "jcareer_member_app",
            "jcareer_member",
            f"select id || '|' || role || '|' || company_id from users where email='{email}';",
        )
        company_row = psql(
            "jcareer_company_app",
            "jcareer_company",
            f"select id || '|' || name from companies where name='{company_name}';",
        )
        assert member_row.returncode == 0
        assert member_row.stdout.strip() == f"{signup_user_id}|recruiter|{signup_company_id}"
        assert company_row.returncode == 0
        assert company_row.stdout.strip() == f"{signup_company_id}|{company_name}"
    finally:
        member_cleanup = psql(
            "jcareer_member_app",
            "jcareer_member",
            "delete from audit_events where actor_user_id in "
            f"(select id from users where email='{email}');"
            f"delete from users where email='{email}';",
        )
        company_cleanup = psql(
            "jcareer_company_app",
            "jcareer_company",
            "delete from jobs where company_id in "
            f"(select id from companies where name='{company_name}');"
            f"delete from companies where name='{company_name}';",
        )
        assert member_cleanup.returncode == 0, member_cleanup.stderr
        assert company_cleanup.returncode == 0, company_cleanup.stderr
        member_residue = psql(
            "jcareer_member_app",
            "jcareer_member",
            f"select count(*) from users where email='{email}';",
        )
        company_residue = psql(
            "jcareer_company_app",
            "jcareer_company",
            f"select count(*) from companies where name='{company_name}';",
        )
        assert member_residue.returncode == 0 and member_residue.stdout.strip() == "0"
        assert company_residue.returncode == 0 and company_residue.stdout.strip() == "0"

    print("J-Career member/company database boundary: PASS")
    print("member tables=5, company tables=2, cross-role CONNECT denied, exact logical link verified, synthetic rows cleaned")


if __name__ == "__main__":
    main()
