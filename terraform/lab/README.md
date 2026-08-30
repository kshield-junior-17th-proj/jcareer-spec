# J-Career synthetic AWS runtime lab

This root is the short-lived runtime-preview apply surface. It is not
`terraform/asis`, a client environment, or a production service. AWS resource mutation
remains disabled until an operator supplies the explicit activation acknowledgement and
applies the allowlisted saved plan. Plan-only is not offline: it performs read-only STS,
provider refresh, and data-source calls. The lab root does not yet bind that plan to a
separately signed approval record. This source alone does not claim a current deployment
or provider call. The dated deployment observation records one direct Bedrock synthetic
call, one permission-blocked Lab apply, its exact cleanup, and the resulting zero-resource
state.

현재 확인 결과와 재시도 조건은
[`DEPLOYMENT_OBSERVATION_2026-08-30.md`](DEPLOYMENT_OBSERVATION_2026-08-30.md)에 정리했다.
필요한 IAM 작업과 이름·태그·리전 제한은
[`IAM_RETRY_PREREQUISITES_2026-08-30.md`](IAM_RETRY_PREREQUISITES_2026-08-30.md)에서
확인할 수 있다.

## Managed graphs

| Lab mode | Managed resources | Runtime composition |
|---|---:|---|
| SSM-only, local explanation stub | 13 | six core containers |
| SSM-only + Bedrock | 14 | core + Bedrock capability broker |
| HTTPS private-origin preview, local explanation stub | 23 | core + private subnet/NAT + CloudFront |
| HTTPS private-origin preview + Bedrock | 24 | core + private subnet/NAT + CloudFront + Bedrock broker |

OpenDART does not add a resource to this Terraform root. It consumes a separately
approved `terraform/serverless-opendart` runtime-stage deployment with exactly 11
managed resources, then adds one OpenDART capability-broker container at runtime.

The base lab is one `t3.small` Amazon Linux host in `ap-northeast-2`, encrypted
`gp3`, IMDSv2-required, standard T3 credits, no inbound security-group rules, SSM
management, and a bounded automatic stop. Its public address is used for outbound
bootstrap only and is not exposed as an output. The optional HTTPS path moves the
instance to a private subnet with no public address and adds short-lived NAT egress,
CloudFront, a VPC Origin, a viewer-request cookie gate, and TCP/3000 ingress only
from the service-managed `CloudFront-VPCOrigins-Service-SG`. It is a shared
demonstration cookie, not per-user authentication, tenant isolation, or production
authorization.

`auto_stop_minutes` is a requested configuration value, not an observed timer value
for an already-created host. This root intentionally ignores later `user_data` changes
to preserve a healthy short-lived host. Changing the timeout therefore requires a
separately reviewed destroy/recreate if the existing host must receive the new timer.

## Provider capability brokers

Bedrock and OpenDART are independently default-off. Each requires its own exact
acknowledgement. Application containers run as fixed non-root UIDs, receive no AWS
credential environment variables, have EC2 metadata disabled, and can reach only
their own Unix-domain socket. A fixed-UID broker checks `SO_PEERCRED` and exposes
only reviewed operations; it publishes no TCP port, receives no Docker socket, and
never returns AWS credentials.

This is process separation, not IAM isolation. Both optional brokers obtain the
same EC2 instance-role credentials to minimize the one-host lab cost. Compromise of
either broker could therefore reach every permission on that role. A later
production design needs separate compute roles or another workload-identity
boundary; this lab must not be described as production credential isolation.

Bedrock is restricted to `bedrock:InvokeModel` for the reviewed APAC Amazon Nova
Lite profile/foundation model and generates explanation text only. It does not
change deterministic scores or ranking. OpenDART is restricted to queue dispatch
and result-table reads/deletes for the names recovered from the separately approved
serverless state; OpenDART facts retain `score_effect=NONE`.

## Guarded deployment

The wrapper runs static/source checks, Terraform validation, a saved plan, exact
13/14/23/24 plan allowlisting, saved-plan apply when `-Apply` is present, runtime
upload through SSM, and remote smoke/boundary checks. It rejects delete or replace
actions. Provider installation is locked to the reviewed dependency lockfile.
Plan-only mode creates and retains one binary plan plus its checked JSON, then prints
three values: the provider-account digest, exact binary-plan digest, and a normalized
JSON-projection digest that excludes only Terraform's top-level volatile `timestamp`.
The JSON projection is not claimed to be formally canonical JSON; the exact binary
digest is authoritative for apply identity.

