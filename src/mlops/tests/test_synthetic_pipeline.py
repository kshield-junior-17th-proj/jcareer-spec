from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


MLOPS_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = MLOPS_ROOT / "generate_synthetic_training.py"
TRAINER = MLOPS_ROOT / "train_challenger.py"
sys.path.insert(0, str(MLOPS_ROOT))

from export_runtime_training import (  # noqa: E402
    SYNTHETIC_ATTESTATION,
    TRAINING_FEATURES as RUNTIME_TRAINING_FEATURES,
    export_runtime_dataset,
)
from lambda_handler import (  # noqa: E402
    SERVERLESS_ENABLE_VALUE,
    run_serverless_pipeline,
)
from train_challenger import train_from_manifest  # noqa: E402


class SyntheticMLOpsPipelineTests(unittest.TestCase):
    def run_command(self, *arguments: object, expect_success: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, *(str(argument) for argument in arguments)],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if expect_success and result.returncode != 0:
            self.fail(f"command failed: {result.stderr}")
        if not expect_success and result.returncode == 0:
            self.fail("command unexpectedly succeeded")
        return result

    def generate_and_train(self, root: Path) -> tuple[Path, Path]:
        dataset_dir = root / "dataset"
        model_dir = root / "model"
        self.run_command(
            GENERATOR,
            "--out-dir",
            dataset_dir,
            "--seed",
            42001,
            "--candidates",
            80,
            "--jobs",
            15,
            "--pairs-per-candidate",
            7,
        )
        self.run_command(
            TRAINER,
            "--manifest",
            dataset_dir / "dataset_manifest.json",
            "--out-dir",
            model_dir,
            "--epochs",
            240,
        )
        return dataset_dir, model_dir

    def test_pipeline_is_deterministic_and_not_runtime_approved(self) -> None:
        with tempfile.TemporaryDirectory() as first_raw, tempfile.TemporaryDirectory() as second_raw:
            first_dataset, first_model = self.generate_and_train(Path(first_raw))
            second_dataset, second_model = self.generate_and_train(Path(second_raw))

            first_manifest = json.loads((first_dataset / "dataset_manifest.json").read_text(encoding="utf-8"))
            model = json.loads((first_model / "challenger_model.json").read_text(encoding="utf-8"))
            evaluation = json.loads((first_model / "evaluation_observations.json").read_text(encoding="utf-8"))

            self.assertTrue(first_manifest["synthetic_only"])
            self.assertFalse(first_manifest["member_data_used"])
            self.assertFalse(first_manifest["company_customer_data_used"])
            self.assertEqual(
                first_manifest["field_roles"]["training_features"],
                ["skill_overlap", "experience_fit", "role_overlap"],
            )
            self.assertEqual(model["model_state"], "TRAINED_SYNTHETIC_NOT_APPROVED")
            self.assertEqual(model["approval_state"], "HUMAN_DECISION_NOT_RECORDED")
            self.assertFalse(model["runtime_wired"])
            self.assertFalse(model["can_change_runtime_ranking"])
            self.assertEqual(evaluation["observation_state"], "MEASURED_SYNTHETIC_NOT_ASSESSED")
            self.assertFalse(evaluation["automatic_pass_fail_gate"])
            self.assertIsNone(evaluation["compliance_conclusion"])
            self.assertIsNone(evaluation["fairness_conclusion"])
            self.assertIsNone(evaluation["runtime_release_decision"])
            self.assertGreater(evaluation["metrics"]["challenger"]["row_count"], 0)

            for relative in [
                "dataset/ranking_dataset.csv",
                "dataset/dataset_manifest.json",
                "model/challenger_model.json",
                "model/evaluation_observations.json",
            ]:
                first_bytes = (Path(first_raw) / relative).read_bytes()
                second_bytes = (Path(second_raw) / relative).read_bytes()
                self.assertEqual(hashlib.sha256(first_bytes).digest(), hashlib.sha256(second_bytes).digest())

    def test_dataset_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            dataset_dir = Path(raw) / "dataset"
            self.run_command(GENERATOR, "--out-dir", dataset_dir, "--candidates", 30, "--jobs", 8, "--pairs-per-candidate", 4)
            dataset_path = dataset_dir / "ranking_dataset.csv"
            dataset_path.write_bytes(dataset_path.read_bytes() + b"\n")
            result = self.run_command(
                TRAINER,
                "--manifest",
                dataset_dir / "dataset_manifest.json",
                "--out-dir",
                Path(raw) / "model",
                expect_success=False,
            )
            self.assertIn("dataset SHA-256 does not match manifest", result.stderr)

    def test_manifest_claiming_member_data_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            dataset_dir = Path(raw) / "dataset"
            self.run_command(GENERATOR, "--out-dir", dataset_dir, "--candidates", 30, "--jobs", 8, "--pairs-per-candidate", 4)
            manifest_path = dataset_dir / "dataset_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["member_data_used"] = True
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = self.run_command(
                TRAINER,
                "--manifest",
                manifest_path,
                "--out-dir",
                Path(raw) / "model",
                expect_success=False,
            )
            self.assertIn("dataset manifest rejects member_data_used", result.stderr)

    def test_existing_artifacts_are_not_overwritten_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            dataset_dir = Path(raw) / "dataset"
            self.run_command(GENERATOR, "--out-dir", dataset_dir, "--candidates", 30, "--jobs", 8, "--pairs-per-candidate", 4)
            result = self.run_command(
                GENERATOR,
                "--out-dir",
                dataset_dir,
                "--candidates",
                30,
                "--jobs",
                8,
                "--pairs-per-candidate",
                4,
                expect_success=False,
            )
            self.assertIn("refusing to overwrite existing artifact", result.stderr)


