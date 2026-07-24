-- Complete (success) snapshots should reconcile: silver trial rows equal the
-- manifest record count, with unique NCT IDs. Warn severity: a mismatch means
-- "investigate", not "block the pipeline".
{{ config(severity='warn') }}

select
    ingestion_run_id,
    manifest_record_count,
    trial_row_count,
    distinct_trial_count
from {{ ref('mart_data_reliability') }}
where status = 'success'
  and (
      not coalesce(manifest_reconciled_flag, false)
      or not coalesce(unique_nct_flag, false)
  )
