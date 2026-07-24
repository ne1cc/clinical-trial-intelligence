# Data Quality Report

Generated: 2026-07-24T22:37:35+00:00 (UTC)

Scope: public ClinicalTrials.gov registry snapshots taken by this
project. Quality findings describe registry listings, not trial
conduct or outcomes.

## Ingestion run reliability

| run | snapshot date | status | pages | manifest records | silver rows | reconciled | unique NCT | quarantined | flagged share | usable location share | low-confidence cond. share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 20260724T203950Z_46dc682b | 2026-07-24 | success | 26 | 2592 | 2592 | yes | yes | 0 | 0.000 | 0.481 | 0.340 |
| 20260724T203236Z_cade2517 | 2026-07-24 | partial | 2 | 200 | — | — | — | 0 | — | — | — |

## Cross-layer reconciliation

| check | run | expected | actual | passed | note |
| --- | --- | --- | --- | --- | --- |
| bronze_manifest_vs_silver_rows | 20260724T203950Z_46dc682b | 2592 | 2592 | yes |  |
| silver_nct_ids_unique | 20260724T203950Z_46dc682b | 2592 | 2592 | yes |  |
| warehouse_dim_trial_vs_latest_silver | 20260724T203950Z_46dc682b | 2592 | 2592 | yes | dim_trial holds one row per NCT ID seen in any snapshot; equality holds while snapshots share one query scope. |
| warehouse_one_current_record_per_trial | — | 2592 | 2592 | yes | Current records cannot exceed known trials. |

**4/4 reconciliation checks passed.**

## Schema drift

- Run checked: `20260724T203950Z_46dc682b`
- Status: **ok**
- Observed field paths: 125

## Interpretation guardrails

- Counts are registry listings, not patient availability.
- Snapshot-transition metrics stay at zero until this project has
  accrued multiple snapshots; registry-date proxies are labeled.
- Facility identity is best-effort text matching; no site-capacity
  or performance claims are made.
