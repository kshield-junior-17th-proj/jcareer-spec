#!/usr/bin/env python3
"""Generate a deterministic, synthetic-only ranking-training dataset.

The generator intentionally has no ingestion path for member or company exports.
It exists to make an offline MLOps demonstration reproducible without personal data.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import random
from pathlib import Path


SCHEMA_VERSION = "jcareer-synthetic-ranking-dataset-v1"
TRAINING_FEATURES = ["skill_overlap", "experience_fit", "role_overlap"]
FIELDNAMES = [
    "candidate_ref",
    "job_ref",
    "company_ref",
    *TRAINING_FEATURES,
    "synthetic_engagement",
    "evaluation_group",
    "split",
]
FORBIDDEN_OUTPUT_PARTS = {
    ("docs", "current"),
    ("context", "raw"),
    ("context", "proposals"),
    ("terraform",),
}


def sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


def stable_split(candidate_ref: str) -> str:
    marker = hashlib.sha256(candidate_ref.encode("utf-8")).digest()[0]
    return "train" if marker < 205 else "test"


def build_rows(seed: int, candidate_count: int, job_count: int, pairs_per_candidate: int) -> list[dict[str, object]]:
    rng = random.Random(seed)
    rows: list[dict[str, object]] = []
    for candidate_index in range(1, candidate_count + 1):
        candidate_ref = f"syn-candidate-{candidate_index:05d}"
        evaluation_group = "synthetic-a" if candidate_index % 2 else "synthetic-b"
        selected_jobs = rng.sample(range(1, job_count + 1), k=pairs_per_candidate)
        candidate_skill_tendency = rng.betavariate(2.4, 2.0)
        candidate_experience_tendency = rng.betavariate(2.0, 2.2)
        candidate_role_tendency = rng.betavariate(2.2, 2.0)
        for job_index in sorted(selected_jobs):
            skill_overlap = min(1.0, max(0.0, candidate_skill_tendency * 0.72 + rng.random() * 0.28))
            experience_fit = min(1.0, max(0.0, candidate_experience_tendency * 0.68 + rng.random() * 0.32))
            role_overlap = min(1.0, max(0.0, candidate_role_tendency * 0.64 + rng.random() * 0.36))

            # Synthetic latent relationship only. It is not a claim about hiring quality.
            latent = -2.35 + (2.35 * skill_overlap) + (1.25 * experience_fit) + (1.75 * role_overlap)
            synthetic_engagement = 1 if rng.random() < sigmoid(latent) else 0
            rows.append(
                {
                    "candidate_ref": candidate_ref,
                    "job_ref": f"syn-job-{job_index:04d}",
                    "company_ref": f"syn-company-{((job_index - 1) % max(1, job_count // 3)) + 1:03d}",
                    "skill_overlap": f"{skill_overlap:.6f}",
                    "experience_fit": f"{experience_fit:.6f}",
                    "role_overlap": f"{role_overlap:.6f}",
                    "synthetic_engagement": synthetic_engagement,
                    "evaluation_group": evaluation_group,
                    "split": stable_split(candidate_ref),
                }
            )
    return rows


def csv_bytes(rows: list[dict[str, object]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDNAMES, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def safe_output_directory(raw_path: str) -> Path:
    root = repository_root()
    path = Path(raw_path)
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        return resolved
    relative_parts = tuple(part.lower() for part in relative.parts)
    for forbidden in FORBIDDEN_OUTPUT_PARTS:
        if relative_parts[: len(forbidden)] == forbidden:
            raise ValueError(f"output directory is protected for this demonstrator: {relative.as_posix()}")
    return resolved


def write_artifact(path: Path, content: bytes, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite existing artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="measurement/out/mlops-demo")
    parser.add_argument("--seed", type=int, default=42001)
    parser.add_argument("--candidates", type=int, default=240)
    parser.add_argument("--jobs", type=int, default=30)
    parser.add_argument("--pairs-per-candidate", type=int, default=12)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.candidates < 20:
        raise SystemExit("--candidates must be at least 20")
    if args.jobs < 5:
        raise SystemExit("--jobs must be at least 5")
    if not 2 <= args.pairs_per_candidate <= args.jobs:
        raise SystemExit("--pairs-per-candidate must be between 2 and --jobs")

    output_directory = safe_output_directory(args.out_dir)
    rows = build_rows(args.seed, args.candidates, args.jobs, args.pairs_per_candidate)
    dataset_content = csv_bytes(rows)
    dataset_sha256 = hashlib.sha256(dataset_content).hexdigest()
    dataset_path = output_directory / "ranking_dataset.csv"
    manifest_path = output_directory / "dataset_manifest.json"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "synthetic_only": True,
        "member_data_used": False,
        "company_customer_data_used": False,
        "purpose": "offline_challenger_model_demonstration",
        "runtime_wired": False,
        "seed": args.seed,
        "row_count": len(rows),
        "candidate_count": args.candidates,
        "job_count": args.jobs,
        "pairs_per_candidate": args.pairs_per_candidate,
        "dataset_file": dataset_path.name,
        "dataset_sha256": dataset_sha256,
        "field_roles": {
            "training_features": TRAINING_FEATURES,
            "label": "synthetic_engagement",
            "evaluation_only": ["evaluation_group"],
            "logical_identifiers_not_features": ["candidate_ref", "job_ref", "company_ref"],
            "split": "split",
        },
        "excluded_real_world_fields": [
            "name",
            "email",
            "phone",
            "birth_date",
            "address",
            "school_name",
            "self_intro_raw",
            "disability",
            "veteran_status",
            "gender",
        ],
        "human_decision_required_before_runtime_use": True,
    }
    manifest_content = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    write_artifact(dataset_path, dataset_content, args.overwrite)
    write_artifact(manifest_path, manifest_content, args.overwrite)
    print(f"SYNTHETIC_DATASET=CREATED rows={len(rows)} sha256={dataset_sha256}")
    print(f"DATASET_PATH={dataset_path}")
    print(f"MANIFEST_PATH={manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
