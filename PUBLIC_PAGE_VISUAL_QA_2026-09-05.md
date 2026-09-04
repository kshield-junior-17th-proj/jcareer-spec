# Public page visual and AI security QA — 2026-09-05

## Decision

Publish the corrected AI security assessment dashboard as a clearly labelled working snapshot. Do not publish the pending animation atlas yet.

The dashboard can be made legible and honest without changing its frozen assessment values. The atlas has unresolved motion-accessibility and architecture-status narration issues that need source-owner correction before public linking.

## Scope and evidence boundary

- Latest public site: `https://kshield-junior-17th-proj.github.io/jcareer-spec/`
- Public baseline commit during review: `f3cfba2`
- Pending source reviewed read-only: `publish-ai-security-20260905`; finalized during review as `c165747`
- Assessment framework: NIST AI RMF only
- Architecture evidence: committed public specifications, diagram specifications, pending presentation source, and source declarations only
- Excluded: cloud API calls, Terraform execution, Docker, credentials, state, raw prompts, and model responses

The live page returned HTTP 200 and contained the current `APPLY · LIVE SMOKE NOT RUN` boundary. It did not yet contain the pending assessment-dashboard route.

## Findings

### Pending assessment dashboard

1. The responsive stylesheet removed all in-page navigation below 1000 px and did not provide an alternative.
2. There was no skip link, visible `:focus-visible` treatment, reduced-motion rule, canonical URL, description, or Open Graph description of the page.
3. `main { overflow: hidden; }` could conceal painted overflow instead of resolving it. Rigid finding columns and large Korean display type increased the clipping risk.
4. `27-control evidence profile`, `CHECKLIST EVIDENCE`, and T.x labels could be mistaken for NIST-defined control IDs or a NIST checklist. NIST states that Core actions are not a checklist or ordered sequence.
5. The 0–4 radar and all-4.0 target could read as a maturity or compliance score despite the small caveat. NIST AI RMF does not define this project-specific score.
6. `3/2 · 관찰 실패 · 검증 공백` was ambiguous. The intended meaning in the snapshot is 3 observed vulnerable behaviors and 2 verification gaps.
7. Finding selection used visual `.active` state only. It did not expose a selected-tab state or keyboard arrow navigation.

### Pending animation atlas — hold

1. The brand link inherited default browser blue on a dark green masthead and had no explicit focus treatment or skip link.
2. The embedded SVGs guard dashed-line CSS animation with `prefers-reduced-motion`, but their repeated SMIL `<animateMotion>` dots have no reduced-motion stop or static substitute.
3. The overall delivery diagram visibly includes apply and live-smoke steps. The current public truth separates the newest saved plan (`a9764f8`, run `33569358467/1`) from the last observed deployment (`7a5acfb`, run `33466745822`). Without that revision split on the atlas plate, the flow can imply that the newest plan reached apply/live smoke.
4. The TO-BE control chain is technically framed as proposed and not deployed. Source declarations also default its components off and do not associate the proposed CloudFront-scope WAF with an existing distribution. That boundary must remain visible if the atlas is revised.

### AWS technical-blog quality

The strongest existing quality is the explicit separation of source, observed state, and proposed target. The weakest part was the pending dashboard's lack of method provenance and the atlas's loss of revision-specific state. Public diagrams should answer four questions beside the visual: what changed, what was observed, what remains unverified, and what evidence closes the gate.

## Implemented on this branch

- Added `assessment-dashboard/` with a responsive, keyboard-accessible working-snapshot presentation.
- Added a visible NIST AI RMF interpretation boundary and the four Core functions: GOVERN, MAP, MEASURE, and MANAGE.
- Relabelled T.x as project-internal identifiers, not NIST subcategory IDs.
- Relabelled the radar as an internal display index, not an AI RMF score, compliance score, maturity level, operating-effectiveness result, or residual-risk decision.
- Disambiguated the five PoC samples as 3 observed vulnerable behaviors and 2 verification gaps.
- Added skip navigation, focus-visible states, retained mobile section navigation, touch treatment, reduced-motion behavior, canonical and social metadata, and a route back to the architecture site.
- Added a text alternative for every radar value and semantic evidence-list descriptions.
- Implemented the six findings as an ARIA tab set with one selected tab, arrow keys, Home, and End.
- Added the assessment route to the public landing navigation and workstream list.
- Changed the mobile landing navigation to a two-row layout and changed the coordinate ledger to a stacked layout so added routes and the location label do not clip.
- Extended browser QA to detect painted text outside the viewport and individual navigation-link clipping, not only document-level horizontal scroll.

## Before and after verification

| Check | Before | After |
|---|---|---|
| Public route set | 7 pages × 2 viewports; 14/14 existing checks passed | 8 pages × 2 viewports; 16/16 checks passed |
| Assessment mobile navigation | Hidden below 1000 px | 5 section links remain visible at 390 px |
| Keyboard focus | No dashboard focus-visible rule | Skip link and all links/buttons have a 3 px visible focus indicator |
| Finding selection | Visual `.active` class only | 6 tabs, exactly 1 `aria-selected=true`, labelled tabpanel, arrow/Home/End support |
| Horizontal fit | Overflow could be masked by `main` | Root scroll width, key box bounds, painted hero text, and every landing-nav link fit at 390 px and 1440 px |
| Assessment interpretation | Custom IDs/index could resemble NIST controls/score | Visible internal-ID, non-score, non-compliance, non-operating-effectiveness, and non-residual-risk boundary |
| Static contract | None for pending dashboard | 3/3 assessment contract tests passed |

Browser verification command: `node scripts/check_public_ui.mjs`

Static dashboard verification command: `python -B -m unittest tests.test_assessment_dashboard_static`

## NIST sources

- [NIST AI RMF 1.0](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf)
- [NIST AI RMF Core](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/)
- [NIST AI RMF Playbook](https://airc.nist.gov/airmf-resources/playbook/)
