# J-Career AI security assessment dashboard

Status: `WORKING_DRAFT_HUMAN_REVIEW_PENDING` / `REMEDIATION_OPEN_UNVERIFIED` / `NOT_DEPLOYED`.

This GitHub Pages directory is a public specification and presentation reference for the NIST AI RMF assessment. It is not the isolated AWS assessment-dashboard deployment, an AWS delivery receipt, or evidence that a TO-BE control operates effectively. It remains separate from `../dashboard`, the static Evidence Desk boundary that must not calculate assessment or residual-risk judgments.

## Judgment contract

- NIST AI RMF is the sole assessment framework.
- The 27 `T.x` values are project-internal technical-item identifiers, not NIST AI RMF controls or subcategory identifiers.
- Every `T.x` item maps exactly once into `NF-01` through `NF-06`; these NF values are human-review-pending presentation groups, not confirmed persistent finding IDs.
- Every group has an `OPEN_UNVERIFIED` remediation, one proposed protection set, and one human revalidation gate.
- The decision path is `CHECKLIST → FINDING → REMEDIATION → UNVERIFIED_TARGET → HUMAN_REVALIDATION`.
- The radar separates measured AS-IS values from the target projection. `actualAfter` is deliberately `null` until an accepted human revalidation exists.
- The baseline combines design-level review with five isolated-Lab samples; it is not proof of full operating effectiveness.

`traceability.sourceBinding` records SHA-256 digests for the external 2026-09-05 source workbook and its D:J mapped workbook without exposing local paths or workbook contents. The digests bind this frozen snapshot to named inputs; they do not validate workbook semantics or replace the pending human review.

## Public data and browser boundary

The browser renders only the checked-in static snapshot and makes no runtime network request. The page contains no credentials, raw prompts, model responses, live customer records, direct applicant identifiers, AWS resource identifiers, service URLs, state, or Evidence Desk objects. Its CSP permits same-origin scripts, styles, images and fonts, blocks connections, forms, objects and frames, and requires no inline script or style exception.

GitHub Pages is the current public reference surface. The separately proposed AWS dashboard surface remains `NOT_DEPLOYED`; publishing this page cannot change that status. A future static deployment or live smoke would prove only that delivery surface, not the effectiveness of any `UNVERIFIED_TARGET` protection.

## Offline verification

These checks do not contact AWS, acquire credentials, read state, use Docker, or deploy anything:

```powershell
python -B -m unittest tests.test_assessment_dashboard_static
node --check assessment-dashboard/app.js
node --check assessment-dashboard/assessment-snapshot.js
node --test tests/assessment_dashboard_data.test.cjs
node scripts/check_public_ui.mjs
```
