# Synthetic serverless MLOps operator workflow

`invoke-synthetic-demo.ps1` is the guarded operator path for the AS-IS synthetic demonstration. It does not open PostgreSQL to the host or to the Internet. The exporter is attached temporarily to the existing `jcareer-asis-runtime_default` Docker network on the validated lab instance.

The script defaults to plan only. All modes require the exact acknowledgement string. Use placeholders locally; do not paste identifiers into reports, chat, screenshots, or terminal recordings.

```powershell
$common = @{
  ActivationAcknowledgement = 'JCAREER_SYNTHETIC_SERVERLESS_MLOPS_APPROVED'
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

The invocation path validates the managed lab tags and SSM status, transfers only the bounded exporter source, and builds an ephemeral exporter image on the lab host. The exporter reads the two logical synthetic databases over the Compose network and returns one digest-checked compressed archive containing exactly:

- `ranking_dataset.csv`
- `dataset_manifest.json`
- `source_read_receipt.json`

Those files are uploaded under `mlops/sources/{run_id}/`. The Lambda is invoked once in `feature_snapshot` mode. Success requires the DynamoDB state `TRAINED_PENDING_HUMAN_REVIEW`, six exact result objects under `mlops/runs/{run_id}/`, `runtime_ranking_wired=false`, and `automatic_model_activation=false`.

The script blocks any Terraform plan containing a delete or replacement action. It never stops or destroys the lab. Temporary local files and the temporary Docker credential directory are removed when the process ends. The remote exporter image and per-run work directory are also removed. A failed transfer can leave only the uniquely named `/tmp/jcareer-mlops-exporter-{run_id}.*` transfer file for an operator to inspect and remove deliberately.

This workflow does not establish production model quality, fairness, legal compliance, certification readiness, or release approval. A person must review the synthetic observations and decide whether any challenger can progress beyond the demonstration boundary.
