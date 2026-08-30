# J-Career synthetic serverless MLOps demo

This is an isolated Terraform root for a short-lived, synthetic-only MLOps
demonstration. It does not modify or apply `terraform/asis`, does not change the
reviewed one-EC2 inventory in `terraform/lab`, and does not use SageMaker.

## What this root can create after explicit enablement

- an immutable, scan-on-push ECR repository for the Lambda image;
- a private, versioned, SSE-S3 bucket for feature snapshots and results;
- a PAY_PER_REQUEST DynamoDB table for idempotent run state;
- a bounded CloudWatch log group and a path-scoped Lambda role; and
- one on-demand, digest-pinned Lambda only in `runtime` stage.

These are planned/creatable targets, not a statement that they currently exist.

There is no API endpoint, NAT Gateway, RDS instance, schedule, or automatic
model activation. The Lambda concurrency is one. If a separately authorized one-shot run occurs, its result remains
`TRAINED_PENDING_HUMAN_REVIEW`; a person decides whether anything may happen
after that. This state is not a compliance, fairness, or release decision.

Enablement/event/config validation and the conditional initial `RUNNING` write
occur before the fail-state boundary. A pre-state rejection, duplicate run ID,
or failed initial state write can therefore end without a `FAILED_SAFE` record.
Only failures after `RUNNING` attempt that transition.

## Data path

```text
synthetic member DB + synthetic company DB (inside the EC2 lab)
  -> exporter derives five numeric matching features
  -> one feature CSV and two validation JSON files under mlops/sources/<run-id>/
  -> one-shot Lambda validates cross-file digests and trains a challenger
  -> six artifacts under mlops/runs/<run-id>/ + DynamoDB run state
```

Names, email addresses, phone numbers, raw self-introductions, raw company
direction text, and raw job summaries are not persisted in the snapshot.
Stable synthetic references and numeric derived features are present. The
application-status label is a pipeline-progression proxy, not candidate quality,
hiring probability, or employment success.

Two current numeric features derive from self-introduction text versus a job
description and company direction, but they are token-overlap proxies. They are
not Bedrock embeddings and must not be presented as semantic understanding.
The existing Bedrock explanation lane may describe qualitative alignment without
changing the deterministic score. A later reviewed feature contract may add
versioned embedding similarities to the challenger; it is not wired here.

The lab's PostgreSQL port stays inside Docker and the lab security group keeps
zero inbound rules. The feature-only package is exported beside the database;
the Lambda therefore needs no DB URL, DB password, VPC attachment, or NAT.

## Fail-closed stages

- `disabled` (default): zero managed resources.
- `bootstrap`: ECR, S3, DynamoDB, logs, and IAM only.
- `runtime`: bootstrap resources plus the digest-pinned Lambda.

Both non-disabled stages require the exact human acknowledgement
`JCAREER_SYNTHETIC_SERVERLESS_MLOPS_APPROVED`. Runtime additionally rejects an
image URI that is not an `@sha256` reference from the ECR repository managed by
this same root. The acknowledgement is a procedural opt-in, not authentication
or proof of organizational approval. Do not use `-target`.

## AWS-free source verification

These commands do not apply infrastructure:

```powershell
python scripts/check_serverless_mlops_static.py --root .
python tests/test_serverless_mlops_static.py
python -m unittest src/mlops/tests/test_synthetic_pipeline.py
terraform -chdir=terraform/serverless-mlops init -backend=false
terraform -chdir=terraform/serverless-mlops fmt -check
terraform -chdir=terraform/serverless-mlops validate
```

With mock environment credentials, the default disabled plan has zero resource
changes. A successful source test or disabled plan is not AWS execution evidence.

## Operator boundary

The operator workflow under `provisioning/` must be run only after the separate
EC2 lab is running and its six-service runtime has passed remote smoke checks.
Plan is the default; AWS mutation and Lambda invocation require separate explicit
switches. The workflow must use saved plans, reject deletion/replacement, avoid
printing account/resource identifiers, and never stop or destroy the lab.

The guarded entrypoint is
`terraform/serverless-mlops/provisioning/invoke-synthetic-demo.ps1`; see the
adjacent `provisioning/README.md` for plan-only, deploy-only, and explicit
one-shot invocation forms.

The protected `.github/**` workflows do not currently deploy this independent
root. A workflow owner must review and add that integration later; the human
acknowledgement must not be hard-coded into CI.

No AWS deployment or live invocation is claimed until a separately authorized operator run
produces its own redacted receipt.
