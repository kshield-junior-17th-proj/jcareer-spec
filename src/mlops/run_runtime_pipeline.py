#!/usr/bin/env python3
"""Run the synthetic runtime DB challenger pipeline once.

This is the shared core used by the CLI and Lambda adapter. It never activates
the challenger or changes the runtime ranking path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from export_runtime_training import SYNTHETIC_ATTESTATION, export_runtime_dataset
from generate_synthetic_training import safe_output_directory, write_artifact
from train_challenger import train_from_manifest


RUN_SCHEMA_VERSION = "jcareer-synthetic-runtime-mlops-run-v1"
RUN_ID_PATTERN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}")


def validate_run_id(run_id: str) -> str:
    if RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise ValueError("run_id must be 1..80 safe characters")
    return run_id


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_pipeline(
    *,
    member_database_url: str,
    company_database_url: str,
    output_root: Path,
    synthetic_attestation: str,
    run_id: str,
    epochs: int = 320,
    overwrite: bool = False,
) -> dict[str, Path]:
    validate_run_id(run_id)
    if synthetic_attestation != SYNTHETIC_ATTESTATION:
        raise ValueError("synthetic runtime attestation is required")
    dataset_directory = output_root / "dataset"
    model_directory = output_root / "model"
    exported = export_runtime_dataset(
        member_database_url=member_database_url,
        company_database_url=company_database_url,
        output_directory=dataset_directory,
        synthetic_attestation=synthetic_attestation,
        overwrite=overwrite,
    )
    trained = train_from_manifest(
        manifest_path=exported["manifest"],
        output_directory=model_directory,
        epochs=epochs,
        overwrite=overwrite,
    )
    artifacts = {**exported, **trained}
    run_receipt_path = output_root / "pipeline_run_receipt.json"
    run_receipt = {
        "schema_version": RUN_SCHEMA_VERSION,
        "run_id": run_id,
        "execution_mode": "ON_DEMAND_SERVERLESS_COMPATIBLE",
        "synthetic_only": True,
        "source_runtime_db_wired": True,
        "challenger_trained": True,
        "runtime_ranking_wired": False,
        "automatic_model_activation": False,
        "approval_state": "HUMAN_DECISION_NOT_RECORDED",
        "model_state": "TRAINED_SYNTHETIC_RUNTIME_DATA_NOT_APPROVED",
        "artifact_sha256": {
            name: _sha256(path) for name, path in sorted(artifacts.items())
        },
        "human_decision_required_before_any_runtime_use": True,
    }
    write_artifact(
        run_receipt_path,
        (json.dumps(run_receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        overwrite,
    )
    artifacts["run_receipt"] = run_receipt_path
    return artifacts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--member-database-url", required=True)
    parser.add_argument("--company-database-url", required=True)
    parser.add_argument("--synthetic-attestation", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--out-dir", default="measurement/out/mlops-runtime/run")
    parser.add_argument("--epochs", type=int, default=320)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        artifacts = run_pipeline(
            member_database_url=args.member_database_url,
            company_database_url=args.company_database_url,
            output_root=safe_output_directory(args.out_dir),
            synthetic_attestation=args.synthetic_attestation,
            run_id=args.run_id,
            epochs=args.epochs,
            overwrite=args.overwrite,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print("MLOPS_RUN=TRAINED_PENDING_HUMAN_REVIEW")
    print(f"ARTIFACT_COUNT={len(artifacts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
