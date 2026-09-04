# JCareer TO-BE AI security Terraform proposal

> **PROPOSED / NOT DEPLOYED / HUMAN REVIEW PENDING**

This directory is a read-only-safe Terraform design proposal. Its default
configuration is `enable = false`, every module-level AWS resource is gated,
and no backend, account identifier, credential, secret, live URL, current-state
lookup, import, or deployment receipt is included. Nothing in this directory is
evidence that a control exists or works in AWS.

This is intentionally **not** the approval-gated
`jcareer-worktrees/terraform-tobe/terraform/tobe` implementation root. It does
not satisfy or bypass that root's P0 authority gate. It provides reviewable HCL
for a possible later, release-scoped handoff.

## Architecture boundary

The repository-supported current path remains the narrow serverless slice:

`CloudFront/private S3 -> API Gateway/Cognito -> API Lambda -> SQS -> Agent -> LLM Gateway -> Capability Broker -> exact Bedrock model -> DynamoDB/evidence S3`

This proposal does not replace that path, import its state, create the
enterprise ECS/RDS/Redis topology, or claim a custom domain, Evidence Desk,
MLOps runtime, endpoint fleet, or customer production estate.

The proposal responds to the assessment snapshot's human-review-pending
findings without upgrading them to remediation-complete status:

| Module | Proposed control delta | Finding/control trace | What it does not prove |
|---|---|---|---|
| `modules/edge` | CloudFront-scope WAF, source-IP rate rule, AWS managed rule group in `COUNT`, bounded/redacted block logging; exact owner-stack handoff plus optional post-change live read-back | `NF-06`, plus `NF-05` delivery boundary; `T.6.1`, `T.6.2` | It does not import or mutate the existing distribution. Until its owner sets `web_acl_id` and the second-pass verification succeeds, association remains open |
| `modules/bedrock-boundary` | Retained versioned Bedrock guardrail; exact reviewed model/profile ARN set for the Broker; Gateway permission to invoke one numeric published Broker Lambda version; direct-Bedrock deny on the Gateway | `NF-03`, `NF-05`, `NF-04`; `T.1.1`-`T.1.3`, `T.3.1`-`T.3.3` | No semantic-output safety, IAM simulation result, model approval, final-score authority, or live invocation |
| `modules/metadata-observability` | KMS-encrypted role-separated metadata log groups, S3 prefixes, and DynamoDB leading-key partitions; private Object-Locked evidence S3 and PITR DynamoDB; separate KMS-encrypted CloudTrail bucket, selected S3/DynamoDB data events, CloudWatch delivery and guardrail-block alarm | `NF-02`, `NF-04`, `NF-06`; `T.2.1`-`T.2.3`, `T.7.1`, `T.7.2`, `T.8.1`, `T.8.2` | No content inspection, Evidence Desk, tenant authorization, legal-hold decision, deletion propagation, alarm response ownership, or runtime evidence |

Every taggable proposed resource carries `jk_layer=tobe`, `control_id`,
`gap_id`, and `evidence_id`. Values beginning `EXPECTED-` are trace targets,
not observed evidence. Required tags override optional tags. Disabled source
and outputs retain `PROPOSED_NOT_DEPLOYED`; resources that an authorized apply
would create are tagged `status=PROPOSED_CONTROL_NOT_VERIFIED`. That status
means a control object exists but its binding, request contract, negative tests,
and operating effectiveness remain unverified.

## Safety and ownership choices

- The master `enable` switch and all component switches default to `false`.
- Changing `enable` is insufficient. A pseudonymous plan-bound approval
  reference and the exact human acknowledgement are also required.
- CloudFront WAF is created through a `us-east-1` provider alias. AWS and the
  Terraform provider require CloudFront association through the owning
  distribution's `web_acl_id`; `aws_wafv2_web_acl_association` must not be used.
  This root therefore emits the exact ACL ARN and a digest of the distribution
  ID, while a separately reviewed owner stack performs the change. A second
  plan with `verify_cloudfront_binding=true` reads CloudFront and fails unless
  the distribution is `Deployed` and its `web_acl_id` equals that ACL ARN.
- The WAF rate rule is keyed by source IP. Authenticated subject/tenant quota,
  token budget, SQS backpressure, and cost cut-off belong in the application
  plane and remain required gates.
- The common managed rule set begins in `COUNT`. A reviewed false-positive
  baseline is required before any rule is changed to block.
- WAF logs retain only `BLOCK`/`COUNT` actions and redact authorization,
  cookies, query strings, and paths. Source IP is still security telemetry and
  needs privacy-owner approval.
