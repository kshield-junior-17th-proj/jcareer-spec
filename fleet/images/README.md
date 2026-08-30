# Consultant workplace image sources

These sources turn the six endpoint labels into repeatable build contracts. No
AMI, macOS image, signed package, device, user, credential, or observation is
currently claimed.

The Windows route uses EC2 Image Builder with a human-reviewed, version-pinned
Windows Server 2022 Desktop parent, IMDSv2, and fail-closed Firewall/Defender
tests. It is a practical AWS desktop simulation, not Windows 11. The image
contains no preview token or account credentials. A later approved session
workflow supplies a query/fragment/user-info-free HTTPS preview URL and an
operator-held EC2 Windows credential outside Terraform. The endpoint saved plan
also requires a human image receipt
that matches its AMI, build reference, current source bundle SHA-256, and
redacted AWS build observation. Separate one-run build and AMI/snapshot cleanup
approvals prevent automation from releasing or deleting an image by itself. The
endpoint launch source renews a bounded automatic stop task on every boot; an
allowlisted, separately approved delete-only saved plan remains the cleanup path.

The macOS route is deliberately source-only. The current lab permits t3.micro
and t3.small resources, while EC2 Mac requires a Mac Dedicated Host. A human
must select either licensed physical Macs managed through MDM or approve a
separate EC2 Mac policy/budget exception. The shell components are inputs to
that later process; they are not an image artifact. They now include
credential-free Slack/OpenDART shortcuts and an approved-preview session script,
but do not establish MDM enrollment, remote access, or a physical device.
