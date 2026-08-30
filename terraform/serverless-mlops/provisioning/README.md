# Synthetic serverless MLOps operator workflow

`invoke-synthetic-demo.ps1` is the guarded operator path for the AS-IS synthetic demonstration. It does not open PostgreSQL to the host or to the Internet. The exporter is attached temporarily to the existing `jcareer-asis-runtime_default` Docker network on the validated lab instance.

The script defaults to plan only. All modes require the exact acknowledgement string. Use placeholders locally; do not paste identifiers into reports, chat, screenshots, or terminal recordings.

```powershell
$common = @{
  ActivationAcknowledgement = 'JCAREER_SYNTHETIC_SERVERLESS_MLOPS_APPROVED'
  # Lowercase SHA-256 of the separately approved 12-digit provider account ID.
  # Derive it outside recorded output; never paste or persist the raw account ID.
  ProviderAccountSha256      = '<approved-provider-account-sha256>'
  InstanceId                = '<managed-lab-instance-id>'
  ArtifactBucketName        = '<globally-unique-managed-bucket-name>'
}

# Saved bootstrap plan and non-destructive allowlist check only.
./terraform/serverless-mlops/provisioning/invoke-synthetic-demo.ps1 @common

# Apply bootstrap and runtime saved plans, build/scan/push the Lambda image,
# and pin the function to the observed ECR digest. Does not read the DB or invoke.
./terraform/serverless-mlops/provisioning/invoke-synthetic-demo.ps1 @common -Apply

# Explicit one-shot demonstration gate.
./terraform/serverless-mlops/provisioning/invoke-synthetic-demo.ps1 @common -Apply -Invoke
```

The account hash is mandatory and empty, malformed, repeated-character placeholder values fail closed. The script retrieves the caller account only into process memory, hashes it immediately, and compares the hash again before plan capture, each saved-plan apply, registry mutation, snapshot upload, and Lambda invocation. The raw account ID is not added to the approval context or printed. All external tools are resolved once to direct absolute `.exe` paths; a function, alias, script, or cmdlet shadow with the same name blocks execution.

Each saved Terraform plan is copied into a current-user-only protected snapshot and held with a read lock. Its redacted JSON view and a context containing only hashes, region, run ID, and acknowledgement bindings are locked with it. The plan and JSON hashes plus the provider-account hash are rechecked immediately before applying the protected plan path. Success output is emitted only after protected snapshot and temporary-directory cleanup is observed.

The invocation path validates the managed lab tags and SSM status, transfers only the bounded exporter source, and builds an ephemeral exporter image on the lab host. The exporter reads the two logical synthetic databases over the Compose network and returns one digest-checked compressed archive containing exactly:

- `ranking_dataset.csv`
- `dataset_manifest.json`
- `source_read_receipt.json`

Those files are uploaded under `mlops/sources/{run_id}/`. The Lambda is invoked once in `feature_snapshot` mode. Success requires the DynamoDB state `TRAINED_PENDING_HUMAN_REVIEW`, six exact result objects under `mlops/runs/{run_id}/`, `runtime_ranking_wired=false`, and `automatic_model_activation=false`.

The operator script intentionally stops at that pending state. The deployed
Lambda source has a separate `record_human_review` action, but this script does
not manufacture or submit a review decision. A later authorized caller must
provide a bounded synthetic approver reference, `APPROVED` or `REJECTED`, and
the exact six S3 key, SHA-256, and VersionId bindings returned by training.
Missing or mismatched input,
a non-pending run, or an existing receipt is rejected without overwriting the
model artifacts. Recording either decision does not activate the model or
connect it to runtime ranking; the state is `HUMAN_INPUT_RECORDED`, the decision
is separate, and `release_authorized=false` remains explicit.

The script blocks any Terraform plan containing a delete or replacement action. It never stops or destroys the lab. Temporary local files and the temporary Docker credential directory are removed when the process ends. The remote exporter image and per-run work directory are also removed. A failed transfer can leave only the uniquely named `/tmp/jcareer-mlops-exporter-{run_id}.*` transfer file for an operator to inspect and remove deliberately.

Artifact purge/destroy authorization and a remote Terraform state design are intentionally outside this workflow. A person must decide those boundaries before adding any cleanup mutation or shared state backend; this operator does not infer or execute either one.

This workflow does not establish production model quality, fairness, legal compliance, certification readiness, or release approval. A person must review the synthetic observations and decide whether any challenger can progress beyond the demonstration boundary.