- An enabled plan accepts one reviewed model/profile ID plus an exact set of
  1..8 Bedrock resource ARNs. Cross-region inference can require both an
  inference-profile ARN and every destination foundation-model ARN, so the ID
  and ARN set are separate inputs. At least one invocation ARN must end in the
  exact model/profile ID, preventing an unrelated target from being paired with
  the label. They are approved only as one unit: model ID, sorted ARN set,
  numeric published Broker Lambda version ARN and its base64 CodeSha256,
  Broker/Gateway role names, ARNs, unique IDs, and request region are JSON-
  encoded and SHA-256-bound to
  `bedrock_approval_binding_sha256`. A mismatched set fails the plan gate.
- The Gateway receives only `lambda:InvokeFunction` for the exact Broker ARN
  from this module and an explicit deny on all direct Bedrock invocation. The
  ARN must end in a numeric published version; aliases, `$LATEST`, and an
  unqualified function are rejected. An enabled plan reads that version and
  fails unless its qualified ARN, version, and CodeSha256 match the approval.
  The two IAM role names are also read back and must match their approval-bound
  ARN and unique ID, detecting same-name role replacement before attachment.
  These are point-in-time plan gates, not apply or operating-effectiveness
  evidence. The Broker receives the exact reviewed Bedrock resource set and
  guardrail only. The model remains qualitative-only: it cannot own the final
  score, ranking, hire/reject action, or automatic promotion.
- Every Bedrock guardrail version sets `skip_destroy=true`, preserving versions
  referenced by approval and evidence records. A retained version is only a
  rollback candidate; selecting or retiring one requires its own reviewed plan,
  evaluation evidence, and record update. This module does not auto-roll back.
- Guardrails are defense in depth. Field allowlisting, Korean PII detection,
  bounded structured output, deterministic backend scoring, safe browser
  rendering, and human decision authority remain application responsibilities.
- The `PROMPT_ATTACK` filter is not completed by Terraform or IAM. For
  `InvokeModel` and `InvokeModelWithResponseStream`, the Capability Broker must
  serialize every untrusted prompt segment with the Amazon Bedrock
  guard-content input-tag contract and send the approval-bound guardrail ID and
  version. The application must reject missing/malformed tags before Bedrock.
  A live gate must prove that a tagged injection is blocked, benign tagged
  content passes, missing/malformed tags fail closed, and neither raw prompt nor
  response is retained. HCL can neither inspect the request body nor prove that
  this runtime contract is used.
- The evidence bucket accepts only KMS-headered uploads asserting the
  `jk-data-class=metadata-only` object tag. A tag does not inspect content; the
  publisher must enforce the field allowlist and a residual-content test.
- Gateway and Broker publishers do not share a write policy: each can write
  only its own CloudWatch log group, `records/<channel>/` S3 prefix, and
  `<channel>#` DynamoDB partition-key prefix. `dynamodb:LeadingKeys` constrains
  the partition key but cannot validate the remaining item schema or tenant
  ownership, which stay application and negative-test responsibilities.
- Object Lock `COMPLIANCE` mode is intentionally costly to reverse. Retention,
  privacy deletion, legal/backup hold, and purge ownership must be reconciled
  before an approved plan. This store is not the separately deployed Evidence
  Desk described in the architecture backlog.
- The shared KMS key has `prevent_destroy=true` because Object-Locked evidence,
  the audit bucket, metadata/audit logs, and DynamoDB ciphertext depend on it.
  Key retirement requires a separate approved change: inventory every consumer
  and maximum retention, preserve decrypt access through that period, migrate
  or re-encrypt each decryptable copy, switch and verify CloudTrail/log/store
  writers, prove historical reads and digest validation, and only then review
  key disable/deletion. Removing the key guard in a component-disable rollout
  is prohibited.
- DynamoDB TTL is eventual deletion, not a deletion SLA. The runtime must
  verify expiry across the index, S3 versions, logs, caches, and any exports.
- CloudTrail management events and evidence S3/DynamoDB data events are sent to
  a separate audit bucket and KMS-encrypted CloudWatch log group. The separate
  bucket is intentional: CloudTrail does not provide the application evidence
  object's required `jk-data-class=metadata-only` tag. Because the audit bucket
  enables S3 Bucket Keys, the CloudTrail service grant contains `Decrypt`,
  `GenerateDataKey*`, and `DescribeKey`; both `aws:SourceArn` and the CloudTrail
  encryption context are pinned to the exact proposed trail ARN. Log delivery,
  alarm routing, event completeness, and response remain live verification
  gates.

## Metadata-only contract

Allowed application log/evidence fields are exposed as the
`permitted_metadata_fields` output: correlation/event identifiers, timestamps,
schema/policy versions, status, latency/size counters, a model-ID digest, a
tenant-reference digest, and guardrail action. The following are prohibited:

- raw or reconstructable prompts and model responses;
- applicant/customer fields, resumes, names, contacts, free text, or direct
  tenant/user identifiers;
- credentials, tokens, session material, cookies, authorization headers, or
  provider payloads;
- final hiring decisions represented as model-authored facts.

Terraform can create retention and storage boundaries; it cannot prove that a
producer obeys this content contract.

## Validation and activation gates

