from __future__ import annotations

import os
import random
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Application, AuditEvent, Company, ConsentEvent, Job, Resume, User
from .opendart import OpenDartClient
from .outcome_store import seed_synthetic_outcome_dataset
from .security import hash_password


SEED = 20260826
DEMO_PASSWORD = "Demo123!"


def synthetic_id(kind: str, key: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"jcareer-synthetic/{kind}/{key}"))


def required_seed_ids() -> dict[str, set[str]]:
    company_ids = {synthetic_id("company", key) for key, _, _ in COMPANIES}
    user_ids = {
        synthetic_id("user", "admin"),
        synthetic_id("user", "candidate-demo"),
        synthetic_id("user", "recruiter-alpha"),
        synthetic_id("user", "recruiter-beta"),
        *(synthetic_id("user", f"candidate-{index:03d}") for index in range(1, 37)),
    }
    resume_ids = {
        synthetic_id("resume", "candidate-demo"),
        *(synthetic_id("resume", f"candidate-{index:03d}") for index in range(1, 37)),
    }
    consent_ids = {
        synthetic_id("consent", "candidate-demo-core"),
        *(
            synthetic_id("consent", f"candidate-{index:03d}-core")
            for index in range(1, 37)
        ),
    }
    job_ids = {
        synthetic_id("job", f"job-{index:03d}")
        for index in range(1, len(JOB_TEMPLATES) + 1)
    }
    candidate_ids = [
        synthetic_id("user", f"candidate-{index:03d}") for index in range(1, 37)
    ]
    rng = random.Random(SEED)
    application_ids: set[str] = set()
    for index in range(1, len(JOB_TEMPLATES) + 1):
        job_id = synthetic_id("job", f"job-{index:03d}")
        for candidate_id in rng.sample(candidate_ids, k=min(6, len(candidate_ids))):
            application_ids.add(
                synthetic_id("application", f"{job_id}-{candidate_id}")
            )
            rng.choice(["applied", "reviewing", "interview", "rejected"])
    demo_candidate_id = synthetic_id("user", "candidate-demo")
    for index in range(1, 4):
        job_id = synthetic_id("job", f"job-{index:03d}")
        application_ids.add(
            synthetic_id("application", f"{job_id}-{demo_candidate_id}")
        )
    return {
        "companies": company_ids,
        "users": user_ids,
        "resumes": resume_ids,
        "consents": consent_ids,
        "jobs": job_ids,
        "applications": application_ids,
        "audit": {synthetic_id("audit", "seed-complete")},
    }


def assert_existing_seed_complete(db: Session) -> None:
    expected = required_seed_ids()
    models = {
        "companies": Company,
        "users": User,
        "resumes": Resume,
        "consents": ConsentEvent,
        "jobs": Job,
        "applications": Application,
        "audit": AuditEvent,
    }
    missing_counts: list[str] = []
    for label, identifiers in expected.items():
        model = models[label]
        present = set(
            db.scalars(select(model.id).where(model.id.in_(sorted(identifiers)))).all()
        )
        missing = identifiers - present
        if missing:
            missing_counts.append(f"{label}:{len(missing)}")
    if missing_counts:
        raise RuntimeError(
            "Incomplete deterministic synthetic seed detected; automatic repair is disabled ("
            + ", ".join(missing_counts)
            + ")"
        )


COMPANIES = [
    ("alpha", "아크웨이브", "서울특별시 성동구"),
    ("beta", "모자이크웍스", "경기도 성남시 분당구"),
    ("gamma", "포지데이터", "서울특별시 영등포구"),
]

COMPANY_PROFILES = {
    "alpha": {
        "direction_statement": "신뢰할 수 있는 채용 플랫폼을 안정적으로 운영하고 반복 업무를 자동화합니다.",
        "declared_values": ["신뢰", "안정", "자동화", "협업"],
    },
    "beta": {
        "direction_statement": "검증 가능한 데이터 품질과 책임 있는 실험으로 채용 의사결정을 지원합니다.",
        "declared_values": ["데이터 품질", "책임", "실험", "검증"],
    },
    "gamma": {
        "direction_statement": "복잡한 채용 경험을 누구나 이해할 수 있는 명료하고 포용적인 제품으로 바꿉니다.",
        "declared_values": ["사용자 경험", "명료함", "포용", "문제 해결"],
    },
}

OPENDART_CORP_CODES = {
    "alpha": "90000001",
    "beta": "90000002",
    "gamma": "90000003",
}
OPENDART_FIXTURE_TIME = datetime(2026, 8, 27, 0, 0, tzinfo=timezone.utc)