def create_runtime_databases(root: Path) -> tuple[str, str, set[str]]:
    member_path = root / "member.db"
    company_path = root / "company.db"
    raw_canaries: set[str] = set()
    member = sqlite3.connect(member_path)
    company = sqlite3.connect(company_path)
    try:
        member.executescript(
            """
            CREATE TABLE users (
              id TEXT PRIMARY KEY, email TEXT, display_name TEXT, role TEXT,
              active INTEGER, withdrawn_at TEXT
            );
            CREATE TABLE resumes (
              id TEXT PRIMARY KEY, user_id TEXT, phone TEXT, birth_date TEXT,
              address_region TEXT, education TEXT, desired_role TEXT,
              years_experience INTEGER, skills TEXT, certificates TEXT,
              self_intro TEXT
            );
            CREATE TABLE applications (
              id TEXT PRIMARY KEY, job_id TEXT, candidate_id TEXT, status TEXT,
              applied_at TEXT, updated_at TEXT
            );
            CREATE TABLE consent_events (
              id TEXT PRIMARY KEY, user_id TEXT, consent_type TEXT, action TEXT,
              policy_version TEXT, collected_items TEXT, purposes TEXT,
              legal_basis TEXT, occurred_at TEXT
            );
            """
        )
        company.executescript(
            """
            CREATE TABLE companies (
              id TEXT PRIMARY KEY, name TEXT, direction_statement TEXT,
              declared_values TEXT, profile_version TEXT, status TEXT
            );
            CREATE TABLE jobs (
              id TEXT PRIMARY KEY, company_id TEXT, title TEXT, summary TEXT,
              required_skills TEXT, min_experience INTEGER, status TEXT
            );
            """
        )
        company.execute(
            "INSERT INTO companies VALUES (?, ?, ?, ?, ?, ?)",
            (
                "company-1",
                "합성 기업 원문 CANARY-COMPANY",
                "신뢰할 수 있는 자동화와 협업",
                json.dumps(["신뢰", "자동화", "협업"], ensure_ascii=False),
                "fixture-v1",
                "approved",
            ),
        )
        jobs = [
            (
                "job-1",
                "company-1",
                "백엔드 Python 엔지니어",
                "Python FastAPI 채용 플랫폼 API 개발",
                json.dumps(["Python", "FastAPI"], ensure_ascii=False),
                2,
                "open",
            ),
            (
                "job-2",
                "company-1",
                "데이터 SQL 엔지니어",
                "SQL 데이터 파이프라인 운영",
                json.dumps(["SQL", "Python"], ensure_ascii=False),
                3,
                "open",
            ),
        ]
        company.executemany("INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?)", jobs)

        for index in range(1, 41):
            candidate_id = f"candidate-{index:03d}"
            email = f"runtime-canary-{index:03d}@example.invalid"
            display_name = f"합성 원문 이름 CANARY-NAME-{index:03d}"
            phone = f"010-0000-{index:04d}"
            self_intro = (
                f"CANARY-INTRO-{index:03d} Python API 자동화 협업 경험으로 "
                "신뢰할 수 있는 서비스를 만들었습니다."
            )
            raw_canaries.update({email, display_name, phone, f"CANARY-INTRO-{index:03d}"})
            member.execute(
                "INSERT INTO users VALUES (?, ?, ?, 'candidate', 1, NULL)",
                (candidate_id, email, display_name),
            )
            member.execute(
                "INSERT INTO resumes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"resume-{index:03d}",
                    candidate_id,
                    phone,
                    "1995-01-01",
                    "합성시 합성구",
                    "합성대학교",
                    "백엔드 엔지니어",
                    1 + index % 7,
                    json.dumps(["Python", "FastAPI", "SQL"], ensure_ascii=False),
                    json.dumps(["합성 자격"], ensure_ascii=False),
                    self_intro,
                ),
            )
            member.execute(
                "INSERT INTO consent_events VALUES (?, ?, 'privacy_core', 'grant', ?, ?, ?, 'consent', ?)",
                (
                    f"consent-{index:03d}",
                    candidate_id,
                    "fixture-v1",
                    json.dumps(["resume"]),
                    json.dumps(["ai_recommendation"]),
                    "2026-08-28T00:00:00+00:00",
                ),
            )
            member.execute(
                "INSERT INTO applications VALUES (?, 'job-1', ?, 'reviewing', ?, ?)",
                (
                    f"application-{index:03d}-positive",
                    candidate_id,
                    "2026-08-28T00:00:00+00:00",
                    "2026-08-28T00:00:00+00:00",
                ),
            )
            member.execute(
                "INSERT INTO applications VALUES (?, 'job-2', ?, 'rejected', ?, ?)",
                (
                    f"application-{index:03d}-negative",
                    candidate_id,
                    "2026-08-28T00:00:00+00:00",
                    "2026-08-28T00:00:00+00:00",
                ),
            )
            member.execute(
                "INSERT INTO applications VALUES (?, 'job-2', ?, 'applied', ?, ?)",
                (
                    f"application-{index:03d}-unresolved",
                    candidate_id,
                    "2026-08-28T00:00:00+00:00",
                    "2026-08-28T00:00:00+00:00",
                ),
            )
        member.commit()
        company.commit()
    finally:
        member.close()
        company.close()
    return f"sqlite:///{member_path.as_posix()}", f"sqlite:///{company_path.as_posix()}", raw_canaries


