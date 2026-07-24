# Executive Memo — Feasibility Review Priorities
<!--
TEMPLATE. Square-bracket fields are filled from the warehouse after each
snapshot; italic figures below show the 2026-07-24 build as an example.
Language must follow docs/clinical_interpretation_guardrails.md.
-->

**To:** Director of Clinical Operations
**From:** [Analyst]
**Date:** [YYYY-MM-DD] · Snapshot: [snapshot_date] · Run: [ingestion_run_id]
**Re:** Where to direct the next cycle of site-feasibility reviews

> Source: ClinicalTrials.gov public registry listings. All figures are
> potential competition signals for feasibility review — not recruitment
> forecasts, patient availability, or site-performance judgments.

## 1. Bottom line
Of [N segments] condition–state–phase segments with active recruiting
listings *(449 on 2026-07-24)*, [K] warrant feasibility review this cycle
*(75 in band `review`; 0 reached `priority_review`)*. The strongest
signals concentrate in [top segments] *(Alzheimer's disease Phase 3 in
FL, CA, TX)*.

## 2. Top segments for review
| Rank | Segment | Score | Recruiting listings | Sponsor HHI | Why (deterministic explanation) |
|---|---|---|---|---|---|
| 1 | [cond · state · phase] | [0.xx] | [n] | [0.xx] | [priority_explanation] |
| 2 | … | | | | |
| 3 | … | | | | |

*(Source: `mart_feasibility_priority_queue`; explanations are generated
from fixed component phrases, not written ad hoc.)*

## 3. What is driving the signals
- **Density:** [n] recruiting listings across the top segments
  *(419 recruiting trials nationally, 50 states with listed sites)*.
- **Growth:** [transition counts, or:] snapshot history is [m] snapshots
  deep; growth currently uses the registry first-post-date proxy and is
  labeled as such.
- **Site overlap:** [n] facilities are listed by more than one recruiting
  trial *(301 of 6,241 listed facilities)* — shared-listing signal only.
- **Sponsor concentration:** [segments with HHI ≥ x] show concentrated
  lead-sponsor listings.

## 4. Data confidence
[usable_location_share]% of location rows were usable for U.S. geography
*(48.1%)*; [flagged share]% of trial records carried quality flags
*(0.0%)*; manifest reconciliation [passed/failed] *(passed, 2,592 = 2,592,
unique NCT IDs)*. Details: `reports/data_quality_report.md`.

## 5. Recommended actions (all human-review actions)
1. Commission feasibility reviews for the top [K] segments.
2. For overlapping facilities in those segments, verify actual site
   availability directly — listings do not measure capacity.
3. Re-run the pipeline next [week]; transition-based growth replaces the
   proxy automatically once history accrues.

## 6. Cost framing (assumptions, not outcomes)
Under the editable assumptions in `config/roi_assumptions.yml`
([reviews/cycle], [cost/review], …), the [base] scenario frames
[currency amount] of review effort better targeted. **Illustrative
arithmetic over stated assumptions — no observed savings are claimed.**

## Appendix
- Queue extract: `analysis_top_priority_segments` (dbt analysis)
- Methodology: `docs/metric_definitions.md`
- Limitations: `docs/assumptions_and_limitations.md`