def synthetic_opendart_snapshot(company_key: str) -> dict[str, object]:
    client = OpenDartClient(mode="fixture", clock=lambda: OPENDART_FIXTURE_TIME)
    return client.refresh_company(OPENDART_CORP_CODES[company_key])


def apply_synthetic_opendart_snapshot(company: Company, company_key: str) -> None:
    snapshot = synthetic_opendart_snapshot(company_key)
    company.opendart_corp_code = OPENDART_CORP_CODES[company_key]
    company.opendart_snapshot = snapshot
    company.opendart_sync_state = "AVAILABLE_SYNTHETIC_FIXTURE"
    company.opendart_snapshot_version = (
        f"opendart-snapshot-{str(snapshot['content_sha256'])[:12]}"
    )
    company.opendart_synced_at = OPENDART_FIXTURE_TIME
    company.opendart_last_attempt_at = OPENDART_FIXTURE_TIME

JOB_TEMPLATES = [
    ("백엔드 플랫폼 엔지니어", "Python과 PostgreSQL로 채용 플랫폼 핵심 API를 개발합니다.", "서울 성동구", ["Python", "FastAPI", "PostgreSQL", "Docker"], 3),
    ("프론트엔드 엔지니어", "React 기반 구직자·채용담당자 경험을 설계하고 구현합니다.", "서울 영등포구", ["React", "TypeScript", "CSS", "Playwright"], 2),
    ("데이터 엔지니어", "신뢰할 수 있는 채용 데이터 파이프라인과 품질 기준을 만듭니다.", "경기 성남시", ["Python", "SQL", "Airflow", "AWS"], 3),
    ("클라우드 플랫폼 엔지니어", "AWS 기반 서비스 운영환경과 배포 흐름을 개선합니다.", "서울 성동구", ["AWS", "Terraform", "Docker", "Linux"], 4),
    ("서비스 기획자", "기업 채용 업무와 구직자 경험을 연결하는 제품을 기획합니다.", "서울 영등포구", ["제품기획", "데이터분석", "Figma", "SQL"], 3),
    ("머신러닝 엔지니어", "결정론적 매처와 설명 생성 경로를 분리해 운영합니다.", "경기 성남시", ["Python", "Machine Learning", "SQL", "Docker"], 3),
    ("정보보호 엔지니어", "클라우드 서비스의 접근·로그·취약점 관리 체계를 운영합니다.", "서울 성동구", ["AWS", "ISMS", "Python", "Linux"], 4),
    ("DevOps 엔지니어", "애플리케이션 배포와 관측성을 자동화합니다.", "서울 영등포구", ["Docker", "Terraform", "GitHub Actions", "AWS"], 3),
    ("B2B 세일즈 매니저", "기업 고객의 채용 운영 문제를 정의하고 해결합니다.", "서울 성동구", ["B2B", "CRM", "데이터분석"], 2),
    ("프로덕트 디자이너", "복잡한 채용 업무를 명료한 화면 흐름으로 바꿉니다.", "경기 성남시", ["Figma", "UX Research", "Design System"], 3),
    ("QA 엔지니어", "API와 사용자 흐름의 회귀 테스트 체계를 구축합니다.", "서울 영등포구", ["Playwright", "API Testing", "Python"], 2),
    ("데이터베이스 엔지니어", "PostgreSQL 성능과 데이터 복구 절차를 운영합니다.", "서울 성동구", ["PostgreSQL", "SQL", "AWS", "Linux"], 4),
]

SKILL_POOLS = [
    ["Python", "FastAPI", "PostgreSQL", "Docker", "AWS"],
    ["React", "TypeScript", "CSS", "Playwright", "Figma"],
    ["Python", "SQL", "Airflow", "AWS", "Linux"],
    ["Terraform", "AWS", "Docker", "Linux", "GitHub Actions"],
    ["제품기획", "데이터분석", "SQL", "Figma", "B2B"],
]


def seed_outcome_snapshot(db: Session) -> dict[str, object]:
    """Populate the isolated synthetic outcome DB from current synthetic fixtures."""

    applications = db.scalars(select(Application).order_by(Application.id)).all()
    resumes = db.scalars(select(Resume).order_by(Resume.user_id)).all()
    jobs = db.scalars(select(Job).order_by(Job.id)).all()
    return seed_synthetic_outcome_dataset(
        db,
        applications,
        {resume.user_id: resume for resume in resumes},
        {job.id: job for job in jobs},
    )


