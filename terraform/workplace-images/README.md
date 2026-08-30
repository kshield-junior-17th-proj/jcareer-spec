# Consultant workplace image definitions

This default-off root defines a repeatable Windows consultant image. `disabled`
manages zero resources; `definition` plans twelve. Terraform creates Image Builder
definitions only: it does not start a build or launch the three requested desktops.

The OS contract is a Windows Server 2022 desktop simulation, not Windows 11. The
recipe requires a reviewed, version-pinned parent image, encrypted `gp3`, IMDSv2,
`t3.small`, automatic failed-build termination,
Windows Firewall, Defender real-time monitoring, SSM Agent, Remote Desktop, and a
validly signed Microsoft Edge executable. It embeds hash-bound session configure
and expiry-cleanup scripts. No user, AWS, SaaS, OpenDART, Bedrock, preview token, or
preview URL is baked into the image.

The image test fails unless Remote Desktop is allowed by the terminal-server policy,
TCP 3389 is listening, and an enabled inbound Windows Firewall rule is associated
with that port. This is an image-build observation only; the endpoint security group
still has zero inbound rules and access remains through the approved SSM-tunneled
session path.

Terraform receives operator-supplied build subnet and security-group IDs. The build
wrapper re-reads those exact live objects after approval and immediately before the
pipeline run, requiring one available subnet with public-IP mapping disabled and one
same-VPC security group with zero ingress. This is a point-in-time observation, not a
claim about every route or later network change.

Definition approval binds the exact saved-plan, backend, and provider-account
hashes. The generic wrapper prints only the account digest for review, stores it
atomically with the backend binding, rechecks it immediately before and after
apply, and links it through the protected operation journal; it does not persist or
print the raw account number. A different bounded approval starts one pipeline
execution and writes a redacted observation
for one private, encrypted, tested AMI. The observation also binds the image-build
reference, source-bundle SHA-256, and pipeline-configuration SHA-256. It does not
release the image for endpoints by itself. The pipeline-configuration digest is
computed from canonical JSON containing the complete live Image Builder pipeline,
recipe, infrastructure configuration, and distribution configuration objects read
before approval. An available-build observation is written only after the AMI has
zero launch permissions and every output snapshot has zero create-volume
permissions; both measured counts remain explicit in the observation.

Each valid Image Builder output descriptor and each discovered snapshot set is
written incrementally to a BOM-free operator-private inventory before release
validation. A terminal failed/cancelled build, including one with zero artifacts, can
produce a complete non-releasable inventory for a separate human cleanup approval.
If AWS returns an invalid descriptor or discovery stops before the full artifact set
is known, the inventory remains explicitly incomplete: automated cleanup stays
blocked and a person must choose a recovery method. A non-releasable observation
cannot create an endpoint image receipt.

Cleanup requires another approval bound to the build observation and a private
inventory. It requests Image Builder deletion with AMIs/snapshots, then requires an
endpoint-disposition observation demonstrating that the known three endpoint slots
and active instances for the image have been reviewed. After that approval check,
the cleanup wrapper reinitializes the supplied endpoint backend, requires its state
list to be exactly empty, and recounts active instances for every inventory AMI
immediately before requesting deletion. These are point-in-time reads across
separate Terraform and AWS APIs: they narrow but cannot eliminate every concurrent
change window. Files containing raw AWS
identifiers remain operator-private and need their own encrypted storage, access,
and retention controls.

If deletion reached the live Image Builder `DELETED` state but the normal cleanup
receipt was not written, `scripts/New-WindowsImageDeletedRecoveryObservation.ps1`
uses a separate read-only approval. It requires two repeated observations of an
empty endpoint Terraform state, zero active instances for every inventory AMI,
and zero residual inventory AMIs and snapshots. `ResourceNotFound` for the Image
Builder build is rejected; only the inventory-scoped EC2 AMI/snapshot not-found
responses can count as residual zero. The recovery observation is explicitly
`OBSERVATION_ONLY_NOT_COMPLETION`; only its hash-bound recovery receipt completes
the local record pair. Each approval writes to its own approval-hash directory, so
an expired observation-only attempt remains preserved while a newly approved
attempt can create a separate pair. Neither record asserts that this operator performed the
deletion, that a lifecycle execution succeeded, or that the whole account is
empty.

Normal cleanup and read-only recovery share one canonical logical-backend global
mutex across users and worktrees on the same Windows operator host. This does not coordinate different
hosts. Until a human approves a remote conditional-lock/operation-ledger design,
only one approved operator host may run either workflow. Record timestamps are
checked against the approval window and each other, but are still based on the
operator clock and have no external immutable timestamp anchor.

The generic Terraform apply and teardown wrappers additionally share a
canonical-backend active journal under the current Windows account's local
application-data directory. It coordinates both modes across worktrees for that
account, retains cleanup failures for human disposition, and archives successful
receipt/journal pairs before clearing the active marker. It is not shared by
different Windows accounts or hosts. Current operation therefore assumes one
approved OS account on one operator host; multi-account operation requires a
human-approved machine-wide or remote conditional ledger design.

The operators create ACL-protected temporary files before writing JSON or CLI
stderr and replace completed records atomically. They require Windows PowerShell
on an ACL-capable local filesystem. This controls ordinary access but is not secure
erasure; operator-host disk encryption, trusted software paths, log handling, and
retention remain operational controls.

Build, cleanup, endpoint-disposition, and deleted-state recovery also copy every
operation input into an operator-only temporary set while holding read locks that
deny write and delete sharing. Hashing, JSON parsing, Python validation, and
Terraform backend initialization consume those same copies. The build set includes
the five source-bundle files and both sibling Python modules under their expected
names, so the approved source digest is calculated from the protected tree. Python
validation runs with environment, user-site, site startup, and bytecode writes
disabled. Exact input counts make an omitted optional or required capture fail
closed. These controls bind local bytes during one process; they do not attest the
operator executable, the imported snapshot module, a different host, or later AWS
state.

A forced process termination can still leave an operator-private snapshot directory.
No automatic sweep deletes it. The shared module exposes an explicit stale-recovery
operation that requires the acknowledgement
`JCAREER_STALE_SNAPSHOT_RECOVERY_APPROVED` and accepts only one direct-child
prefix/GUID directory owned by the current SID, with the exact protected ACL, no
reparse point anywhere in the tree, and no active per-directory global mutex. The
same conditions are checked again immediately before recursive removal. A person
must first establish that the abandoned inputs may be removed; the function does
not make that retention decision.

macOS is deliberately source-only in this root. The component set verifies Safari,
installs approved Slack/OpenDART shortcuts, binds a credential-free preview URL by
SHA-256, records `MAC-01` through `MAC-03`, limits sessions to 15 minutes through 8 hours,
and installs five-minute expiry cleanup. It is not a signed package, MDM profile,
macOS image, or device observation. A human must choose licensed physical Macs plus
MDM or approve an EC2 Mac Dedicated Host exception, budget, region capacity,
identity, and remote-access method.

All Terraform actions require an externally supplied encrypted S3 backend with an
S3 lockfile and root-specific key. The generic approved-Terraform wrapper and the
separate build/cleanup wrappers consume decisions; they do not make them.
