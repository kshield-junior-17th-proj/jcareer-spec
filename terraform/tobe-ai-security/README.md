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
| `modules/edge` | CloudFront-scope WAF, source-IP rate rule, AWS managed rule group in `COUNT`, bounded/redacted block logging | `NF-06`, plus `NF-05` delivery boundary; `T.6.1`, `T.6.2` | No WAF association, per-user/tenant quota, load recovery, cost boundary, or live negative test |
| `modules/bedrock-boundary` | Versioned Bedrock guardrail, one exact foundation-model allow for the existing Broker role, explicit direct-Bedrock deny for the existing Gateway role | `NF-03`, `NF-05`, `NF-04`; `T.1.1`-`T.1.3`, `T.3.1`-`T.3.3` | No semantic-output safety, role provenance, IAM simulation result, model approval, final-score authority, or live invocation |
| `modules/metadata-observability` | Bounded application metadata log groups; private, versioned, KMS-encrypted, Object-Locked S3 evidence; PITR/deletion-protected/KMS DynamoDB index | `NF-02`, `NF-04`, `NF-06`; `T.2.1`-`T.2.3`, `T.7.1`, `T.7.2`, `T.8.1`, `T.8.2` | No content inspection, Evidence Desk, tenant authorization, publisher identity, legal-hold decision, deletion propagation, or runtime evidence |

Every taggable proposed resource carries `jk_layer=tobe`, `control_id`,
`gap_id`, and `evidence_id`. Values beginning `EXPECTED-` are trace targets,
not observed evidence. Required tags override optional tags.

## Safety and ownership choices

- The master `enable` switch and all component switches default to `false`.
- Changing `enable` is insufficient. A pseudonymous plan-bound approval
  reference and the exact human acknowledgement are also required.
- CloudFront WAF is created through a `us-east-1` provider alias, but this root
  deliberately does not mutate an existing distribution. A separately reviewed
  owner stack must consume the proposed ACL identifier.
- The WAF rate rule is keyed by source IP. Authenticated subject/tenant quota,
  token budget, SQS backpressure, and cost cut-off belong in the application
  plane and remain required gates.
- The common managed rule set begins in `COUNT`. A reviewed false-positive
  baseline is required before any rule is changed to block.
- WAF logs retain only `BLOCK`/`COUNT` actions and redact authorization,
  cookies, query strings, and paths. Source IP is still security telemetry and
  needs privacy-owner approval.
- An enabled plan resolves one reviewed foundation-model ID. The Broker policy
  allows that model only when the exact numeric guardrail version is supplied,
  denies all other models, and rejects wildcards and role reuse.
  The model remains qualitative-only: it cannot own the final score, ranking,
  hire/reject action, or automatic promotion.
- Guardrails are defense in depth. Field allowlisting, Korean PII detection,
  bounded structured output, deterministic backend scoring, safe browser
  rendering, and human decision authority remain application responsibilities.
- The evidence bucket accepts only KMS-headered uploads asserting the
  `jk-data-class=metadata-only` object tag. A tag does not inspect content; the
  publisher must enforce the field allowlist and a residual-content test.
- Object Lock `COMPLIANCE` mode is intentionally costly to reverse. Retention,
  privacy deletion, legal/backup hold, and purge ownership must be reconciled
  before an approved plan. This store is not the separately deployed Evidence
  Desk described in the architecture backlog.
- DynamoDB TTL is eventual deletion, not a deletion SLA. The runtime must
  verify expiry across the index, S3 versions, logs, caches, and any exports.

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

No command below was run while preparing this proposal. A future authorized
handoff must pass the gates in order:

1. **Authority:** approve the control assessment and remediation fields; select
   one production destination; record owner, retention/privacy decision,
   budget/quota, region/model, exact role names, approval time, rollback, and a
   dedicated Phase 2 handoff.
2. **Static validation:** in a clean, isolated checkout run formatting,
   `terraform init -backend=false`, `terraform validate`, HCL/policy tests, and
   security scanners using the pinned tool/provider versions. Static PASS is
   source evidence only.
3. **Plan safety:** CI/OIDC plan only; separate state key; no AS-IS import,
   deletion, or type change; expected component-only creates; all required tags;
   no wildcard model allow; no resource association outside approved scope.
4. **Edge verification:** association observed from the owner stack; HTTPS/auth
   regression; rate threshold and recovery; managed-rule false positives;
   redaction review; per-subject/tenant quota, queue backpressure, and cost alarm
   positive/negative tests.
5. **AI boundary verification:** Broker correct-model/guardrail positive test;
   wrong model, unversioned guardrail, and direct Gateway calls denied; input
   allowlist and injection regression; Korean PII residual test; structured
   output and browser execution/external-load zero tests; backend retains final
   score authority.
6. **Metadata/evidence verification:** prohibited seed strings absent from logs,
   S3, DynamoDB, and exported receipts; TLS/public/wrong-key/wrong-tag requests
   denied; version/lock/PITR/deletion protection observed; expiry/deletion tested
   across every copy; alarm and incident owner exercises completed.
7. **Release integrity:** distinct-human approval of the saved plan, immutable
   source/input/archive/backend digests, apply of that same plan only, scoped
   smoke and rollback, redacted evidence, residual/cost check, and pipeline
   re-lock. Each independent release keeps its own status and receipts.

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
exact_model_id              = ""
broker_role_name            = ""
gateway_role_name           = ""
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

The sources are architecture and assessment inputs, not deployment approval.
