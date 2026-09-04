# J-Career AI Security Posture dashboard

Presentation-facing consulting dashboard for the 27-control assessment. It is intentionally separate from `../dashboard`, which is the static Evidence Desk and must not calculate assessment or residual-risk judgments.

## Interpretation boundary

- NIST AI RMF is the sole primary assessment framework.
- The baseline combines design-level review with five isolated-Lab samples; it is not proof of full operating effectiveness.
- The AS-IS evidence profile is frozen assessment data. The browser only renders it.
- The TO-BE radar is a proposed target and is explicitly not a verified after-state.
- No compliance score, residual-risk decision, or automatic finding judgment is produced.

Open `index.html` directly or serve this directory with any static HTTP server. No AWS, Terraform, credentials, state, raw prompts, or model responses are required.
