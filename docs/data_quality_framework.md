# Data Quality Framework

Five layers of automated checks; nothing is silently dropped or fixed.

## 1. Ingestion integrity (Python, per run)
- Run lifecycle: `running → success | partial | failed` in the manifest;
  manifests are written even when a run fails (finally-block).
- Reconciliation against the API's `totalCount` (`countTotal=true`).
- **Quarantine, not drop**: invalid records get reason codes
  (`NOT_AN_OBJECT`, `MISSING_NCT_ID`, `INVALID_NCT_ID_FORMAT`) and are
  counted in the manifest.
- Partial runs (page-capped) are excluded from incremental reuse, from
  silver by default, and from every metric.

## 2. Transform validation (Python, per run)
- NCT regex validation; within-run duplicate NCT IDs deduped kept-first
  and logged with counts.
- `record_quality_flag` per trial: `missing_overall_status`,
  `missing_study_type`, `start_after_completion`,
  `results_before_first_post`, `negative_enrollment`, else `ok`.
- Silver row counts reconciled against the manifest; profile JSON written
  per run (`data/silver/_profiles/`).

## 3. Warehouse tests (dbt — 73 data tests, all green at last build)
- Schema tests: `not_null`, `unique`, `accepted_values`, `relationships`
  on every key and grain, staging through marts.
- Singular tests:
  | Test | Severity | Asserts |
  |---|---|---|
  | assert_valid_study_dates | warn | start ≤ completion where both exist |
  | assert_one_current_record_per_trial | error | ≤1 `current_record_flag` per NCT |
  | assert_trial_site_relationship_integrity | error | every site row joins dim_trial |
  | assert_valid_us_state | error | 2-letter state codes at the mart boundary |
  | assert_snapshot_completeness | warn | success runs reconcile with unique NCTs |
  | assert_feasibility_score_within_bounds | error | score ∈ [0, 1] |
- Privacy guardrail: `stg_trial_contacts` is structurally empty.

## 4. Cross-layer reconciliation (`src/quality/reconciliation.py`)
Per success run: bronze manifest vs silver rows; NCT uniqueness. Warehouse:
`dim_trial` vs latest silver distinct NCTs; current-record cap. Results
render in the quality report (4/4 passing at last run).

## 5. Schema drift (`src/quality/schema_drift.py`)
Observed bronze field paths (depth 3) vs a stored baseline
(`data/bronze/_schema_baseline.json`, 125 paths). Drift produces a report
with added/removed paths; the baseline changes only via explicit
`--update-schema-baseline`. Drift is surfaced, never auto-accepted.

## Reporting
`make quality-report` → `reports/data_quality_report.md`: run reliability
table (from `mart_data_reliability`), reconciliation results, drift
status, and the interpretation guardrails. Unit/integration suite: pytest
(46 tests) including config-sync tests that fail if score weights or band
thresholds diverge between YAML, the dbt seed, and dbt vars.

## Severity philosophy
- **error** = structural contract broken → fix before shipping metrics.
- **warn** = real-world registry messiness → investigate, document, and
  disclose in `mart_data_reliability` rather than block the pipeline.
