# Three Windows consultant endpoints

This default-off root is the deployment half of the Windows image contract.
`disabled` manages zero resources. `windows_three` plans exactly nine resources,
including three `t3.small` instances labelled `WIN-01`, `WIN-02`, and `WIN-03`.
They remain Windows Server 2022 desktop simulations, not Windows 11 workstations.

A usable image receipt must bind the reviewed AMI, image-build reference, current
source bundle, and redacted build-observation SHA-256. The deployment wrapper checks
those bindings and the exact saved-plan before apply. Its v3 human approval also
binds the provider-account SHA-256 printed by plan-only mode. The raw account number
is not printed or stored; the atomic plan binding and protected operation journal
retain only the digest, which is rechecked immediately before and after apply.

Instances use encrypted `gp3`, IMDSv2, standard CPU credits, a no-inbound security
group, SSM management, and a boot-renewed automatic shutdown task. Outbound is
TCP/443 to the Internet and is not domain allowlisting. Initial Windows credentials
remain under the operator-controlled EC2 key-pair process; no password or private
key enters Terraform or the image.

After deployment, `scripts/Invoke-ApprovedWindowsEndpointSession.ps1` consumes a
separate approval for exactly three endpoint/session/local-port bindings and an
expiry within eight hours. Through SSM it rechecks instance/image lineage, SSM and
RDP-loopback health, Firewall, Defender, Microsoft Edge signature, and the embedded
session-script hashes. It then binds the credential-free HTTPS preview URL by
SHA-256 and can open exactly three SSM-tunneled RDP clients with `/prompt`.

The approval also binds the SHA-256 of the HTTPS preview bootstrap token and fixes
its delivery method to `RDP_CLIPBOARD_ONE_TIME`. The operator supplies that token
as a PowerShell `SecureString` obtained with `Read-Host -AsSecureString`; the
wrapper never sends it through SSM, Terraform,
or a receipt. After each RDP client opens, the wrapper places the bootstrap URL on
the local clipboard once, waits for the operator to paste it into Edge, and clears
the clipboard immediately. The clean URL remains in an explicit Microsoft-signed
Edge shortcut with a session-specific browser profile. Ending the interactive
workflow stops all three local tunnels, removes the remote session profile and
shortcut, and schedules endpoint shutdown.

Clearing the active clipboard does not prove removal from host clipboard history
or cloud-synchronization stores. The operator host therefore still needs an
approved clipboard-history/sync policy; the wrapper records delivery, not proof of
historical clipboard erasure. Likewise, the shutdown marker records that shutdown
was scheduled, not that the later EC2 stopped state was observed.

Before any remote configuration, the wrapper reads the sensitive Terraform
security-group output, requires each instance to have exactly that one group, and
observes zero live ingress permissions. These are runtime observations, not a
general security or compliance verdict.

The redacted session observation records no raw instance IDs or credentials.
`gui_login_observed=false` and `preview_https_observed=false` remain until a
consultant separately observes and records the interactive result. Therefore an
applied endpoint plan alone is not evidence that a person successfully used all
three desktops.

The session wrapper resolves its AWS, Terraform, Python, and RDP applications to
absolute executable paths, module-qualifies process/CIM/TCP/clipboard operations,
and protects temporary JSON and stderr with the current operator's Windows ACL
before content is written. The operator host must therefore be Windows with an
ACL-capable local filesystem. Absolute-path resolution prevents PowerShell
alias/function shadowing after resolution; it does not certify the publisher or
integrity of every resolved CLI or the Session Manager plugin. Trusted endpoint
software distribution and allowlisting remain operational prerequisites.

Concurrent session approvals that target the same backend are serialized by one
canonical logical-backend global mutex across users and local worktrees on the same
operator host. The lock is not
a cross-host or durable remote operation ledger. Multi-host operation remains
blocked pending a human-approved conditional remote lease and replay policy.

Before either checker, Terraform, or remote configuration consumes an input, the
session wrapper captures nine files into one operator-only temporary snapshot set:
backend configuration, approval, deployment/image receipts, build observation,
both endpoint scripts, and both Python checkers. Each copy is made while the source
is opened read-only without write/delete sharing; source-before, snapshot, and
source-after SHA-256 plus byte length must agree. Read handles keep the snapshots
non-writable until the operation ends, and Terraform receives the same backend
snapshot that produced the mutex identity. A success observation is written only
after snapshot deletion is observed. Failure observations record the actual
snapshot count and whether local cleanup needs retry. This closes the reviewed
same-host input-swap race; it does not authenticate the provenance of inputs that
were already modified before capture.
Both success and failure observations are emitted only after the ordinary request/
stderr temporary directory has also been checked for removal; a failed removal is
reported as cleanup-retry-required rather than as no cleanup needed.

Local tunnel cleanup retains the root process handle, verifies PID/start-time and
CIM parent/creation identities for observed descendants, terminates matching SSM
sessions, and requires the loopback port to close. The process is not launched in
a Windows Job Object, so these observations cannot prove that an untracked child
escaped before the final snapshot. A Job Object or equivalent brokered launcher is
a remaining architecture decision before treating process-tree closure as strong
host containment evidence.

This root creates zero macOS resources. `MAC-01` through `MAC-03` require the
separate physical-Mac/MDM route or a human-approved EC2 Mac exception described in
the image contract. The macOS cleanup source removes its local shortcut and
session launcher and makes best-effort Safari/Slack termination attempts, but it
cannot prove browser-cookie removal. Cookie cleanup therefore remains
`HUMAN_MDM_REQUIRED`; no automatic macOS session-complete claim is made. Do not
describe six requested labels as six deployed devices.

All apply and teardown actions require an externally supplied encrypted S3 backend,
S3 locking, and plan-bound human approval. Teardown applies only the approved
delete-only saved plan and still needs a separate residual-inventory observation.