A later `-Apply` invocation does not re-plan. It read-locks those retained artifacts,
requires all three reviewed digests through `-ProviderAccountSha256`,
`-ReviewedSavedPlanSha256`, and `-ReviewedPlanSemanticSha256`, checks that Terraform-
bearing runtime flags and acknowledgements match the reviewed plan, and rechecks the
provider account before and after applying that exact binary. A same-session named
mutex plus an exclusive same-worktree file lock serializes create/destroy plan use.
Immediately before apply, the stable artifacts are moved to a GUID operation path and
a non-secret durable consumption marker is created. Successful apply/account recheck
removes the operation artifacts and marker. A crash, partial move, failed apply, or
cleanup failure leaves the marker and any operation artifacts in place; every later
plan/apply/destroy invocation then stops for human state inspection and cleanup
disposition. The lock does not coordinate copied worktrees or another host. Omit
`-Apply` for plan-only review.

The durable marker covers plan consumption through Terraform apply, provider-account
recheck, and operation-artifact cleanup. It is cleared before runtime upload/remote
checks and, on destroy, before the post-destroy state inventory. A failure in either
later verification phase therefore does not leave this consumption marker; the wrapper's
separate fail-safe stop, nonzero exit, and state inspection path remain the signals.

```powershell
.\terraform\lab\provisioning\deploy-lab.ps1 `
  -ActivationAcknowledgement JCAREER_SYNTHETIC_LAB_APPROVED
```

After reviewing the retained local binary plan and JSON, re-run the same mode with
all three printed digests:

```powershell
.\terraform\lab\provisioning\deploy-lab.ps1 `
  -ActivationAcknowledgement JCAREER_SYNTHETIC_LAB_APPROVED `
  -ProviderAccountSha256 <reviewed-plan-only-account-sha256> `
  -ReviewedSavedPlanSha256 <reviewed-exact-binary-plan-sha256> `
  -ReviewedPlanSemanticSha256 <reviewed-timestamp-free-plan-sha256> `
  -Apply
```

An approved HTTPS + Bedrock run adds these switches. The operator must retain the
same HTTPS bootstrap token as a `SecureString` across plan-only review and apply;
otherwise the semantic plan digest changes and apply is refused. The secret can later
be delivered once through an approved Windows RDP clipboard session. It is never
passed to Terraform in plaintext, written to the endpoint, or sent through SSM. A
successful HTTPS run prints only the token SHA-256 for the separate endpoint-session
approval; the edge gate does not accept that digest as a bearer value. The wrapper
rejects fewer than eight distinct hex symbols and repeated periods up to 32 characters,
but this heuristic does not prove randomness. The operator must source the 256-bit
token from an approved CSPRNG or password manager and retain it outside repository files.

```powershell
$previewBootstrap = Read-Host 'Approved 64-character preview token' -AsSecureString
.\terraform\lab\provisioning\deploy-lab.ps1 `
  -ActivationAcknowledgement JCAREER_SYNTHETIC_LAB_APPROVED `
  -EnableAwsHttpsPreview `
  -HttpsPreviewAcknowledgement JCAREER_SYNTHETIC_HTTPS_PREVIEW_APPROVED `
  -HttpsPreviewBootstrapToken $previewBootstrap `
  -EnableBedrockLive `
  -BedrockAcknowledgement JCAREER_SYNTHETIC_BEDROCK_APPROVED

# After reviewing the retained plan, reuse the same SecureString and all three digests.
.\terraform\lab\provisioning\deploy-lab.ps1 `
  -ActivationAcknowledgement JCAREER_SYNTHETIC_LAB_APPROVED `
  -EnableAwsHttpsPreview `
  -HttpsPreviewAcknowledgement JCAREER_SYNTHETIC_HTTPS_PREVIEW_APPROVED `
  -HttpsPreviewBootstrapToken $previewBootstrap `
  -EnableBedrockLive `
  -BedrockAcknowledgement JCAREER_SYNTHETIC_BEDROCK_APPROVED `
  -ProviderAccountSha256 <reviewed-plan-only-account-sha256> `
  -ReviewedSavedPlanSha256 <reviewed-exact-binary-plan-sha256> `
  -ReviewedPlanSemanticSha256 <reviewed-timestamp-free-plan-sha256> `
  -Apply -OpenPreview
```

