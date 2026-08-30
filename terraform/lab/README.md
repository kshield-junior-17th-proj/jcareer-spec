# J-Career synthetic AWS lab

This directory is the only Terraform apply surface for the runtime preview. It does not deploy
`terraform/asis`, does not represent the client or production service, and may contain synthetic
fixtures only.

**Default boundary:** AWS use remains disabled until a person supplies the exact activation
acknowledgement under `TASK-101`. The lab is not a client or production environment.

## Guardrails

- Region is fixed to `ap-northeast-2`.
- Exactly one `t3.small` EC2 instance is allowed. `t3.micro` is not claimed as a viable host for
  the six-container runtime.
- T3 CPU credits use `standard`; detailed monitoring is disabled.
- Root storage is encrypted `gp3`, deleted with the instance, at most 30 GiB and 3,000 IOPS.
- The security group has no inbound rules. SSH and public port 3000 are not opened.
- IMDSv2 with hop limit 1 is required, metadata tags/IPv6 are disabled, and the instance is managed
  through SSM.
- Operator browser access uses an SSM local port-forwarding session to instance loopback.
- The bootstrap failure trap is armed before the timer unit files are written. After user-data starts,
  timer installation or later bootstrap failure requests a direct shutdown fallback; the OS timer
  stops the instance after 240 minutes by default. There is no out-of-band TTL if user-data never starts.
- `/agent` and `/llm` are not exposed through the web entrypoint.
- The runtime is bounded by per-service memory ceilings and a 2 GiB swap file on the encrypted root
  volume. Deployment rejects hosts with less than 1.8 GiB RAM or 8 GiB free root space.
- The deployment uses the local synthetic explanation stub. Bedrock live is currently blocked even
  with acknowledgements: AWS documents that IMDSv2 hop 1 can prevent container credentials, while
  raising it to 2 without container isolation would broaden instance-role exposure.
- The runtime creates two logical PostgreSQL databases and roles on one host. This is not physical
  database isolation and cross-database writes are not atomic.
- The VPC resource has an activation precondition, but this is not evidence that every targeted Terraform
  graph is gated. `-target` is not an approved lab workflow.

The budget object has no notification recipient and is an observation control, not a hard spending
cap. Stop-on-failure, the auto-stop timer, and `terraform destroy` are the cost controls. A person
must still verify teardown from the reviewed state.

## One-command guarded deployment

From the repository root, this single command runs the source tests, Terraform initialization and
validation, saved plan, cost/exposure allowlist, saved-plan apply, SSM runtime upload, and remote smoke
checks. It rejects plans containing deletion or replacement actions. It never enables Bedrock live,
opens inbound access, or prints the AWS account ID.

```powershell
.\terraform\lab\provisioning\deploy-lab.ps1 `
  -ActivationAcknowledgement JCAREER_SYNTHETIC_LAB_APPROVED `
  -Apply
```

Omit `-Apply` to create and inspect the guarded plan without changing AWS resources. The plan and
state stay under ignored local Terraform paths and must not be committed. This is a one-command
operator workflow, not a GitHub Actions deployment button; `.github/**` remains human-owned.

## Stage 1: infrastructure

After explicit human authorization, set the activation acknowledgement, then run `fmt`, `validate`,
a saved plan, the static lab checker, and `scripts/check_lab_budget.py` before any apply.
Do not use `-target`. The protected general CI currently attempts a lab plan without the acknowledgement
and without installing the exact Terraform version required here, so it is not a usable lab activation
path. Changing that protected workflow requires its owner; the acknowledgement must not be auto-injected
to simulate human approval.

```powershell
$env:TF_VAR_activation_acknowledgement = 'JCAREER_SYNTHETIC_LAB_APPROVED'
$env:TF_VAR_enable_bedrock_live = 'false'
python scripts/check_lab_static.py
terraform -chdir=terraform/lab init
terraform -chdir=terraform/lab validate
terraform -chdir=terraform/lab plan -out=.terraform/tfplan-lab
terraform -chdir=terraform/lab show -json .terraform/tfplan-lab > terraform/lab/.terraform/plan.json
python scripts/check_lab_budget.py --plan terraform/lab/.terraform/plan.json
terraform -chdir=terraform/lab apply .terraform/tfplan-lab
```

Do not commit the local state or plan artifacts.

The static checker also inventories ignored artifacts without printing their stored values. At the
time of this source-only review, a historical state backup, saved plans, a stale lock, and a large
provider cache remained locally. A person must approve retention or disposal; an empty current
state alone does not establish that no AWS resources exist.

## Stage 2: runtime

The deployment script first validates the target's lab tags, running state, instance type, instance
profile name against the instance `Name` tag, and Bedrock plan flag. It currently sends `src/runtime`
and the whole `terraform/lab/provisioning` directory—including lab scripts and tests, not only the proxy
configuration—through SSM. It verifies the transferred archive SHA-256 and does not clone Git or transfer
repository credentials. The session signing key is generated on the instance and does not enter Terraform
state.

The archive checksum detects transfer corruption. It does not prove that the worktree revision was
approved, and source chunks can remain in SSM command history subject to the account's retention
policy. Commit/tree provenance, immutable image digests, and SSM history retention remain activation
decisions.

```powershell
$instanceId = terraform -chdir=terraform/lab output -raw runtime_instance_id
& terraform/lab/provisioning/deploy-runtime.ps1 `
  -InstanceId $instanceId `
  -ActivationAcknowledgement JCAREER_SYNTHETIC_LAB_APPROVED
```

The default deployment builds six containers with the local synthetic explanation stub. It checks
candidate, recruiter, cross-company denial, administrator audit, internal route non-exposure, and
the logical member/company database roles. It does not call Bedrock. A failed deployment or check
requests a stop only after the target passed the exact tag/state/type/profile preflight.
The memory/disk guard and service limits are source contracts, not evidence that `t3.small` has
completed the build or sustained the workload; that requires a later approved observation.

Bedrock application code remains available for local contract tests, but this EC2/Compose lab does
not yet have an approved container-scoped credential delivery design. Both Terraform and the
deployment script fail closed if live Bedrock is requested. A person must choose and review a
credential boundary before that gate is changed. See the
[AWS container IMDS consideration](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instancedata-data-retrieval.html).

## Operator connection

Start an SSM local tunnel and keep that terminal open:

```powershell
aws ssm start-session `
  --region ap-northeast-2 `
  --target $instanceId `
  --document-name AWS-StartPortForwardingSession `
  --parameters '{"portNumber":["3000"],"localPortNumber":["3000"]}'
```

Then open `http://127.0.0.1:3000/jobs`. The web container binds to instance loopback; there is no
public runtime URL.

From a second local terminal, the same two-sided API smoke can exercise the operator tunnel without
probing internal container ports:

```powershell
python src/runtime/tests/lab_remote_smoke.py
```

The local tunnel URL is HTTP and is suitable only for the short-lived synthetic operator preview.
Do not enter real applicant, employee, or company data.

## Endpoint simulation boundary

This Terraform provisions one Amazon Linux application host. It does **not** provision or emulate
three Windows PCs, three Macs, employee identities, endpoint agents, or an office network. Browser
and endpoint coverage for those six client profiles needs a separately approved test method and
owned images. No Windows/macOS compatibility or endpoint-security observation can be inferred from
this lab.

## Cleanup

Stopping the instance does not delete chargeable storage, and restarting it starts a new auto-stop
window. When the preview is finished, destroy the lab and confirm the saved state reports no managed
resources.

```powershell
terraform -chdir=terraform/lab destroy
```
