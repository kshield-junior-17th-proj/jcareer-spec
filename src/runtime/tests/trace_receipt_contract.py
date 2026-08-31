from __future__ import annotations

import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path


TEMP_ROOT = tempfile.TemporaryDirectory(prefix="jcareer-trace-contract-")
temp_path = Path(TEMP_ROOT.name)
os.environ["MEMBER_DATABASE_URL"] = f"sqlite:///{temp_path / 'member.db'}"
os.environ["COMPANY_DATABASE_URL"] = f"sqlite:///{temp_path / 'company.db'}"
os.environ["OUTCOME_DATABASE_URL"] = f"sqlite:///{temp_path / 'outcome.db'}"
os.environ["DATASET_PROFILE"] = "demo_not_for_measurement"
os.environ["TRACE_SUBJECT_KEY"] = "synthetic-test-subject-key"

API_ROOT = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(API_ROOT))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import trace_receipts as trace  # noqa: E402
from app.database import (  # noqa: E402
    CompanyBase,
    MemberBase,
    OutcomeBase,
    SessionLocal,
    company_engine,
    member_engine,
    outcome_engine,
)
from app.models import Company, Job, User  # noqa: E402
from app.security import issue_token  # noqa: E402


def score_breakdown(total: float = 100.0) -> dict[str, object]:
    role_points = max(0.0, total - 90.0)
    return {
        "schema_version": "score-breakdown-v1",
        "formula_version": "deterministic-70-20-10-v1",
        "policy_source": "platform_default",
        "formula": "skills 70 + experience 20 + role 10",
        "total_points": total,
        "max_points": 100.0,
        "configured_priority_factor_id": "skills",
        "largest_contribution_factor_ids": ["skills"],
        "factors": [
            {
                "factor_id": "skills",
                "label": "skills",
                "raw_points": 70.0,
                "display_points": 70.0,
                "max_points": 70.0,
                "calculation": "redacted by receipt projection",
                "evidence": ["SYNTH-RAW-SKILL-CANARY"],
                "details": {"matched_count": 1},
            },
            {
                "factor_id": "experience",
                "label": "experience",
                "raw_points": 20.0,
                "display_points": 20.0,
                "max_points": 20.0,
                "calculation": "redacted by receipt projection",
                "evidence": [],
                "details": {"candidate_years": 4},
            },
            {
                "factor_id": "role",
                "label": "role",
                "raw_points": role_points,
                "display_points": role_points,
                "max_points": 10.0,
                "calculation": "redacted by receipt projection",
                "evidence": [],
                "details": {"matched": bool(role_points)},
            },
        ],
        "excluded_input_fields": [
            "name",
            "phone",
            "email",
            "birthdate",
            "address",
            "school",
            "certificates",
            "projects",
            "self_intro",
        ],
    }


def recommendation_response(
    *, total: float = 100.0, cache: str = "miss"
) -> dict[str, object]:
    return {
        "recommendation_status": "AVAILABLE",
        "matcher_version": "deterministic-0.2.0",
        "provider_config_fingerprint": "a" * 64,
        "correlation_id": "00000000-0000-0000-0000-abcdeffedcba",
        "cache": cache,
        "items": [
            {
                "job": {
                    "id": "job-1",
                    "company_id": "company-1",
                    "company_name": "SYNTH-RAW-COMPANY-CANARY",
                    "summary": "SYNTH-RAW-JOB-CANARY",
                },
                "score": total,
                "score_breakdown": score_breakdown(total),
                "matched_feature_ids": [
                    "skill.python",
                    "experience.minimum_met",
                    *(["role.title_overlap"] if total > 90 else []),
                ],
                "matched_feature_labels": ["SYNTH-RAW-LABEL-CANARY"],
                "matcher_version": "deterministic-0.2.0",
                "explanation": {
                    "candidate_context": {
                        "email": "raw-candidate@example.invalid",
                        "phone": "010-0000-9999",
                        "self_intro": "SYNTH-RAW-INTRO-CANARY",
                    }
                },
            }
        ],
    }


def candidate_user(user_id: str = "candidate-1") -> User:
    return User(
        id=user_id,
        email=f"{user_id}@example.invalid",
        password_hash="not-used",
        display_name="Synthetic Candidate",
        role="candidate",
    )


