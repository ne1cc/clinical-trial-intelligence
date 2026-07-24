-- One row per normalized sponsor (from each trial's current snapshot).
with current_runs as (
    select ingestion_run_id, nct_id from {{ ref('int_current_trial_status') }}
),

sponsors as (
    select s.*
    from {{ ref('stg_trial_sponsors') }} s
    inner join current_runs r
        on s.ingestion_run_id = r.ingestion_run_id and s.nct_id = r.nct_id
    where s.sponsor_normalized is not null
)

select
    {{ generate_surrogate_key(['sponsor_normalized']) }} as sponsor_key,
    sponsor_normalized,
    min(sponsor_name) as sponsor_display_name,
    min(sponsor_class) as sponsor_class,
    count(distinct nct_id) as trial_count,
    count(distinct case when sponsor_role = 'lead_sponsor' then nct_id end)
        as lead_sponsor_trial_count
from sponsors
group by sponsor_normalized