### Clean-state OpenDART staging

An OpenDART-linked lab cannot be the first apply from two empty states. The
serverless runtime policy must name the lab role, while the lab's linked apply
requires the already completed serverless apply receipt. Use three separately
reviewed stages; none of the acknowledgement strings creates an approval by
itself.

1. **Stage A — create the final-shaped lab with OpenDART off.** Plan, review, and
   apply `terraform/lab` without `-EnableOpenDartLive`. Choose the final HTTPS shape in Stage A,
   and choose the intended Bedrock mode there as well. Adding
   HTTPS later changes the instance subnet/public-address placement and can
   require a replacement, which this wrapper rejects. Enabling Bedrock later can add
   the conditional policy, but disabling an already enabled Bedrock mode deletes that
   policy and the same wrapper rejects the deletion; keep the reviewed Stage A mode
   stable through this sequence. Complete the core/provider remote smoke. A successful
   apply emits `runtime_role_name=<non-secret-role-name>`; copy only that bounded value
   into Stage B's `api_sender_role_name` input.
2. **Stage B — create OpenDART against the existing lab role.** With the encrypted
   root-specific backend, use the generic approved-Terraform wrapper for an exact
   eight-address bootstrap plan/apply. Build, scan, and push the worker only through
   the repository's separately acknowledged `Prepare` → fact-binding `Review` → human
   scan disposition → single-use `Publish` path. Pin the returned ECR digest, then
   create and review the exact eleven-address runtime plan with the Stage A role name.
   Apply that saved plan and retain its redacted apply receipt. A local Prepare run built
   and scanned the worker image, recorded six vulnerability occurrences, and stopped at
   `AWAITING_HUMAN_SCAN_DISPOSITION`. No human disposition, push, runtime apply, or
   OpenDART call has been recorded.
3. **Stage C — link and redeploy the same lab with OpenDART on.** Re-plan the
   existing lab with `-EnableOpenDartLive`, the exact acknowledgement, backend, and
   Stage B receipt. Review the new saved-plan digests, apply that exact plan, and
   let the runtime wrapper verify the backend hash, eleven-address state, Lambda
   image digest, account-free outputs, and exact sender-policy role before starting
   the Unix-socket broker. The optional public-API smoke remains a separate call
   decision.

For teardown, reverse the dependency. Disable the lab broker first with a reviewed
OpenDART-off lab plan, remove the OpenDART root before destroying the lab role, and
destroy the lab last. Each destructive plan uses its own approval and inventory
check; stopping the instance is not teardown.

The command skeleton below fixes the plan/apply pairing and var-file handoff. Angle-
bracket values are operator-owned paths or reviewed digests, not shell-ready defaults.
Do not place the API key value, account ID, bootstrap token, or credentials in a var
file. Every apply consumes the saved plan from the immediately preceding plan-only run.

```powershell
# Stage A plan-only, then apply the same final HTTPS/Bedrock shape with its three digests.
.\terraform\lab\provisioning\deploy-lab.ps1 `
  -ActivationAcknowledgement JCAREER_SYNTHETIC_LAB_APPROVED `
  <same-final-shape-switches>
.\terraform\lab\provisioning\deploy-lab.ps1 `
  -ActivationAcknowledgement JCAREER_SYNTHETIC_LAB_APPROVED `
  <same-final-shape-switches> `
  -ProviderAccountSha256 <reviewed-account-sha256> `
  -ReviewedSavedPlanSha256 <reviewed-binary-plan-sha256> `
  -ReviewedPlanSemanticSha256 <reviewed-plan-json-sha256> `
  -Apply

# Stage B1 bootstrap: var file uses deployment_stage=bootstrap and the Stage A role output.
.\scripts\Invoke-ApprovedTerraform.ps1 -Root serverless-opendart `
  -BackendConfig <private-backend-config> -VarFile <bootstrap-var-file>