def recruiter_user(user_id: str, company_id: str) -> User:
    return User(
        id=user_id,
        email=f"{user_id}@example.invalid",
        password_hash="not-used",
        display_name="Synthetic Recruiter",
        role="recruiter",
        company_id=company_id,
    )


def admin_user() -> User:
    return User(
        id="admin-1",
        email="admin@example.invalid",
        password_hash="not-used",
        display_name="Synthetic Reviewer",
        role="admin",
    )


class TraceReceiptContractTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        member_engine.dispose()
        company_engine.dispose()
        outcome_engine.dispose()
        TEMP_ROOT.cleanup()

    def setUp(self) -> None:
        os.environ["TRACE_MODE"] = "disabled"
        OutcomeBase.metadata.drop_all(bind=outcome_engine)
        CompanyBase.metadata.drop_all(bind=company_engine)
        MemberBase.metadata.drop_all(bind=member_engine)
        OutcomeBase.metadata.create_all(bind=outcome_engine)
        CompanyBase.metadata.create_all(bind=company_engine)
        MemberBase.metadata.create_all(bind=member_engine)
        with SessionLocal() as db:
            db.add(Company(id="company-1", name="Synthetic Company One"))
            db.add(Company(id="company-2", name="Synthetic Company Two"))
            db.flush()
            db.add(
                Job(
                    id="job-1",
                    company_id="company-1",
                    title="Backend Engineer",
                    summary="Synthetic job",
                    location="Synthetic City",
                    required_skills=["Python"],
                    min_experience=3,
                )
            )
            db.add_all(
                [
                    candidate_user(),
                    candidate_user("candidate-2"),
                    recruiter_user("recruiter-1", "company-1"),
                    recruiter_user("recruiter-2", "company-2"),
                    admin_user(),
                ]
            )
            db.commit()

    def draft(
        self, *, key: str = "receipt-key-1", total: float = 100.0, cache: str = "miss"
    ):
        return trace.build_receipt_drafts(
            path="/api/v1/candidates/me/recommendations",
            auth_payload={"sub": "candidate-1", "role": "candidate"},
            response=recommendation_response(total=total, cache=cache),
            idempotency_key=key,
            capture_mode="shadow",
        )[0]

    def stored_receipt(self, *, key: str = "receipt-key-1") -> trace.DecisionReceipt:
        return trace._persist_receipt_drafts(
            [self.draft(key=key)], engine=outcome_engine
        )[0]

    def test_canonical_integrity_idempotency_conflict_and_no_pii(self) -> None:
        self.assertEqual(
            trace.canonical_sha256({"b": 2, "a": 1}),
            trace.canonical_sha256({"a": 1, "b": 2}),
        )
        receipt = self.stored_receipt()
        trace.verify_receipt(receipt)
        retry = trace._persist_receipt_drafts([self.draft()], engine=outcome_engine)[0]
        self.assertEqual(retry.id, receipt.id)
        with self.assertRaises(trace.TraceConflictError):
            trace._persist_receipt_drafts(
                [self.draft(total=90.0)], engine=outcome_engine
            )

        encoded = trace.canonical_json(receipt.payload_json)
        for canary in (
            "SYNTH-RAW-COMPANY-CANARY",
            "SYNTH-RAW-JOB-CANARY",
            "SYNTH-RAW-SKILL-CANARY",
            "SYNTH-RAW-LABEL-CANARY",
            "SYNTH-RAW-INTRO-CANARY",
            "raw-candidate@example.invalid",
            "010-0000-9999",
        ):
            self.assertNotIn(canary, encoded)
        self.assertNotIn("matched_feature_labels", receipt.payload_json)
        self.assertNotIn("calculation", encoded)
        self.assertEqual(receipt.payload_json["automatic_hiring_decision"], False)
        self.assertEqual(receipt.payload_json["automatic_recourse_decision"], False)
        self.assertEqual(trace.DecisionReceipt.__tablename__, "trace_decision_receipts")
        self.assertNotIn("mlops", trace.DecisionReceipt.__tablename__)

        recruiter_response = recommendation_response()
        recruiter_item = recruiter_response["items"][0]
        recruiter_item.pop("job")
        recruiter_item["candidate"] = {
            "user_id": "candidate-1",
            "email": "recruiter-visible@example.invalid",
            "phone": "010-0000-1234",
            "self_intro": "SYNTH-RECRUITER-RAW-CANARY",
        }
        recruiter_response["job"] = {"id": "job-1", "company_id": "company-1"}
        recruiter_draft = trace.build_receipt_drafts(
            path="/api/v1/recruiter/jobs/job-1/recommendations",
            auth_payload={"sub": "recruiter-1", "role": "recruiter"},
            response=recruiter_response,
            idempotency_key="recruiter-receipt-key",
            capture_mode="shadow",
        )[0]
        recruiter_encoded = trace.canonical_json(recruiter_draft.payload_json)
        self.assertEqual(
            recruiter_draft.subject_ref,
            trace.pseudonymous_subject_ref("candidate-1"),
        )
        self.assertNotIn("recruiter-visible@example.invalid", recruiter_encoded)
        self.assertNotIn("010-0000-1234", recruiter_encoded)
        self.assertNotIn("SYNTH-RECRUITER-RAW-CANARY", recruiter_encoded)

    def test_hash_tamper_detection_and_cache_source_boundary(self) -> None:
        receipt = self.stored_receipt()
        with Session(bind=outcome_engine) as db:
            stored = db.get(trace.DecisionReceipt, receipt.id)
            payload = copy.deepcopy(stored.payload_json)
            payload["score_breakdown"]["total_points"] = 1.0
            stored.payload_json = payload
            db.commit()
            with self.assertRaises(trace.ReceiptIntegrityError):
                trace.verify_receipt(stored)

        cache_draft = self.draft(key="cache-hit-key", cache="hit")
        self.assertEqual(cache_draft.source_status, "CACHE_HIT_RESPONSE")
        self.assertEqual(cache_draft.payload_json["cache_state"], "hit")

    def test_candidate_recruiter_admin_scope(self) -> None:
        receipt = self.stored_receipt()
        with SessionLocal() as db:
            trace.authorise_receipt(db, candidate_user(), receipt)
            trace.authorise_receipt(
                db, recruiter_user("recruiter-1", "company-1"), receipt
            )
            trace.authorise_receipt(db, admin_user(), receipt)
            with self.assertRaises(HTTPException) as other_candidate:
                trace.authorise_receipt(db, candidate_user("candidate-2"), receipt)
            self.assertEqual(other_candidate.exception.status_code, 403)
            with self.assertRaises(HTTPException) as other_recruiter:
                trace.authorise_receipt(
                    db, recruiter_user("recruiter-2", "company-2"), receipt
                )
            self.assertEqual(other_recruiter.exception.status_code, 403)

    def test_recourse_twin_review_transitions_retry_and_conflict(self) -> None:
        self.assertEqual(
            trace.DISPOSITION_STATE,
            {
                "UPHOLD": "CLOSED_UPHELD",
                "CHANGE": "CLOSED_CHANGED",
                "REQUEST_INFO": "NEEDS_CANDIDATE_INFO",
                "ESCALATE": "ESCALATED",
            },
        )
        receipt = self.stored_receipt()
        corrected_item = {
            "subject_ref": receipt.subject_ref,
            "score": 90.0,
            "score_breakdown": score_breakdown(90.0),
            "matched_feature_ids": ["skill.python", "experience.minimum_met"],
            "matcher_version": "deterministic-0.2.0",
        }
        replay = trace.build_replay_observation(receipt, corrected_item)
        self.assertEqual(replay["delta_points"], -10.0)
        self.assertEqual(replay["score_or_ranking_effect"], "NONE")
        self.assertTrue(replay["observation_only"])

        with SessionLocal() as db:
            bound = db.get(trace.DecisionReceipt, receipt.id)
            case = trace._create_recourse_case(
                db,
                receipt=bound,
                request_reference=trace.request_ref("recourse-key-1"),
                reason_code="FEATURE_INCORRECT",
                replay=replay,
            )
            retry = trace._create_recourse_case(
                db,
                receipt=bound,
                request_reference=trace.request_ref("recourse-key-1"),
                reason_code="FEATURE_INCORRECT",
                replay=replay,
            )
            self.assertEqual(retry.id, case.id)
            with self.assertRaises(trace.TraceConflictError):
                trace._create_recourse_case(
                    db,
                    receipt=bound,
                    request_reference=trace.request_ref("recourse-key-1"),
                    reason_code="FEATURE_MISSING",
                    replay=replay,
                )

            review_request = trace.ReviewRequest(
                disposition="UPHOLD",
                basis_code="EVIDENCE_CONFIRMED",
                expected_version=1,
            )
            review = trace.record_human_review(
                db,
                case=case,
                reviewer=admin_user(),
                request_reference=trace.request_ref("review-key-1"),
                request=review_request,
            )
            self.assertEqual(review.to_state, "CLOSED_UPHELD")
            self.assertEqual(case.state, "CLOSED_UPHELD")
            self.assertEqual(case.version, 2)
            retry_review = trace.record_human_review(
                db,
                case=case,
                reviewer=admin_user(),
                request_reference=trace.request_ref("review-key-1"),
                request=review_request,
            )
            self.assertEqual(retry_review.id, review.id)
            with self.assertRaises(trace.TraceConflictError):
                trace.record_human_review(
                    db,
                    case=case,
                    reviewer=admin_user(),
                    request_reference=trace.request_ref("review-key-2"),
                    request=trace.ReviewRequest(
                        disposition="CHANGE",
                        basis_code="CORRECTION_SUPPORTED",
                        expected_version=2,
                    ),
                )
            with self.assertRaises(HTTPException) as non_admin:
                trace.record_human_review(
                    db,
                    case=case,
                    reviewer=recruiter_user("recruiter-1", "company-1"),
                    request_reference=trace.request_ref("review-key-3"),
                    request=review_request,
                )
            self.assertEqual(non_admin.exception.status_code, 403)
            case.state = "ESCALATED"
            db.commit()
            with self.assertRaises(trace.ReceiptIntegrityError):
                trace.case_payload(db, case)

    def test_role_scoped_http_receipt_case_and_review_apis(self) -> None:
        receipt = self.stored_receipt(key="http-receipt-key")
        mini = FastAPI()

        async def replay_matcher(_path: str, payload: dict[str, object]):
            subject = payload["candidates"][0]["id"]
            return {
                "status": "AVAILABLE",
                "matcher_version": "deterministic-0.2.0",
                "items": [
                    {
                        "subject_ref": subject,
                        "score": 90.0,
                        "score_breakdown": score_breakdown(90.0),
                        "matched_feature_ids": [
                            "skill.python",
                            "experience.minimum_met",
                        ],
                        "matcher_version": "deterministic-0.2.0",
                    }
                ],
            }

        trace.install_trace(mini, matcher_runner=replay_matcher)
        client = TestClient(mini)

        def auth(user: User) -> dict[str, str]:
            return {"Authorization": f"Bearer {issue_token(user)}"}

        owner_headers = auth(candidate_user())
        self.assertEqual(
            client.get(
                f"/api/v1/trace/receipts/{receipt.id}", headers=owner_headers
            ).status_code,
            200,
        )
        self.assertEqual(
            client.get(
                f"/api/v1/trace/receipts/{receipt.id}",
                headers=auth(candidate_user("candidate-2")),
            ).status_code,
            403,
        )
        self.assertEqual(
            client.get(
                f"/api/v1/trace/receipts/{receipt.id}",
                headers=auth(recruiter_user("recruiter-1", "company-1")),
            ).status_code,
            200,
        )
        self.assertEqual(
            client.get(
                f"/api/v1/trace/receipts/{receipt.id}",
                headers=auth(recruiter_user("recruiter-2", "company-2")),
            ).status_code,
            403,
        )

        request_body = {
            "base_integrity_sha256": receipt.integrity_sha256,
            "reason_code": "FEATURE_INCORRECT",
            "corrected_features": {
                "desired_role": "Backend Engineer",
                "skills": ["Python"],
                "years_experience": 3,
            },
        }
        created = client.post(
            f"/api/v1/trace/receipts/{receipt.id}/recourse",
            headers={**owner_headers, "Idempotency-Key": "http-recourse-key"},
            json=request_body,
        )
        self.assertEqual(created.status_code, 201, created.text)
        case_id = created.json()["case_id"]
        self.assertEqual(created.json()["state"], "PENDING_REVIEW")
        retried = client.post(
            f"/api/v1/trace/receipts/{receipt.id}/recourse",
            headers={**owner_headers, "Idempotency-Key": "http-recourse-key"},
            json=request_body,
        )
        self.assertEqual(retried.status_code, 201, retried.text)
        self.assertEqual(retried.json()["case_id"], case_id)
        recruiter_recourse = client.post(
            f"/api/v1/trace/receipts/{receipt.id}/recourse",
            headers={
                **auth(recruiter_user("recruiter-1", "company-1")),
                "Idempotency-Key": "http-recruiter-recourse-key",
            },
            json=request_body,
        )
        self.assertEqual(recruiter_recourse.status_code, 403)

        review_body = {
            "disposition": "CHANGE",
            "basis_code": "CORRECTION_SUPPORTED",
            "expected_version": 1,
        }
        candidate_review = client.post(
            f"/api/v1/trace/cases/{case_id}/reviews",
            headers={**owner_headers, "Idempotency-Key": "http-candidate-review-key"},
            json=review_body,
        )
        self.assertEqual(candidate_review.status_code, 403)
        admin_review = client.post(
            f"/api/v1/trace/cases/{case_id}/reviews",
            headers={**auth(admin_user()), "Idempotency-Key": "http-admin-review-key"},
            json=review_body,
        )
        self.assertEqual(admin_review.status_code, 201, admin_review.text)
        self.assertEqual(admin_review.json()["case"]["state"], "CLOSED_CHANGED")
        candidate_case = client.get(
            f"/api/v1/trace/cases/{case_id}", headers=owner_headers
        )
        self.assertEqual(candidate_case.status_code, 200)
        self.assertEqual(
            candidate_case.json()["human_reviews"][-1]["disposition"], "CHANGE"
        )

    def test_trace_modes_shadow_and_enforced_fail_closed(self) -> None:
        mini = FastAPI()

        async def unused_matcher(_path: str, _payload: dict[str, object]):
            raise AssertionError("replay matcher is not called during receipt capture")

        @mini.get("/api/v1/candidates/me/recommendations")
        def recommendations(cache: str = "miss"):
            return recommendation_response(cache=cache)

        trace.install_trace(mini, matcher_runner=unused_matcher)
        token = issue_token(candidate_user())
        headers = {"Authorization": f"Bearer {token}"}
        client = TestClient(mini)

        disabled = client.get("/api/v1/candidates/me/recommendations", headers=headers)
        self.assertEqual(disabled.status_code, 200)
        self.assertNotIn("trace_receipt", disabled.json())
        with Session(bind=outcome_engine) as db:
            self.assertEqual(db.scalar(select(func.count(trace.DecisionReceipt.id))), 0)

        original_persist = trace._persist_receipt_drafts

        def fail_write(*_args, **_kwargs):
            raise SQLAlchemyError("synthetic receipt write failure")

        try:
            trace._persist_receipt_drafts = fail_write
            os.environ["TRACE_MODE"] = "shadow"
            shadow = client.get(
                "/api/v1/candidates/me/recommendations", headers=headers
            )
            self.assertEqual(shadow.status_code, 200)
            self.assertEqual(
                shadow.json()["trace_receipt"]["source_status"],
                "STORE_UNAVAILABLE_SHADOW",
            )
            self.assertEqual(shadow.json()["recommendation_status"], "AVAILABLE")

            os.environ["TRACE_MODE"] = "enforced"
            enforced = client.get(
                "/api/v1/candidates/me/recommendations", headers=headers
            )
            self.assertEqual(enforced.status_code, 503)
            self.assertEqual(enforced.json()["error_code"], "TRACE_RECEIPT_UNAVAILABLE")
        finally:
            trace._persist_receipt_drafts = original_persist

        os.environ["TRACE_MODE"] = "shadow"
        current_headers = {**headers, "Idempotency-Key": "middleware-current-key"}
        first = client.get(
            "/api/v1/candidates/me/recommendations?cache=miss",
            headers=current_headers,
        )
        second = client.get(
            "/api/v1/candidates/me/recommendations?cache=miss",
            headers=current_headers,
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(
            first.json()["trace_receipt"]["receipt_refs"][0]["receipt_id"],
            second.json()["trace_receipt"]["receipt_refs"][0]["receipt_id"],
        )
        cache_hit = client.get(
            "/api/v1/candidates/me/recommendations?cache=hit",
            headers={**headers, "Idempotency-Key": "middleware-cache-hit-key"},
        )
        self.assertEqual(cache_hit.status_code, 200)
        self.assertEqual(
            cache_hit.json()["trace_receipt"]["source_status"], "RECORDED_CACHE_HIT"
        )
        with Session(bind=outcome_engine) as db:
            self.assertEqual(db.scalar(select(func.count(trace.DecisionReceipt.id))), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