def seed_demo(db: Session) -> None:
    """Create deterministic UI fixtures, explicitly not a FAIR-01 measurement dataset."""

    if os.getenv("DATASET_PROFILE", "demo_not_for_measurement") != "demo_not_for_measurement":
        raise RuntimeError("Only demo_not_for_measurement is available before dataset approval")

    job_count = db.scalar(select(func.count(Job.id))) or 0
    user_count = db.scalar(select(func.count(User.id))) or 0
    if bool(job_count) != bool(user_count):
        raise RuntimeError(
            "Partial synthetic seed detected across member/company databases; "
            "automatic cross-database repair is intentionally disabled"
        )

    if job_count and user_count:
        assert_existing_seed_complete(db)
        for key, name, _ in COMPANIES:
            company = db.scalar(select(Company).where(Company.name == name))
            if company and not company.direction_statement:
                company.direction_statement = COMPANY_PROFILES[key]["direction_statement"]
                company.declared_values = COMPANY_PROFILES[key]["declared_values"]
                company.profile_version = f"company-profile-seed-{SEED}"
            if company and not company.opendart_snapshot:
                apply_synthetic_opendart_snapshot(company, key)
        demo_resume = db.scalar(
            select(Resume).where(Resume.user_id == synthetic_id("user", "candidate-demo"))
        )
        if demo_resume and "신뢰" not in demo_resume.self_intro:
            demo_resume.self_intro = (
                "복잡한 채용 API를 신뢰할 수 있고 안정된 구조로 풀어내며 "
                "협업과 자동화를 중시하는 합성 백엔드 개발자입니다."
            )
        if demo_resume and not demo_resume.projects:
            demo_resume.projects = [
                {
                    "title": "합성 채용 API 안정화 프로젝트",
                    "role": "백엔드 API와 데이터 흐름 설계",
                    "technologies": ["Python", "FastAPI", "PostgreSQL", "Docker"],
                    "summary": "Python과 FastAPI로 채용 API를 구현하고 반복 배포를 자동화했습니다.",
                    "outcome": "합성 부하 시나리오에서 오류 원인을 재현하고 협업 검토 절차를 정리했습니다.",
                }
            ]
        seed_outcome_snapshot(db)
        db.commit()
        return

    rng = random.Random(SEED)
    companies: list[Company] = []
    for key, name, address in COMPANIES:
        company = Company(
            id=synthetic_id("company", key),
            name=name,
            address=address,
            direction_statement=COMPANY_PROFILES[key]["direction_statement"],
            declared_values=COMPANY_PROFILES[key]["declared_values"],
            profile_version=f"company-profile-seed-{SEED}",
        )
        apply_synthetic_opendart_snapshot(company, key)
        db.add(company)
        companies.append(company)

    admin = User(
        id=synthetic_id("user", "admin"),
        email="admin@jcareer.test",
        password_hash=hash_password(DEMO_PASSWORD),
        display_name="운영 관리자",
        role="admin",
    )
    demo_candidate = User(
        id=synthetic_id("user", "candidate-demo"),
        email="candidate@jcareer.test",
        password_hash=hash_password(DEMO_PASSWORD),
        display_name="김제이 (합성)",
        role="candidate",
    )
    recruiter = User(
        id=synthetic_id("user", "recruiter-alpha"),
        email="recruiter@jcareer.test",
        password_hash=hash_password(DEMO_PASSWORD),
        display_name="박채용 (합성)",
        role="recruiter",
        company_id=companies[0].id,
    )
    other_recruiter = User(
        id=synthetic_id("user", "recruiter-beta"),
        email="recruiter-beta@jcareer.test",
        password_hash=hash_password(DEMO_PASSWORD),
        display_name="이담당 (합성)",
        role="recruiter",
        company_id=companies[1].id,
    )
    db.add_all([admin, demo_candidate, recruiter, other_recruiter])
    # Explicit flush keeps FK ordering deterministic across PostgreSQL and SQLite.
    db.flush()

    demo_resume = Resume(
        id=synthetic_id("resume", "candidate-demo"),
        user_id=demo_candidate.id,
        phone="010-0000-0001",
        birth_date=date(1995, 5, 12),
        address_region="서울특별시 마포구",
        education="합성대학교 컴퓨터공학 전공",
        desired_role="백엔드 엔지니어",
        years_experience=4,
        skills=["Python", "FastAPI", "PostgreSQL", "Docker", "AWS"],
        certificates=["합성 자격증 A"],
        projects=[
            {
                "title": "합성 채용 API 안정화 프로젝트",
                "role": "백엔드 API와 데이터 흐름 설계",
                "technologies": ["Python", "FastAPI", "PostgreSQL", "Docker"],
                "summary": "Python과 FastAPI로 채용 API를 구현하고 반복 배포를 자동화했습니다.",
                "outcome": "합성 부하 시나리오에서 오류 원인을 재현하고 협업 검토 절차를 정리했습니다.",
            }
        ],
        self_intro=(
            "복잡한 채용 API를 신뢰할 수 있고 안정된 구조로 풀어내며 "
            "협업과 자동화를 중시하는 합성 백엔드 개발자입니다."
        ),
    )
    db.add(demo_resume)
    db.add(
        ConsentEvent(
            id=synthetic_id("consent", "candidate-demo-core"),
            user_id=demo_candidate.id,
            consent_type="privacy_core",
            action="grant",
            collected_items=[
                "name",
                "email",
                "phone",
                "birth_date",
                "address",
                "education",
                "career",
                "certificates",
                "projects",
            ],
            purposes=["member_management", "job_service", "ai_recommendation"],
        )
    )
    db.flush()

    candidates = [demo_candidate]
    pending_resumes: list[Resume] = []
    pending_consents: list[ConsentEvent] = []
    for index in range(1, 37):
        user = User(
            id=synthetic_id("user", f"candidate-{index:03d}"),
            email=f"candidate{index:03d}@example.invalid",
            password_hash=hash_password(DEMO_PASSWORD),
            display_name=f"합성 지원자 {index:03d}",
            role="candidate",
        )
        skill_pool = SKILL_POOLS[index % len(SKILL_POOLS)]
        selected = skill_pool[: 3 + (index % 3)]
        resume = Resume(
            id=synthetic_id("resume", f"candidate-{index:03d}"),
            user_id=user.id,
            phone=f"010-0000-{index + 1000:04d}",
            birth_date=date(1990 + (index % 10), 1 + (index % 12), 1 + (index % 27)),
            address_region=["서울특별시", "경기도 성남시", "인천광역시"][index % 3],
            education="합성 교육기관 · 전공 정보",
            desired_role=JOB_TEMPLATES[index % len(JOB_TEMPLATES)][0],
            years_experience=1 + (index % 9),
            skills=selected,
            certificates=[] if index % 2 else ["합성 기술 자격"],
            projects=[
                {
                    "title": f"합성 직무 프로젝트 {index:03d}",
                    "role": "구현 및 검토",
                    "technologies": selected[:3],
                    "summary": (
                        f"{selected[0]}와 {selected[1]}를 사용해 합성 채용 업무 흐름을 구현했습니다."
                    ),
                    "outcome": "합성 검증 시나리오와 결과 기록을 남겼습니다.",
                }
            ],
            self_intro=f"합성 시나리오 지원자 {index:03d}의 구조화 이력서입니다.",
        )
        db.add(user)
        pending_resumes.append(resume)
        pending_consents.append(
            ConsentEvent(
                id=synthetic_id("consent", f"candidate-{index:03d}-core"),
                user_id=user.id,
                consent_type="privacy_core",
                action="grant",
                collected_items=[
                    "name",
                    "email",
                    "phone",
                    "birth_date",
                    "address",
                    "education",
                    "career",
                    "certificates",
                    "projects",
                ],
                purposes=["member_management", "job_service", "ai_recommendation"],
            )
        )
        candidates.append(user)

    db.flush()
    db.add_all(pending_resumes)
    db.add_all(pending_consents)

    jobs: list[Job] = []
    for index, (title, summary, location, skills, experience) in enumerate(JOB_TEMPLATES):
        company = companies[index % len(companies)]
        job = Job(
            id=synthetic_id("job", f"job-{index + 1:03d}"),
            company_id=company.id,
            title=title,
            summary=summary,
            location=location,
            required_skills=skills,
            min_experience=experience,
            status="open",
        )
        db.add(job)
        jobs.append(job)

    db.flush()

    application_pairs: set[tuple[str, str]] = set()
    for job in jobs:
        eligible = [candidate for candidate in candidates if candidate.id != demo_candidate.id]
        for candidate in rng.sample(eligible, k=min(6, len(eligible))):
            pair = (job.id, candidate.id)
            if pair in application_pairs:
                continue
            application_pairs.add(pair)
            db.add(
                Application(
                    id=synthetic_id("application", f"{job.id}-{candidate.id}"),
                    job_id=job.id,
                    candidate_id=candidate.id,
                    status=rng.choice(["applied", "reviewing", "interview", "rejected"]),
                )
            )

    for job in jobs[:3]:
        db.add(
            Application(
                id=synthetic_id("application", f"{job.id}-{demo_candidate.id}"),
                job_id=job.id,
                candidate_id=demo_candidate.id,
                status="reviewing" if job is jobs[0] else "applied",
            )
        )

    db.flush()
    seed_outcome_snapshot(db)

    db.add(
        AuditEvent(
            id=synthetic_id("audit", "seed-complete"),
            event_type="runtime_seed",
            actor_role="system",
            target_type="dataset",
            target_ref="demo-not-for-measurement",
            action="seed",
            result="success",
            detail={"seed": SEED, "profile": "demo_not_for_measurement"},
        )
    )
    db.commit()
