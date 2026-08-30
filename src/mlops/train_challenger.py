#!/usr/bin/env python3
"""Train and evaluate a synthetic-only offline challenger ranking model."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

from generate_synthetic_training import (
    FIELDNAMES as OFFLINE_FIELDNAMES,
    SCHEMA_VERSION as OFFLINE_SCHEMA_VERSION,
    TRAINING_FEATURES as OFFLINE_TRAINING_FEATURES,
    safe_output_directory,
    write_artifact,
)
from export_runtime_training import (
    FIELDNAMES as RUNTIME_FIELDNAMES,
    LABEL_NAME as RUNTIME_LABEL_NAME,
    SCHEMA_VERSION as RUNTIME_SCHEMA_VERSION,
    SYNTHETIC_ATTESTATION,
    TRAINING_FEATURES as RUNTIME_TRAINING_FEATURES,
)


MODEL_SCHEMA_VERSION = "jcareer-synthetic-ranking-challenger-v1"
EVALUATION_SCHEMA_VERSION = "jcareer-synthetic-ranking-evaluation-v1"


def clipped_probability(value: float) -> float:
    return min(1.0 - 1e-9, max(1e-9, value))


def sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


def load_contract(
    manifest_path: Path,
) -> tuple[dict[str, object], list[dict[str, object]], bytes, list[str], str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema_version = manifest.get("schema_version")
    if schema_version == OFFLINE_SCHEMA_VERSION:
        required_contract = {
            "schema_version": OFFLINE_SCHEMA_VERSION,
            "synthetic_only": True,
            "member_data_used": False,
            "company_customer_data_used": False,
            "purpose": "offline_challenger_model_demonstration",
            "runtime_wired": False,
            "human_decision_required_before_runtime_use": True,
        }
        training_features = OFFLINE_TRAINING_FEATURES
        label_name = "synthetic_engagement"
        expected_fieldnames = OFFLINE_FIELDNAMES
    elif schema_version == RUNTIME_SCHEMA_VERSION:
        required_contract = {
            "schema_version": RUNTIME_SCHEMA_VERSION,
            "synthetic_only": True,
            "synthetic_attestation": SYNTHETIC_ATTESTATION,
            "member_data_used": True,
            "company_customer_data_used": True,
            "purpose": "synthetic_runtime_challenger_training_demonstration",
            "source_runtime_db_wired": True,
            "ranking_runtime_wired": False,
            "runtime_wired": False,
            "human_decision_required_before_runtime_use": True,
        }
        training_features = RUNTIME_TRAINING_FEATURES
        label_name = RUNTIME_LABEL_NAME
        expected_fieldnames = RUNTIME_FIELDNAMES
    else:
        raise ValueError("dataset manifest schema version is unsupported")
    for key, expected in required_contract.items():
        if manifest.get(key) != expected:
            raise ValueError(f"dataset manifest rejects {key}: expected {expected!r}")
    field_roles = manifest.get("field_roles")
    if not isinstance(field_roles, dict) or field_roles.get("training_features") != training_features:
        raise ValueError("dataset manifest training feature contract mismatch")
    if field_roles.get("label") != label_name:
        raise ValueError("dataset manifest label contract mismatch")

    dataset_name = manifest.get("dataset_file")
    if not isinstance(dataset_name, str) or Path(dataset_name).name != dataset_name:
        raise ValueError("dataset file must be a sibling basename")
    dataset_path = manifest_path.parent / dataset_name
    dataset_content = dataset_path.read_bytes()
    observed_hash = hashlib.sha256(dataset_content).hexdigest()
    if observed_hash != manifest.get("dataset_sha256"):
        raise ValueError("dataset SHA-256 does not match manifest")

    reader = csv.DictReader(dataset_content.decode("utf-8").splitlines())
    if reader.fieldnames != expected_fieldnames:
        raise ValueError("dataset columns do not match the synthetic contract")
    rows: list[dict[str, object]] = []
    for line_number, raw in enumerate(reader, start=2):
        if not str(raw["candidate_ref"]).startswith("syn-candidate-"):
            raise ValueError(f"row {line_number}: candidate reference is not synthetic")
        if not str(raw["job_ref"]).startswith("syn-job-"):
            raise ValueError(f"row {line_number}: job reference is not synthetic")
        if not str(raw["company_ref"]).startswith("syn-company-"):
            raise ValueError(f"row {line_number}: company reference is not synthetic")
        features = [float(raw[name]) for name in training_features]
        if any(not 0.0 <= value <= 1.0 for value in features):
            raise ValueError(f"row {line_number}: feature outside 0..1")
        label = int(raw[label_name])
        if label not in {0, 1}:
            raise ValueError(f"row {line_number}: label outside 0/1")
        if raw["evaluation_group"] not in {
            "synthetic-a",
            "synthetic-b",
            "synthetic-cohort-a",
            "synthetic-cohort-b",
        }:
            raise ValueError(f"row {line_number}: unknown synthetic evaluation group")
        if raw["split"] not in {"train", "test"}:
            raise ValueError(f"row {line_number}: unknown split")
        rows.append(
            {
                "candidate_ref": raw["candidate_ref"],
                "features": features,
                "label": label,
                "evaluation_group": raw["evaluation_group"],
                "split": raw["split"],
            }
        )
    if len(rows) != manifest.get("row_count"):
        raise ValueError("dataset row count does not match manifest")
    if not rows or not any(row["split"] == "train" for row in rows) or not any(row["split"] == "test" for row in rows):
        raise ValueError("dataset must contain non-empty train and test splits")
    return manifest, rows, dataset_content, list(training_features), label_name


def train_logistic(
    rows: list[dict[str, object]],
    training_features: list[str],
    epochs: int,
    learning_rate: float,
    l2: float,
) -> tuple[list[float], float]:
    train_rows = [row for row in rows if row["split"] == "train"]
    weights = [0.0 for _ in training_features]
    intercept = 0.0
    for _ in range(epochs):
        weight_gradients = [0.0 for _ in training_features]
        intercept_gradient = 0.0
        for row in train_rows:
            features = row["features"]
            prediction = sigmoid(intercept + sum(weight * feature for weight, feature in zip(weights, features)))
            error = prediction - row["label"]
            intercept_gradient += error
            for index, feature in enumerate(features):
                weight_gradients[index] += error * feature
        scale = 1.0 / len(train_rows)
        intercept -= learning_rate * intercept_gradient * scale
        for index in range(len(weights)):
            regularized_gradient = weight_gradients[index] * scale + l2 * weights[index]
            weights[index] -= learning_rate * regularized_gradient
    return weights, intercept


def challenger_probability(row: dict[str, object], weights: list[float], intercept: float) -> float:
    return sigmoid(intercept + sum(weight * feature for weight, feature in zip(weights, row["features"])))


def baseline_probability(row: dict[str, object]) -> float:
    skill, experience, role = row["features"][:3]
    baseline_score = (0.7 * skill) + (0.2 * experience) + (0.1 * role)
    return sigmoid(-2.4 + (4.8 * baseline_score))


def log_loss(labels: list[int], predictions: list[float]) -> float:
    total = 0.0
    for label, prediction in zip(labels, predictions):
        probability = clipped_probability(prediction)
        total += -(label * math.log(probability) + (1 - label) * math.log(1 - probability))
    return total / len(labels)


def brier_score(labels: list[int], predictions: list[float]) -> float:
    return sum((prediction - label) ** 2 for label, prediction in zip(labels, predictions)) / len(labels)


def auc(labels: list[int], predictions: list[float]) -> float | None:
    positives = [prediction for label, prediction in zip(labels, predictions) if label == 1]
    negatives = [prediction for label, prediction in zip(labels, predictions) if label == 0]
    if not positives or not negatives:
        return None
    wins = 0.0
    for positive in positives:
        for negative in negatives:
            if positive > negative:
                wins += 1.0
            elif positive == negative:
                wins += 0.5
    return wins / (len(positives) * len(negatives))


def ndcg_at_k(rows: list[dict[str, object]], predictions: list[float], k: int = 5) -> float | None:
    grouped: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for row, prediction in zip(rows, predictions):
        grouped[str(row["candidate_ref"])].append((int(row["label"]), prediction))
    values: list[float] = []
    for candidate_rows in grouped.values():
        ideal = sorted((label for label, _ in candidate_rows), reverse=True)[:k]
        ideal_dcg = sum(label / math.log2(index + 2) for index, label in enumerate(ideal))
        if ideal_dcg == 0:
            continue
        ranked = sorted(candidate_rows, key=lambda item: item[1], reverse=True)[:k]
        observed_dcg = sum(label / math.log2(index + 2) for index, (label, _) in enumerate(ranked))
        values.append(observed_dcg / ideal_dcg)
    return sum(values) / len(values) if values else None


def rounded(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None


def metric_set(rows: list[dict[str, object]], predictions: list[float]) -> dict[str, object]:
    labels = [int(row["label"]) for row in rows]
    return {
        "row_count": len(rows),
        "observed_positive_rate": rounded(sum(labels) / len(labels)),
        "mean_prediction": rounded(sum(predictions) / len(predictions)),
        "log_loss": rounded(log_loss(labels, predictions)),
        "brier_score": rounded(brier_score(labels, predictions)),
        "auc": rounded(auc(labels, predictions)),
        "ndcg_at_5": rounded(ndcg_at_k(rows, predictions, 5)),
    }


def evaluate(rows: list[dict[str, object]], weights: list[float], intercept: float) -> dict[str, object]:
    test_rows = [row for row in rows if row["split"] == "test"]
    challenger = [challenger_probability(row, weights, intercept) for row in test_rows]
    baseline = [baseline_probability(row) for row in test_rows]
    group_observations: dict[str, object] = {}
    for group in sorted({str(row["evaluation_group"]) for row in test_rows}):
        indexes = [index for index, row in enumerate(test_rows) if row["evaluation_group"] == group]
        group_rows = [test_rows[index] for index in indexes]
        group_predictions = [challenger[index] for index in indexes]
        group_observations[group] = metric_set(group_rows, group_predictions)
    return {
        "challenger": metric_set(test_rows, challenger),
        "platform_70_20_10_reference": metric_set(test_rows, baseline),
        "synthetic_group_observations": group_observations,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out-dir", default="measurement/out/mlops-demo/model")
    parser.add_argument("--epochs", type=int, default=700)
    parser.add_argument("--learning-rate", type=float, default=0.35)
    parser.add_argument("--l2", type=float, default=0.002)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def train_from_manifest(
    *,
    manifest_path: Path,
    output_directory: Path,
    epochs: int = 700,
    learning_rate: float = 0.35,
    l2: float = 0.002,
    overwrite: bool = False,
) -> dict[str, Path]:
    if not 10 <= epochs <= 10_000:
        raise ValueError("epochs must be between 10 and 10000")
    if not 0.0001 <= learning_rate <= 1.0:
        raise ValueError("learning rate must be between 0.0001 and 1.0")
    if not 0.0 <= l2 <= 1.0:
        raise ValueError("l2 must be between 0 and 1")

    manifest, rows, _, training_features, label_name = load_contract(
        manifest_path.resolve()
    )
    weights, intercept = train_logistic(
        rows, training_features, epochs, learning_rate, l2
    )
    observations = evaluate(rows, weights, intercept)
    model_path = output_directory / "challenger_model.json"
    evaluation_path = output_directory / "evaluation_observations.json"
    runtime_source = manifest["schema_version"] == RUNTIME_SCHEMA_VERSION
    model = {
        "schema_version": MODEL_SCHEMA_VERSION,
        "model_kind": (
            "logistic_synthetic_pipeline_progression_challenger"
            if runtime_source
            else "logistic_synthetic_engagement_challenger"
        ),
        "model_state": (
            "TRAINED_SYNTHETIC_RUNTIME_DATA_NOT_APPROVED"
            if runtime_source
            else "TRAINED_SYNTHETIC_NOT_APPROVED"
        ),
        "approval_state": "HUMAN_DECISION_NOT_RECORDED",
        "runtime_wired": False,
        "can_change_runtime_ranking": False,
        "training_features": training_features,
        "weights": {name: round(value, 12) for name, value in zip(training_features, weights)},
        "intercept": round(intercept, 12),
        "source_dataset": {
            "schema_version": manifest["schema_version"],
            "sha256": manifest["dataset_sha256"],
            "row_count": manifest["row_count"],
            "source_digest": manifest.get("source_digest"),
        },
        "training_configuration": {
            "epochs": epochs,
            "learning_rate": learning_rate,
            "l2": l2,
        },
        "output_semantics": (
            "synthetic_pipeline_progression_proxy_not_candidate_quality_or_hiring_probability"
            if runtime_source
            else "synthetic_engagement_estimate_not_hiring_probability"
        ),
        "human_decision_required_before_any_runtime_use": True,
    }
    if "seed" in manifest:
        model["source_dataset"]["seed"] = manifest["seed"]
    model_content = (json.dumps(model, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    model_sha256 = hashlib.sha256(model_content).hexdigest()
    evaluation = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "observation_state": (
            "MEASURED_SYNTHETIC_RUNTIME_NOT_ASSESSED"
            if runtime_source
            else "MEASURED_SYNTHETIC_NOT_ASSESSED"
        ),
        "automatic_pass_fail_gate": False,
        "compliance_conclusion": None,
        "fairness_conclusion": None,
        "runtime_release_decision": None,
        "model_sha256": model_sha256,
        "dataset_sha256": manifest["dataset_sha256"],
        "metrics": observations,
        "metric_notes": {
            label_name: (
                "historical application status proxy; not hiring success or candidate quality"
                if runtime_source
                else "generated label; not hiring success or candidate quality"
            ),
            "platform_70_20_10_reference": "offline numeric reference; current runtime output remains unchanged",
            "synthetic_group_observations": "descriptive values only; a person determines any interpretation",
        },
        "known_limitations": (
            [
                "historical application status can reproduce recruiter behavior",
                "unresolved applied status rows are excluded",
                "no automatic compliance, fairness, or release decision is made",
            ]
            if runtime_source
            else []
        ),
    }
    evaluation_content = (json.dumps(evaluation, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    write_artifact(model_path, model_content, overwrite)
    write_artifact(evaluation_path, evaluation_content, overwrite)
    return {"model": model_path, "evaluation": evaluation_path}


def main() -> int:
    args = parse_args()
    try:
        paths = train_from_manifest(
            manifest_path=Path(args.manifest),
            output_directory=safe_output_directory(args.out_dir),
            epochs=args.epochs,
            learning_rate=args.learning_rate,
            l2=args.l2,
            overwrite=args.overwrite,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    model = json.loads(paths["model"].read_text(encoding="utf-8"))
    print(f"CHALLENGER_MODEL={model['model_state']}")
    print(f"MODEL_PATH={paths['model']}")
    print(f"EVALUATION_PATH={paths['evaluation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