class FakeS3:
    def __init__(self, source_objects: dict[tuple[str, str], bytes] | None = None) -> None:
        self.objects: list[dict[str, object]] = []
        self.source_objects = source_objects or {}
        self.get_requests: list[dict[str, str]] = []

    def put_object(self, **arguments: object) -> dict[str, object]:
        self.objects.append(arguments)
        return {"ETag": "synthetic-etag"}

    def get_object(self, **arguments: str) -> dict[str, object]:
        request = {"Bucket": arguments["Bucket"], "Key": arguments["Key"]}
        self.get_requests.append(request)
        body = self.source_objects[(request["Bucket"], request["Key"])]
        return {"Body": io.BytesIO(body), "ContentLength": len(body)}


class FakeDynamoDB:
    def __init__(self) -> None:
        self.items: list[dict[str, object]] = []
        self.claimed_run_ids: set[str] = set()

    def put_item(self, **arguments: object) -> dict[str, object]:
        item = arguments["Item"]
        run_id = item["run_id"]["S"]
        if arguments.get("ConditionExpression") == "attribute_not_exists(run_id)":
            if run_id in self.claimed_run_ids:
                raise RuntimeError("ConditionalCheckFailedException")
            self.claimed_run_ids.add(run_id)
        self.items.append(arguments)
        return {}


def snapshot_objects(
    *,
    exported: dict[str, Path],
    bucket: str,
    run_id: str,
) -> dict[tuple[str, str], bytes]:
    names = {
        "dataset": "ranking_dataset.csv",
        "manifest": "dataset_manifest.json",
        "receipt": "source_read_receipt.json",
    }
    return {
        (bucket, f"mlops/sources/{run_id}/{filename}"): exported[key].read_bytes()
        for key, filename in names.items()
    }