.\scripts\Invoke-ApprovedTerraform.ps1 -Root serverless-opendart `
  -BackendConfig <same-private-backend-config> -Apply -ApprovalFile <bootstrap-approval-record>

# Stage B publisher step 1: build and scan a protected source snapshot; no push.
.\scripts\Invoke-ApprovedOpenDartWorkerPublish.ps1 -Mode Prepare `
  -OperationRef <PUBLISH-UNIQUE_OPERATION_REF> -SourceRevision <40-or-64-lowercase-hex> `
  -ImageTag <unique-lowercase-image-tag> -PreparationReceipt <new-private-preparation-receipt> `
  -ScanReport <new-private-scan-report> -ScanPolicyFile <reviewed-scan-policy> `
  -PreparationAcknowledgement JCAREER_SYNTHETIC_OPENDART_SCAN_PREPARATION

# Step 2: capture factual account/backend/state/repository bindings into a pending draft; no push.
.\scripts\Invoke-ApprovedOpenDartWorkerPublish.ps1 -Mode Review `
  -OperationRef <same-operation-ref> -SourceRevision <same-source-revision> `
  -ImageTag <same-image-tag> -PreparationReceipt <same-preparation-receipt> `
  -ScanReport <same-scan-report> -ScanPolicyFile <same-scan-policy> `
  -BackendConfig <same-private-backend-config> -BootstrapApplyReceipt <bootstrap-apply-receipt> `
  -ApprovalDraft <new-private-pending-draft> `
  -ReviewAcknowledgement JCAREER_SYNTHETIC_OPENDART_PUBLISH_BINDINGS_REVIEW

# A person reviews the scan and bindings and creates a separate, <=24-hour single-publish approval.
# Step 3 is the first path that can log in to ECR or push an image.
.\scripts\Invoke-ApprovedOpenDartWorkerPublish.ps1 -Mode Publish `
  -OperationRef <same-operation-ref> -SourceRevision <same-source-revision> `
  -ImageTag <same-image-tag> -PreparationReceipt <same-preparation-receipt> `
  -ScanReport <same-scan-report> -ScanPolicyFile <same-scan-policy> `
  -BackendConfig <same-private-backend-config> -BootstrapApplyReceipt <bootstrap-apply-receipt> `
  -ApprovalFile <separate-human-approved-publish-record> `
  -PrivateImageUriPath <new-private-digest-pinned-uri-file> `
  -PublishReceipt <new-redacted-publish-receipt>

# Stage B2 runtime, only after the separately approved publisher returns a digest-pinned URI.
.\scripts\Invoke-ApprovedTerraform.ps1 -Root serverless-opendart `
  -BackendConfig <same-private-backend-config> -VarFile <runtime-var-file>
.\scripts\Invoke-ApprovedTerraform.ps1 -Root serverless-opendart `
  -BackendConfig <same-private-backend-config> -Apply -ApprovalFile <runtime-approval-record> `
  -ArtifactSha256 <64-hex-ECR-image-digest-without-sha256-prefix>

# Stage C plan-only, then consume the same reviewed lab plan.
.\terraform\lab\provisioning\deploy-lab.ps1 `
  -ActivationAcknowledgement JCAREER_SYNTHETIC_LAB_APPROVED `
  <same-final-shape-switches> `
  -EnableOpenDartLive `
  -OpenDartAcknowledgement JCAREER_SYNTHETIC_OPENDART_LIVE_APPROVED `
  -OpenDartBackendConfig <same-private-backend-config> `
  -OpenDartApplyReceipt <redacted-runtime-apply-receipt>
.\terraform\lab\provisioning\deploy-lab.ps1 `
  -ActivationAcknowledgement JCAREER_SYNTHETIC_LAB_APPROVED `
  <same-final-shape-switches> `
  -EnableOpenDartLive `
  -OpenDartAcknowledgement JCAREER_SYNTHETIC_OPENDART_LIVE_APPROVED `
  -OpenDartBackendConfig <same-private-backend-config> `
  -OpenDartApplyReceipt <redacted-runtime-apply-receipt> `
  -ProviderAccountSha256 <reviewed-account-sha256> `
  -ReviewedSavedPlanSha256 <reviewed-binary-plan-sha256> `
  -ReviewedPlanSemanticSha256 <reviewed-plan-json-sha256> `
  -Apply
```

The following is only the Stage C shape after Stages A and B have produced the
reviewed inputs:

```powershell
.\terraform\lab\provisioning\deploy-lab.ps1 `
  -ActivationAcknowledgement JCAREER_SYNTHETIC_LAB_APPROVED `
  -EnableOpenDartLive `
  -OpenDartAcknowledgement JCAREER_SYNTHETIC_OPENDART_LIVE_APPROVED `
  -OpenDartBackendConfig <private-backend-config> `
  -OpenDartApplyReceipt <redacted-apply-receipt> `
  -ProviderAccountSha256 <reviewed-plan-only-account-sha256> `
  -ReviewedSavedPlanSha256 <reviewed-exact-binary-plan-sha256> `
  -ReviewedPlanSemanticSha256 <reviewed-timestamp-free-plan-sha256> `
  -Apply
```

`-RunOpenDartLiveSmoke` is a separate, deliberate real public-API observation. It
also requires `-OpenDartCallAcknowledgement JCAREER_SYNTHETIC_ONLY`, one operator-
supplied public company code, and its exact public name. The smoke records only a
PASS marker and a truncated content hash, not the retrieved facts. This post-apply
observation, `-OpenPreview`, and the supplied OpenDART backend/receipt paths are not
Terraform plan variables, so their separate acknowledgements and receipt validation
remain the applicable boundary; the binary plan digest does not approve those actions.

The lab root still uses ignored local Terraform state. Its activation phrase plus
saved-plan checks are not a separately signed, plan-bound approval record. That is
a deployment-governance limitation for a human to accept or close before any run.
The three isolated roots (OpenDART, image definitions, endpoints) use supplied S3
backends and exact-plan approval files.

## Consultant access and endpoint boundary

Private mode is reached through an SSM port forward to instance loopback. HTTPS
preview mode exposes only the clean CloudFront URL after the short-lived bootstrap
cookie flow. `/agent` and `/llm` remain unavailable from the web entrypoint.
The clean URL alone returns 403. A Windows consultant session therefore needs its
own session approval containing only the bootstrap-token SHA-256; the operator
supplies the secret separately as a `SecureString` for one-time clipboard delivery.
This remains a shared demo cookie, not production authentication.

This root does not create three Windows PCs, three Macs. Windows image definitions
and three Windows Server desktop-simulation endpoints are separate default-off,
approved Terraform roots. macOS remains a physical-Mac/MDM source contract because
EC2 Mac licensing, Dedicated Host cost, region capacity, identity, and remote access
require human decisions. Do not infer six deployed or usable devices without their
separate receipts and human GUI observations.

## Cleanup

Use only the fail-closed wrapper. It accepts the exact 13/14 SSM-only graphs and
23/24 private-origin HTTPS-preview graphs. If an interrupted apply leaves a non-empty
subset, recovery accepts only addresses from that same reviewed union. In both cases
it applies only a saved delete-only plan whose addresses exactly match the observed
state, and checks the post-destroy state inventory. Stopping EC2 is not cleanup. In
HTTPS mode the NAT gateway and its public address continue billing after EC2 stops;
the approved destroy path is required to remove them. A post-apply runtime, provider,
or HTTPS-boundary failure requests a stop only for the tag/type/profile-validated EC2
target and still leaves destructive cleanup to this separately acknowledged wrapper.
For a non-empty state, plan-only retains the exact destroy plan and prints the provider-
account, binary-plan, and normalized JSON-projection digests. The apply run does not
re-plan and refuses to delete unless all three reviewed values match. The artifacts
move behind the same durable consumption marker before apply. A failed or interrupted
consumption blocks every later lab wrapper until a person inspects state and explicitly
disposes of the marker/artifacts; they are not auto-deleted as success evidence. An
already-empty state performs no delete and requires only the provider-account digest;
it has no binary or JSON plan to approve.

```powershell
.\terraform\lab\provisioning\destroy-lab.ps1 `
  -DestroyAcknowledgement JCAREER_SYNTHETIC_LAB_DESTROY_APPROVED `
  -ProviderAccountSha256 <reviewed-destroy-plan-account-sha256> `
  -ReviewedSavedPlanSha256 <reviewed-exact-destroy-plan-sha256> `
  -ReviewedPlanSemanticSha256 <reviewed-timestamp-free-destroy-plan-sha256> `
  -Apply
```

The wrapper does not prove that resources outside its state are absent. Historical
ignored plans, cache, state backups, or locks require a separate human retention
decision. `.github/**` remains human-owned; no repository workflow is represented
as an approved deployment button.
