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

As of the redacted 2026-08-31 observation, the reviewed bootstrap saved plan was
applied and its 13 foundation resources exist. The digest-pinned image was not
published, the runtime Lambda was not deployed or invoked, and no result or
service integration is claimed.

There is no API endpoint, NAT Gateway, RDS instance, schedule, or automatic
model activation. The Lambda concurrency is one. If a separately authorized one-shot run occurs, its result remains
`TRAINED_PENDING_HUMAN_REVIEW`; a person decides whether anything may happen
after that. This state is not a compliance, fairness, or release decision.

The same Lambda source also accepts a separately invoked `record_human_review`
action. It requires a synthetic approver reference, an explicit `APPROVED` or
`REJECTED` human input, and the exact S3 key, SHA-256, and VersionId bindings of
all six artifacts from a pending run. Result uploads use `IfNoneMatch=*`; a
conditional DynamoDB update stores the review receipt and its
digest only when the run is still pending and no review exists. The decision is
input recording, not an automatic model-quality, fairness, compliance, or
release assessment. It does not rewrite S3 artifacts, activate a model, or wire
runtime ranking.

The recorded state is `HUMAN_INPUT_RECORDED`; `APPROVED` or `REJECTED` is held
in a separate `decision` field with a record-only decision scope and
`release_authorized=false`. An identical retry validates and returns the stored
receipt. A retry with different approver, decision, or artifact bindings is
rejected.

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

Names, email addresses, phone numbers, raw self-introductions, raw project text, raw company
direction text, and raw job summaries are not persisted in the snapshot.
Stable synthetic references and numeric derived features are present. The
application-status label is a pipeline-progression proxy, not candidate quality,
hiring probability, or employment success.

The current package pools rows from multiple synthetic company customers into one
platform-wide demonstration challenger. It does not prove tenant-specific training
authorization or tenant-isolated models. Whether production learning is global or
per-company is a separate human architecture and data-governance decision. The
separate synthetic `passed/not_passed` document-outcome store is not connected as a
training label.

The exporter does not have application-time resume, job, or company snapshots. It joins
the current resume and current company/job text to the current application-status proxy.
Content changed after the application or status transition can therefore be paired with
an earlier outcome state. Member, application, consent, and company/job reads also use
separate database connections without a shared transaction watermark, so the source
receipt does not prove one atomic cross-database point in time. These rows are suitable
only for the bounded synthetic pipeline demonstration, not as evidence of historical
prediction performance.

The latest `privacy_core` grant is only a synthetic lifecycle filter and is not model
training consent. A later withdrawal or account deletion does not currently invalidate
an already exported S3 snapshot, trained artifact, or DynamoDB run record. Production use
requires a separate purpose/consent decision and a source-withdrawal invalidation policy.

Company/job export additionally requires the runtime seed-bound company profile
marker `company-profile-seed-20260826` on every joined job row. A caller-provided
attestation string alone is insufficient. This marker rejects unmarked companies
and edited company profiles, but it is not a cryptographic commitment to job text;
production use needs a separately approved immutable company/job source receipt.

Training completion stores the exact six artifact hashes with the pending run
state together with each S3 key and VersionId. A later human-review request must
submit the same complete bindings; missing or mismatched values leave the
pending state unchanged. Review receipt
JSON is held in the conditionally updated run-state item, so the six-object S3
result contract remains unchanged.

S3 source/result versions expire under the configured lifecycle while the DynamoDB run
table currently has no TTL. `record_human_review` validates stored key/hash/VersionId
bindings but does not first prove that every bound S3 version still exists. The review
deadline, artifact retention, exact-version existence check, and any longer-lived archive
remain human architecture decisions; a recorded input is not proof that an expired
artifact can still be reproduced.

Uploads are sequential. A failed run can therefore leave partial S3 objects.
Object presence or count alone is never success evidence; only the DynamoDB
`TRAINED_PENDING_HUMAN_REVIEW` state with all six version bindings is the
training-completion signal. Partial objects associated with `FAILED_SAFE` are
not successful run artifacts.

Two current numeric features derive from self-introduction text plus reviewed
project fields (`title`, `role`, `summary`, `outcome`, and `technologies`) versus
a job description and company direction, but they are token-overlap proxies. They are
not Bedrock embeddings and must not be presented as semantic understanding.
The existing Bedrock explanation lane may describe qualitative alignment without
changing the deterministic score. A later reviewed feature contract may add
versioned embedding similarities to the challenger; it is not wired here.
These token-overlap features can be gamed by copying job-description or company-value
terms and therefore must not be interpreted as robust qualitative understanding.

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

The bootstrap-only AWS deployment has a separately authorized redacted receipt.
No image publication, runtime Lambda deployment, live invocation, result production,
human review, or recommendation-service integration is claimed.