class RuntimeDatabaseMLOpsPipelineTests(unittest.TestCase):
    def test_identifier_changes_affect_lineage_but_not_training_rows(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            member_url, company_url, _ = create_runtime_databases(root)
            first = export_runtime_dataset(
                member_database_url=member_url,
                company_database_url=company_url,
                output_directory=root / "first",
                synthetic_attestation=SYNTHETIC_ATTESTATION,
            )
            member_path = root / "member.db"
            connection = sqlite3.connect(member_path)
            try:
                connection.execute(
                    "UPDATE users SET email=?, display_name=? WHERE id='candidate-001'",
                    ("changed-lineage@example.invalid", "변경된 합성 이름"),
                )
                connection.commit()
            finally:
                connection.close()
            second = export_runtime_dataset(
                member_database_url=member_url,
                company_database_url=company_url,
                output_directory=root / "second",
                synthetic_attestation=SYNTHETIC_ATTESTATION,
            )
            first_manifest = json.loads(first["manifest"].read_text(encoding="utf-8"))
            second_manifest = json.loads(second["manifest"].read_text(encoding="utf-8"))
            self.assertEqual(first["dataset"].read_bytes(), second["dataset"].read_bytes())
            self.assertNotEqual(first_manifest["source_digest"], second_manifest["source_digest"])

    def test_runtime_export_trains_without_persisting_raw_member_text(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            member_url, company_url, canaries = create_runtime_databases(root)
            exported = export_runtime_dataset(
                member_database_url=member_url,
                company_database_url=company_url,
                output_directory=root / "dataset",
                synthetic_attestation=SYNTHETIC_ATTESTATION,
            )
            manifest = json.loads(exported["manifest"].read_text(encoding="utf-8"))
            receipt = json.loads(exported["receipt"].read_text(encoding="utf-8"))
            dataset = exported["dataset"].read_text(encoding="utf-8")
            self.assertTrue(manifest["member_data_used"])
            self.assertTrue(manifest["company_customer_data_used"])
            self.assertTrue(manifest["source_runtime_db_wired"])
            self.assertFalse(manifest["ranking_runtime_wired"])
            self.assertEqual(
                manifest["field_roles"]["training_features"],
                RUNTIME_TRAINING_FEATURES,
            )
            self.assertEqual(
                manifest["label_semantics"],
                "historical_pipeline_progression_proxy_not_candidate_quality_or_hiring_probability",
            )
            self.assertEqual(receipt["name_and_email_role"], "lineage_digest_input_only_not_model_features")
            self.assertEqual(receipt["self_intro_role"], "read_then_derived_to_overlap_features_raw_text_not_persisted")
            self.assertFalse(receipt["raw_source_values_persisted"])
            self.assertEqual(manifest["excluded_unresolved_status_counts"], {"applied": 40})
            self.assertTrue(all(canary not in dataset for canary in canaries))

            trained = train_from_manifest(
                manifest_path=exported["manifest"],
                output_directory=root / "model",
                epochs=120,
            )
            model = json.loads(trained["model"].read_text(encoding="utf-8"))
            evaluation = json.loads(trained["evaluation"].read_text(encoding="utf-8"))
            self.assertEqual(model["model_state"], "TRAINED_SYNTHETIC_RUNTIME_DATA_NOT_APPROVED")
            self.assertEqual(model["training_features"], RUNTIME_TRAINING_FEATURES)
            self.assertFalse(model["runtime_wired"])
            self.assertFalse(model["can_change_runtime_ranking"])
            self.assertEqual(evaluation["observation_state"], "MEASURED_SYNTHETIC_RUNTIME_NOT_ASSESSED")
            combined = b"".join(path.read_bytes() for path in [*exported.values(), *trained.values()])
            self.assertTrue(all(canary.encode("utf-8") not in combined for canary in canaries))

    def test_runtime_export_requires_attestation_and_distinct_databases(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            member_url, company_url, _ = create_runtime_databases(root)
            with self.assertRaisesRegex(ValueError, "attestation"):
                export_runtime_dataset(
                    member_database_url=member_url,
                    company_database_url=company_url,
                    output_directory=root / "missing-attestation",
                    synthetic_attestation="",
                )
            with self.assertRaisesRegex(ValueError, "must be different"):
                export_runtime_dataset(
                    member_database_url=member_url,
                    company_database_url=member_url,
                    output_directory=root / "same-database",
                    synthetic_attestation=SYNTHETIC_ATTESTATION,
                )

    def test_lambda_adapter_records_pending_review_without_model_activation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            member_url, company_url, canaries = create_runtime_databases(root)
            s3 = FakeS3()
            dynamodb = FakeDynamoDB()
            result = run_serverless_pipeline(
                {"detail": {"action": "train_challenger", "run_id": "fixture-run-001"}},
                environment={
                    "ALLOW_SYNTHETIC_MLOPS_RUN": SERVERLESS_ENABLE_VALUE,
                    "MLOPS_SYNTHETIC_ATTESTATION": SYNTHETIC_ATTESTATION,
                    "MEMBER_DATABASE_URL": member_url,
                    "COMPANY_DATABASE_URL": company_url,
                    "MLOPS_ARTIFACT_BUCKET": "synthetic-artifact-bucket",
                    "MLOPS_RUN_TABLE": "synthetic-run-table",
                    "MLOPS_EPOCHS": "100",
                },
                s3_client=s3,
                dynamodb_client=dynamodb,
                work_root=root / "lambda-work",
            )
            states = [
                item["Item"]["state"]["S"]
                for item in dynamodb.items
            ]
            self.assertEqual(states, ["RUNNING", "TRAINED_PENDING_HUMAN_REVIEW"])
            self.assertEqual(result["state"], "TRAINED_PENDING_HUMAN_REVIEW")
            self.assertFalse(result["runtime_ranking_wired"])
            self.assertFalse(result["automatic_model_activation"])
            self.assertEqual(result["artifact_count"], 6)
            self.assertEqual(len(s3.objects), 6)
            uploaded = b"".join(bytes(item["Body"]) for item in s3.objects)
            self.assertTrue(all(canary.encode("utf-8") not in uploaded for canary in canaries))
            self.assertTrue(
                all(item["ServerSideEncryption"] == "AES256" for item in s3.objects)
            )

    def test_lambda_failure_is_recorded_fail_safe(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _, company_url, _ = create_runtime_databases(root)
            s3 = FakeS3()
            dynamodb = FakeDynamoDB()
            with self.assertRaises(Exception):
                run_serverless_pipeline(
                    {"action": "train_challenger", "run_id": "fixture-failure-001"},
                    environment={
                        "ALLOW_SYNTHETIC_MLOPS_RUN": SERVERLESS_ENABLE_VALUE,
                        "MLOPS_SYNTHETIC_ATTESTATION": SYNTHETIC_ATTESTATION,
                        "MEMBER_DATABASE_URL": f"sqlite:///{(root / 'empty-member.db').as_posix()}",
                        "COMPANY_DATABASE_URL": company_url,
                        "MLOPS_ARTIFACT_BUCKET": "synthetic-artifact-bucket",
                        "MLOPS_RUN_TABLE": "synthetic-run-table",
                    },
                    s3_client=s3,
                    dynamodb_client=dynamodb,
                    work_root=root / "lambda-failure-work",
                )
            states = [item["Item"]["state"]["S"] for item in dynamodb.items]
            self.assertEqual(states, ["RUNNING", "FAILED_SAFE"])
            self.assertEqual(s3.objects, [])

    def test_lambda_trains_from_exact_bounded_feature_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            member_url, company_url, canaries = create_runtime_databases(root)
            exported = export_runtime_dataset(
                member_database_url=member_url,
                company_database_url=company_url,
                output_directory=root / "snapshot-source",
                synthetic_attestation=SYNTHETIC_ATTESTATION,
            )
            run_id = "snapshot-run-001"
            bucket = "synthetic-snapshot-bucket"
            s3 = FakeS3(source_objects=snapshot_objects(
                exported=exported,
                bucket=bucket,
                run_id=run_id,
            ))
            dynamodb = FakeDynamoDB()
            result = run_serverless_pipeline(
                {
                    "detail": {
                        "action": "train_challenger",
                        "run_id": run_id,
                        "source_prefix": f"mlops/sources/{run_id}/",
                    }
                },
                environment={
                    "ALLOW_SYNTHETIC_MLOPS_RUN": SERVERLESS_ENABLE_VALUE,
                    "MLOPS_SYNTHETIC_ATTESTATION": SYNTHETIC_ATTESTATION,
                    "MLOPS_SOURCE_MODE": "feature_snapshot",
                    "MLOPS_ARTIFACT_BUCKET": "synthetic-artifact-bucket",
                    "MLOPS_FEATURE_SNAPSHOT_BUCKET": bucket,
                    "MLOPS_RUN_TABLE": "synthetic-run-table",
                    "MLOPS_EPOCHS": "100",
                },
                s3_client=s3,
                dynamodb_client=dynamodb,
                work_root=root / "lambda-snapshot-work",
            )
            self.assertEqual(result["source_mode"], "feature_snapshot")
            self.assertEqual(result["artifact_count"], 6)
            self.assertFalse(result["runtime_ranking_wired"])
            self.assertFalse(result["automatic_model_activation"])
            self.assertEqual(
                [request["Key"].rsplit("/", 1)[-1] for request in s3.get_requests],
                [
                    "ranking_dataset.csv",
                    "dataset_manifest.json",
                    "source_read_receipt.json",
                ],
            )
            self.assertEqual(len(s3.objects), 6)
            self.assertTrue(
                all(item["Key"].startswith(f"mlops/runs/{run_id}/") for item in s3.objects)
            )
            uploaded = b"".join(bytes(item["Body"]) for item in s3.objects)
            self.assertTrue(all(canary.encode("utf-8") not in uploaded for canary in canaries))
            run_receipt = json.loads(
                next(
                    bytes(item["Body"])
                    for item in s3.objects
                    if item["Key"].endswith("pipeline_run_receipt.json")
                )
            )
            self.assertEqual(run_receipt["source_mode"], "feature_snapshot")
            self.assertFalse(run_receipt["source_runtime_db_read_in_this_execution"])
            self.assertTrue(run_receipt["source_snapshot_validated"])

    def test_feature_snapshot_rejects_prefix_and_digest_tampering_fail_safe(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            member_url, company_url, _ = create_runtime_databases(root)
            exported = export_runtime_dataset(
                member_database_url=member_url,
                company_database_url=company_url,
                output_directory=root / "snapshot-source",
                synthetic_attestation=SYNTHETIC_ATTESTATION,
            )
            run_id = "snapshot-tamper-001"
            bucket = "synthetic-snapshot-bucket"
            source = snapshot_objects(exported=exported, bucket=bucket, run_id=run_id)
            dataset_key = (bucket, f"mlops/sources/{run_id}/ranking_dataset.csv")
            source[dataset_key] += b"\n"
            s3 = FakeS3(source)
            dynamodb = FakeDynamoDB()
            environment = {
                "ALLOW_SYNTHETIC_MLOPS_RUN": SERVERLESS_ENABLE_VALUE,
                "MLOPS_SYNTHETIC_ATTESTATION": SYNTHETIC_ATTESTATION,
                "MLOPS_ARTIFACT_BUCKET": "synthetic-artifact-bucket",
                "MLOPS_FEATURE_SNAPSHOT_BUCKET": bucket,
                "MLOPS_RUN_TABLE": "synthetic-run-table",
            }
            with self.assertRaisesRegex(ValueError, "dataset SHA-256"):
                run_serverless_pipeline(
                    {
                        "source_mode": "feature_snapshot",
                        "run_id": run_id,
                        "source_prefix": f"mlops/sources/{run_id}/",
                    },
                    environment=environment,
                    s3_client=s3,
                    dynamodb_client=dynamodb,
                    work_root=root / "lambda-tamper-work",
                )
            self.assertEqual(
                [item["Item"]["state"]["S"] for item in dynamodb.items],
                ["RUNNING", "FAILED_SAFE"],
            )
            self.assertEqual(s3.objects, [])

            mismatch_dynamodb = FakeDynamoDB()
            with self.assertRaisesRegex(ValueError, "bounded run prefix"):
                run_serverless_pipeline(
                    {
                        "source_mode": "feature_snapshot",
                        "run_id": "snapshot-prefix-001",
                        "source_prefix": "mlops/sources/another-run/",
                    },
                    environment=environment,
                    s3_client=FakeS3(),
                    dynamodb_client=mismatch_dynamodb,
                    work_root=root / "lambda-prefix-work",
                )
            self.assertEqual(
                [item["Item"]["state"]["S"] for item in mismatch_dynamodb.items],
                ["RUNNING", "FAILED_SAFE"],
            )

    def test_duplicate_lambda_run_id_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            member_url, company_url, _ = create_runtime_databases(root)
            environment = {
                "ALLOW_SYNTHETIC_MLOPS_RUN": SERVERLESS_ENABLE_VALUE,
                "MLOPS_SYNTHETIC_ATTESTATION": SYNTHETIC_ATTESTATION,
                "MEMBER_DATABASE_URL": member_url,
                "COMPANY_DATABASE_URL": company_url,
                "MLOPS_ARTIFACT_BUCKET": "synthetic-artifact-bucket",
                "MLOPS_RUN_TABLE": "synthetic-run-table",
                "MLOPS_EPOCHS": "100",
            }
            event = {"run_id": "duplicate-run-001"}
            s3 = FakeS3()
            dynamodb = FakeDynamoDB()
            run_serverless_pipeline(
                event,
                environment=environment,
                s3_client=s3,
                dynamodb_client=dynamodb,
                work_root=root / "lambda-work",
            )
            with self.assertRaisesRegex(RuntimeError, "ConditionalCheckFailed"):
                run_serverless_pipeline(
                    event,
                    environment=environment,
                    s3_client=s3,
                    dynamodb_client=dynamodb,
                    work_root=root / "lambda-work",
                )
            self.assertEqual(
                [item["Item"]["state"]["S"] for item in dynamodb.items],
                ["RUNNING", "TRAINED_PENDING_HUMAN_REVIEW"],
            )

    def test_feature_snapshot_rejects_hidden_extra_csv_values(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            member_url, company_url, _ = create_runtime_databases(root)
            exported = export_runtime_dataset(
                member_database_url=member_url,
                company_database_url=company_url,
                output_directory=root / "snapshot-source",
                synthetic_attestation=SYNTHETIC_ATTESTATION,
            )
            run_id = "snapshot-extra-field-001"
            bucket = "synthetic-snapshot-bucket"
            source = snapshot_objects(exported=exported, bucket=bucket, run_id=run_id)
            dataset_key = (bucket, f"mlops/sources/{run_id}/ranking_dataset.csv")
            dataset_lines = source[dataset_key].decode("utf-8").splitlines()
            dataset_lines[1] += ",RAW-IDENTIFIER-CANARY"
            source[dataset_key] = ("\n".join(dataset_lines) + "\n").encode("utf-8")
            manifest_key = (bucket, f"mlops/sources/{run_id}/dataset_manifest.json")
            manifest = json.loads(source[manifest_key])
            manifest["dataset_sha256"] = hashlib.sha256(source[dataset_key]).hexdigest()
            source[manifest_key] = (
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            s3 = FakeS3(source)
            dynamodb = FakeDynamoDB()
            with self.assertRaisesRegex(ValueError, "extra or missing fields"):
                run_serverless_pipeline(
                    {"source_mode": "feature_snapshot", "run_id": run_id},
                    environment={
                        "ALLOW_SYNTHETIC_MLOPS_RUN": SERVERLESS_ENABLE_VALUE,
                        "MLOPS_SYNTHETIC_ATTESTATION": SYNTHETIC_ATTESTATION,
                        "MLOPS_ARTIFACT_BUCKET": "synthetic-artifact-bucket",
                        "MLOPS_FEATURE_SNAPSHOT_BUCKET": bucket,
                        "MLOPS_RUN_TABLE": "synthetic-run-table",
                    },
                    s3_client=s3,
                    dynamodb_client=dynamodb,
                    work_root=root / "lambda-extra-field-work",
                )
            self.assertEqual(s3.objects, [])
            self.assertEqual(
                [item["Item"]["state"]["S"] for item in dynamodb.items],
                ["RUNNING", "FAILED_SAFE"],
            )

    def test_serverless_source_has_no_sagemaker_dependency(self) -> None:
        source_files = [
            MLOPS_ROOT / "export_runtime_training.py",
            MLOPS_ROOT / "train_challenger.py",
            MLOPS_ROOT / "run_runtime_pipeline.py",
            MLOPS_ROOT / "run_snapshot_pipeline.py",
            MLOPS_ROOT / "lambda_handler.py",
            MLOPS_ROOT / "requirements.txt",
            MLOPS_ROOT / "Dockerfile.lambda",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in source_files)
        self.assertNotIn("sagemaker", combined.casefold())
        self.assertIn(
            "COPY run_snapshot_pipeline.py ${LAMBDA_TASK_ROOT}/",
            (MLOPS_ROOT / "Dockerfile.lambda").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
