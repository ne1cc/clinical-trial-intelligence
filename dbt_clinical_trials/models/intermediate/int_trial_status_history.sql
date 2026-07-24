-- Longitudinal status history constructed from this project's own snapshots
-- (the registry API serves only current records). One row per NCT ID per
-- complete (status='success') snapshot date; latest run wins within a date.
with complete_snapshots as (
    select ingestion_run_id, snapshot_date
    from {{ ref('stg_trial_snapshots') }}
    where status = 'success'
),

trials as (
    select t.*
    from {{ ref('stg_trials') }} t
    inner join complete_snapshots s using (ingestion_run_id)
    qualify row_number() over (
        partition by t.nct_id, t.snapshot_date
        order by t.snapshot_timestamp_utc desc
    ) = 1
)

select
    nct_id,
    ingestion_run_id,
    snapshot_date,
    snapshot_timestamp_utc,
    overall_status,
    phase_normalized,
    study_type,
    enrollment_count,
    lead_sponsor_name,
    lead_sponsor_normalized,
    has_results_flag,
    study_first_post_date,
    record_quality_flag,
    source_json_hash,
    lag(overall_status) over trial_window as previous_status,
    (
        lag(overall_status) over trial_window is not null
        and lag(overall_status) over trial_window is distinct from overall_status
    ) as status_changed_from_previous_snapshot_flag,
    (
        overall_status = 'RECRUITING'
        and lag(overall_status) over trial_window is not null
        and lag(overall_status) over trial_window != 'RECRUITING'
    ) as entered_recruiting_flag,
    (
        overall_status != 'RECRUITING'
        and lag(overall_status) over trial_window = 'RECRUITING'
    ) as left_recruiting_flag,
    min(snapshot_date) over (partition by nct_id) as first_seen_snapshot_date,
    datediff(
        'day',
        min(snapshot_date) over (partition by nct_id),
        snapshot_date
    ) as days_since_first_seen
from trials
window trial_window as (partition by nct_id order by snapshot_date)
