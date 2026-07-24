-- Reliability of every ingestion run: reconciliation plus the shares that
-- feed the data-confidence score component.
select
    ingestion_run_id,
    snapshot_date,
    status,
    manifest_record_count,
    trial_row_count,
    manifest_reconciled_flag,
    unique_nct_flag,
    quarantined_record_count,
    flagged_record_share,
    usable_location_share,
    low_confidence_condition_share
from {{ ref('mart_data_reliability') }}
order by snapshot_date desc, ingestion_run_id desc
