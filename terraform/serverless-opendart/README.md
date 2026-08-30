# OpenDART serverless wiring

기업 담당자가 공개된 기업 정보를 요청하면, J-Career API가 제한된 중계 경로를 통해
OpenDART를 조회하고 결과 복사본을 기업 DB에 저장하는 설계다. 추천 점수에는 영향을 주지
않는다. 현재는 이미지 검사 결과를 사람이 확인하기 전 단계이며, AWS 배포와 OpenDART
실호출은 아직 수행하지 않았다.

This isolated, default-off Terraform root provides on-demand public-company lookup
for the existing recruiter API. It does not modify `terraform/asis`, and source
presence is not evidence of deployed resources or a completed live OpenDART call.

## Data path

```text
API (UID 11001, no AWS credentials)
  -> peer-checked Unix socket
  -> OpenDART capability broker on the lab host
  -> SQS FIFO -> Lambda -> OpenDART public API
                         -> DynamoDB result, TTL one hour

API <- broker result read/delete <- DynamoDB
API -> validated last-known-good snapshot -> company DB
```

The broker has no TCP listener or generic AWS proxy. Its exact operations are queue
URL discovery, refresh dispatch, bound result retrieval, and conditional result
deletion. It never returns credentials. The Lambda is outside a VPC and cannot
connect to PostgreSQL, avoiding a NAT Gateway and keeping the API as the only
company-DB writer. Retrieved facts have `score_effect=NONE`.

The reader checks logical expiry before accepting an item; DynamoDB TTL is physical
cleanup only. Duplicate refreshes reuse the pending request. Collect, timeout, and
expiry transitions compare-and-set the same pending request ID, preventing an old
result from clearing a newer request.

## Stages and approvals

- `disabled` (default): zero managed resources.
- `bootstrap`: eight planned/creatable resources.
- `runtime`: eleven planned/creatable resources: bootstrap plus digest-pinned
  Lambda, SQS event mapping, and least-privilege API-role policy.

Enabled stages require the exact acknowledgement and a pseudonymous approval
reference. Runtime additionally requires an existing SecureString parameter, an
existing API role name, and an ECR image URI pinned by digest. This root does not
create or store the OpenDART API-key value.

`scripts/Invoke-ApprovedTerraform.ps1` creates the saved plan and consumes a human
approval bound to its SHA-256, backend SHA-256, and provider-account SHA-256. The
account number is held only long enough to hash it; the raw value is not printed or
written. The plan-side bindings are stored and consumed atomically, and the account
digest is rechecked immediately before and after apply and retained in the linked
operation journal. For runtime, the same approval is bound to the Lambda image
digest. Its redacted apply receipt is later checked against the exact
private backend configuration before lab wiring. An apply receipt records command
completion only; it deliberately records `runtime_smoke_completed=false` and is not
a usability or live-call observation. The lab wiring also resolves its validated
instance profile to one IAM role and requires this root's state-recorded API sender
policy to name that same role; an ambiguous or different role fails closed.

Runtime outputs are account-free names only:

- `OPENDART_DISPATCH_MODE`
- `OPENDART_REFRESH_QUEUE_NAME`
- `OPENDART_RESULT_TABLE_NAME`
- `OPENDART_PENDING_TIMEOUT_SECONDS`

No queue URL, ARN, account ID, key, or credential is exported to the application.
The broker and lab wrapper intentionally accept only lowercase queue/table names up
to 80 characters. The FIFO queue base allows lowercase letters, digits, hyphens, and
underscores; the only dot is the required `.fifo` suffix. The DynamoDB table limit is
a narrower project boundary, not AWS's 255-character service maximum.

## Guarded worker image publication source

`scripts/Invoke-ApprovedOpenDartWorkerPublish.ps1` declares a three-step Windows
operator path. Its presence does not mean any step was run.

1. `Prepare` copies the exact worker build context into a current-user-only snapshot,
   builds `linux/amd64`, runs Trivy for the explicitly supplied severity set, and writes
   a preparation receipt plus scan-report hash. It does not decide whether findings are
   acceptable and cannot push.
2. `Review` verifies the private backend and bootstrap apply receipt, reads the exact
   eight-address bootstrap state, hashes the current provider account and state-derived
   ECR URL, verifies the live repository is immutable with scan-on-push and AES256,
   rechecks the prepared image and scanner, and writes only a
   `PENDING_HUMAN_DECISION` draft. Raw account and repository identifiers are not emitted.
3. A person reviews the scan and creates a separate approval record valid for at most
   24 hours. Only `Publish` can consume that record, confirm the unique tag is absent,
   log in through a dedicated current-user-only Docker configuration, push once, compare
   the digest reported by Docker with ECR, blank the temporary authentication config, and
   create a protected digest-pinned URI artifact plus redacted receipt.

The example approval is permanently pending and cannot authorize publication. A source
revision is a human-supplied binding label; the independently computed source tree and
archive hashes bind the actual copied bytes. The local journal and artifacts are retained
after success, failure, or interruption for a person's disposition. This source provides
no signature service, trusted approval store, reviewer identity proof, cross-host mutex,
scan acceptance decision, or evidence that ECR, Lambda, or OpenDART was reached. The fixed
repository path, protected checker/input snapshots, independent PowerShell approval check,
and hashes of the selected tools/checkers/backend bytes close source substitution and TOCTOU
paths in this operator, but tool provenance and approval authenticity still require human
review in the future execution environment.

## Verification and later observation

```powershell
python scripts/check_serverless_opendart_static.py --root .
python tests/test_serverless_opendart_static.py
python tests/test_opendart_runtime_binding.py
python tests/test_aws_capability_broker.py
python scripts/check_opendart_worker_publish.py static --root .
python tests/test_opendart_worker_publish.py
terraform -chdir=terraform/serverless-opendart fmt -check
```

`src/runtime/tests/opendart_live_smoke.py` is an operator-invoked, synthetic-account
observation after an approved deployment. It requires a separate call
acknowledgement and public company code/name, and verifies
`UPDATED_EXTERNAL_SNAPSHOT`, `AVAILABLE_LIVE`, `source_kind=live_open_api`, and
`score_effect=NONE`. It does not print fetched facts. It has not been run here.

Teardown requires a separately approved delete-only saved plan. Post-apply state or
receipt output alone does not establish that all external AWS inventory is absent.
