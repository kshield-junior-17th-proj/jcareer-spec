# TO-BE AI security evidence map

> **SOURCE PROPOSAL / NOT DEPLOYED / HUMAN REVIEW PENDING**

This map keeps four different statements separate:

1. **AS-IS role:** repository-supported responsibility or historical evidence.
2. **Proposed source:** what this Terraform code would request when all gates are
   deliberately enabled.
3. **Required evidence:** what a future authorized release must observe.
4. **Prohibited claim:** what source, plan, output, or an older run cannot prove.

The `T.x` labels are project technical checklist IDs, not NIST AI RMF
subcategories or compliance scores. NIST AI RMF is the interpretation frame.

| Priority | Risk and AS-IS role | Proposed source assertion | Finding / project IDs | Required live evidence | Prohibited claim now |
|---|---|---|---|---|---|
| P0 | CloudFront is the public delivery edge. A new ACL that is not bound to the existing distribution changes nothing. | `modules/edge` creates a CloudFront-scope ACL and emits its ARN. The owner stack must set `web_acl_id`; optional read-back requires `Deployed` and exact ARN equality. | `NF-06`, `NF-05`; `T.6.1`, `T.6.2` | Saved owner-stack plan, distinct-human approval, same-plan apply, distribution status, exact `web_acl_id`, HTTPS/auth/rate/recovery tests | “WAF protects production” from ACL creation, output, diagram, or this repository |
| P0 | LLM Gateway owns explanation orchestration but must not own AWS model capability. Capability Broker is the only intended Bedrock caller. `PROMPT_ATTACK` also depends on the Broker's Bedrock guard-content input-tag request contract; HCL cannot inspect it. | Gateway allow policy has one numeric published-version Broker ARN; enabled plan read-back must match its ARN/version/CodeSha256 and both role ARN/unique IDs. Gateway also receives direct-Bedrock deny. Broker allow contains only the reviewed Bedrock ARN set and retained versioned guardrail. | `NF-03`, `NF-05`, `NF-04`; `T.1.1`–`T.1.3`, `T.3.1`–`T.3.3` | Saved plan records exact read-backs; IAM simulation and CloudTrail verify call boundaries; redacted runtime tests prove every untrusted `InvokeModel`/stream segment is guard-content tagged, tagged injection blocks, benign content passes, and missing/malformed tags fail closed | “Broker isolation or prompt-attack control works” from policy/guardrail HCL, a role name, or point-in-time plan alone; “Bedrock changed the final score” |
| P0 | A model/profile ID and IAM ARN set can silently refer to different approval subjects, especially with cross-region inference. Mutable Lambda aliases and same-name IAM role replacement add equivalent drift. | The model ID, sorted exact ARN set, published Broker version ARN/CodeSha256, two role names/ARNs/unique IDs, and request region are bound to one review digest. Wildcards, aliases, `$LATEST`, unqualified functions, and malformed ARNs are rejected. | `NF-03`, `NF-05`; `T.3.1`, `T.3.2`, `T.8.1` | Reviewer recomputes the digest from saved inputs and read-backs; model/provider owner confirms destinations and data residency; apply consumes the same saved plan | “One exact model/workload” when model targets, code, or role identities were reviewed separately |
| P1 | Gateway and Broker metadata are needed for investigation, but AS-IS raw prompt logging and unbounded content are risks. | Two KMS-encrypted allowlist-named log groups and two publisher policies: each role gets only its own log group, `records/<channel>/` S3 prefix, and `<channel>#` DynamoDB leading-key partition. | `NF-02`, `NF-04`; `T.2.1`–`T.2.3`, `T.7.1`, `T.7.2` | Prohibited canary absent from logs/S3/DynamoDB; exact role identities observed; cross-channel log/prefix/key, wrong tag/key/TLS attempts denied | “No prompt/PII is logged” or “tenant isolation” from field names, leading-key IAM, tags, or encryption alone |
| P1 | Evidence objects need integrity and bounded retention without becoming a claimed Evidence Desk. | Private BucketOwnerEnforced S3, versioning, KMS, Object Lock compliance retention, lifecycle; KMS/PITR/deletion-protected DynamoDB index; shared key has `prevent_destroy`. | `NF-02`, `NF-04`; `T.2.2`, `T.2.3`, `T.7.1`, `T.7.2` | Object version/lock/encryption observed; tamper/delete negative tests; owner-approved retention/deletion reconciliation; key-retirement inventory, migration and historical decrypt proof; expiry across every copy | “Evidence Desk deployed”, “legal hold satisfied”, “key can be retired”, or “deletion SLA met” |
| P1 | Control-plane and evidence-store operations need a durable independent audit path. | Multi-region CloudTrail management events plus evidence S3 and DynamoDB data events; separate private KMS audit bucket with S3 Bucket Keys; exact-trail-ARN and encryption-context-scoped `Decrypt`/data-key grant; KMS CloudWatch delivery; log-file validation. | `NF-04`, `NF-06`; `T.7.1`, `T.8.1`, `T.8.2` | `IsLogging`, digest validation, selected data events, Bucket-Key-encrypted delivery, CloudWatch delivery, denied actions and actor attribution observed; retention/cost owner accepts scope | “Complete audit trail” from a trail resource, key policy, or log group output |
| P2 | Repeated guardrail intervention may signal injection, data leakage attempts, or policy mismatch. | Metadata filter produces `GuardrailBlocked`; five-minute alarm threshold is explicit and bounded. | `NF-03`, `NF-06`; `T.1.2`, `T.6.1`, `T.7.1` | Synthetic block crosses threshold, alarm changes state, routed owner acknowledges, recovery and false-positive review complete | “Incident response works” from an alarm definition without actions or an exercised owner |

## Source-role anchors

- `src/runtime/AI_MATCHING_FLOW.md`: deterministic score remains separate from
  qualitative explanations; AS-IS lacks Bedrock IAM and a verified live broker
  boundary.
- `src/runtime/README.md`: LLM Gateway default provider is synthetic, live flag
  is false, and the conditional broker source is not deployment evidence.
- `terraform/asis/security/iam.tf`: the modelled enterprise stack shares an ECS
  task role, which is not the target least-privilege boundary.
- `terraform/asis/observability/main.tf`: AS-IS includes management-event
  CloudTrail and raw-prompt logging gaps; the TO-BE data-event and metadata-only
  controls must remain separate from that baseline.
- `terraform/asis/edge/main.tf`: the enterprise target owns its distribution;
  CloudFront WAF binding belongs in that owning stack rather than an association
  resource in this proposal.

## Release evidence sequence

`source check → provider-backed validate → reviewed committed multi-platform
provider lock → saved plan → separate review → exact plan apply →
CloudFront/IAM/CloudTrail and Bedrock guard-content request-contract negative and
positive tests → redacted evidence review → residual-risk decision`

No step can be skipped by relabelling `EXPECTED-*` tags, Terraform outputs,
GitHub Pages media, or historical synthetic runtime evidence as current proof.