`VALIDATION.md` records provider-free source checks and schema/mock validation
performed with Terraform 1.15.9 and an already-present local AWS provider
6.59.0 mirror. Local preparation performed `terraform init -backend=false`,
`validate`, and `test` without a provider download. It did not use AWS
credentials or APIs, a backend/state, plan/apply, role attachment, model call,
or CloudFront read-back. The repository CI copies this root into a runner-temp
directory and reruns `init`, `validate`, and `test` there without AWS
credentials; its clean Ubuntu runner may download the pinned provider from the
Terraform registry, but it still performs no AWS API call or apply and leaves
no generated provider artifacts in the public source checkout. A Windows-only
lock generated from the offline local mirror is not
committed because its incomplete checksum set would break Linux CI. Instead,
all root/child modules pin AWS provider `6.59.0`, and CI checks the transient
registry-generated lock selection and checksum immediately after clean init.
This is source-validation continuity only: actual plan/apply is blocked until a
reviewed, committed multi-platform lock contains registry checksums for every
release runner. It must never commit a single-platform local-mirror lock. A
future authorized handoff must pass the gates in order:

1. **Authority:** approve the control assessment and remediation fields; select
   one production destination; record owner, retention/privacy decision,
   budget/quota, region/model, exact role names, approval time, rollback, and a
   dedicated Phase 2 handoff.
2. **Static validation:** in a clean, isolated checkout run formatting and the
   provider-free contract test, then `terraform init -backend=false`,
   `terraform validate`, and mock-provider `terraform test` using the pinned
   tool/provider versions. Provider installation is a CI dependency, not an
   AWS deployment or runtime check. Static PASS is source evidence only.
3. **Plan safety:** CI/OIDC plan only; separate state key; no AS-IS import,
   deletion, or type change; expected component-only creates; all required tags;
   no wildcard model allow; no resource association outside approved scope.
4. **Edge verification:** association observed from the owner stack; HTTPS/auth
   regression; rate threshold and recovery; managed-rule false positives;
   redaction review; per-subject/tenant quota, queue backpressure, and cost alarm
   positive/negative tests.
5. **AI boundary verification:** Broker correct-model/guardrail positive test;
   wrong model, unversioned guardrail, and direct Gateway calls denied; input
   allowlist and injection regression; every untrusted `InvokeModel`/stream
   prompt segment uses the Bedrock guard-content input tag; missing/malformed
   tags fail closed; Korean PII residual test; structured output and browser
   execution/external-load zero tests; backend retains final score authority.
6. **Metadata/evidence verification:** prohibited seed strings absent from logs,
   S3, DynamoDB, and exported receipts; TLS/public/wrong-key/wrong-tag requests
   denied; version/lock/PITR/deletion protection observed; expiry/deletion tested
   across every copy; alarm and incident owner exercises completed.
7. **Release integrity:** distinct-human approval of the saved plan, immutable
   source/input/archive/backend digests, apply of that same plan only, scoped
   smoke and rollback, redacted evidence, residual/cost check, and pipeline
   re-lock. Actual plan/apply remains blocked until a reviewed, committed
   multi-platform provider lock carries registry checksums for every release
   runner. The transient CI lock check validates source only. Each independent
   release keeps its own status and receipts.

An output value, state entry, diagram, static scan, or old smoke result must
never be narrated as current deployment or control-effectiveness evidence.

## Review-only example

The committed defaults intentionally need no values:

```hcl
enable                      = false
enable_edge                 = false
enable_bedrock_boundary     = false
enable_observability        = false
activation_acknowledgement  = "PROPOSED_NOT_DEPLOYED"
approval_ref                = ""
cloudfront_distribution_id  = ""
cloudfront_owner_binding_ref = ""
verify_cloudfront_binding   = false
exact_model_id              = ""
bedrock_invocation_resource_arns = []
broker_function_arn         = ""
broker_code_sha256          = ""
bedrock_approval_binding_sha256 = ""
broker_role_name            = ""
broker_role_arn             = ""
broker_role_unique_id       = ""
gateway_role_name           = ""
gateway_role_arn            = ""
gateway_role_unique_id      = ""
```

Do not commit a future approved variable file. Keep environment identifiers and
approval records in the authorized release system, and never put secrets in
Terraform variables or state.

## Sources used for this proposal

- `artifacts/workstreams/architecture_truth_and_tobe.md` (2026-09-01
  repository-supported cutoff and closed-until-approved backlog)
- `jcareer-public-spec/assessment-dashboard/assessment-snapshot.js`
  (`WORKING_DRAFT_HUMAN_REVIEW_PENDING`, `PROPOSED_NOT_VERIFIED`)
- existing default-off Terraform style under
  `jcareer-public-spec/terraform/serverless-*`
- [`EVIDENCE_MAP.md`](EVIDENCE_MAP.md), which separates source assertions,
  expected evidence, live tests, and claims that remain prohibited

The sources are architecture and assessment inputs, not deployment approval.
