# Provider-free and local-mirror validation

Date: 2026-09-05 KST

Status: **SOURCE VALIDATION PASS / NOT DEPLOYED / NOT OPERATING-EFFECTIVENESS EVIDENCE**

No AWS API, backend, state, plan, apply, role attachment, CloudFront read-back,
model call, log delivery, or smoke test was used. Terraform 1.15.9 reused the
already-present local AWS provider 6.59.0 binary only for schema validation; it
did not download a provider. The generated Windows-only lock file was not kept
because it would be incomplete for Linux CI.

The repository CI copies this root into a runner-temp directory on a clean
Ubuntu runner, so `terraform init` may download the pinned provider from the
Terraform registry without writing generated artifacts into the public source
checkout. The workflow configures no AWS credentials and stops after
provider-schema validation and mock-provider tests; it does not call AWS, read
backend/state, plan, or apply. Immediately after init,
`check_tobe_provider_lock.py` requires the transient lock to select AWS provider
6.59.0 with a checksum. This is the explicit CI gate while the
single-platform local-mirror lock remains deliberately uncommitted. It is not
an apply gate: actual plan/apply remains blocked until a reviewed, committed
multi-platform lock contains registry checksums for every release runner.

| Check | Result | Meaning |
|---|---|---|
| `terraform fmt -check -recursive terraform/tobe-ai-security` | PASS | HCL is parseable and canonically formatted |
| `python -B scripts/check_tobe_ai_security_static.py --root .` | PASS | Default-off, exact-ARN, CloudFront binding, audit prefix, data-event, IAM, and claim boundaries are present |
| `python -B -m unittest tests.test_tobe_ai_security_static tests.test_tobe_provider_lock` | PASS, 6 tests | Static/evidence-language contract, KMS regressions, and provider-lock checker |
| `python -B -m unittest discover -s tests -p 'test_*.py'` | PASS, 152 tests | Existing public repository unit regressions including the six new tests |
| `terraform init -backend=false -plugin-dir=<pre-existing-local-provider-mirror>` | PASS | Local modules and provider schema prepared without backend or provider download |
| `python -B scripts/check_tobe_provider_lock.py --root .` after init | PASS | Transient lock selected exact AWS provider 6.59.0 and included a checksum; lock not retained because local checksum was Windows-only |
| `terraform validate -no-color` | PASS, no warnings | Root and child-module HCL conforms to Terraform/AWS provider schemas |
| `terraform test -no-color` | PASS, 2 tests | Mock-provider default plan selects zero components; populated three-module review input remains unverified and digest-bound |
| `git diff --check` | PASS | No whitespace error at the recorded validation point |

These results do not show that the existing CloudFront distribution uses the
ACL, that live Gateway/Broker roles match the supplied names, that IAM denies
work, that CloudTrail receives events, that KMS grants are sufficient in the
target account, or that the alarm routes to an exercised owner. Those are the
positive/negative release gates in `EVIDENCE_MAP.md`.

The source also cannot prove the Bedrock request-body contract. Before any live
claim, the Capability Broker must apply the Bedrock guard-content input tag to
every untrusted `InvokeModel` and `InvokeModelWithResponseStream` prompt segment,
reject missing/malformed tags before invocation, and pass redacted positive and
negative tests showing tagged injection blocked and benign tagged content
allowed. A configured `PROMPT_ATTACK` filter or IAM guardrail condition alone is
not operating-effectiveness evidence.
