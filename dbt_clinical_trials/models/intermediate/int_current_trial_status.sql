-- One row per NCT ID: the latest snapshot in which the trial appears,
-- plus whether that is the latest snapshot overall.
with history as (
    select * from {{ ref('int_trial_status_history') }}
),

latest_per_trial as (
    select *
    from history
    qualify row_number() over (
        partition by nct_id order by snapshot_date desc
    ) = 1
),

latest_overall as (
    select max(snapshot_date) as latest_snapshot_date from history
)

select
    t.*,
    o.latest_snapshot_date,
    (t.snapshot_date = o.latest_snapshot_date) as active_in_latest_snapshot_flag
from latest_per_trial t
cross join latest_overall o
