-- Grain: one row per trial x sponsor/collaborator x role (from each trial's
-- latest snapshot, matching dim_trial currency).
with current_trials as (
    select nct_id, ingestion_run_id
    from {{ ref('int_current_trial_status') }}
)

select distinct
    {{ generate_surrogate_key([
        's.nct_id', 's.sponsor_normalized', 's.sponsor_role',
    ]) }} as trial_sponsor_key,
    {{ generate_surrogate_key(['s.nct_id']) }} as trial_key,
    {{ generate_surrogate_key(['s.sponsor_normalized']) }} as sponsor_key,
    s.nct_id,
    s.sponsor_name,
    s.sponsor_normalized,
    s.sponsor_role,
    s.sponsor_class,
    (s.sponsor_role = 'lead_sponsor') as lead_sponsor_flag
from {{ ref('stg_trial_sponsors') }} s
inner join current_trials c
    on s.ingestion_run_id = c.ingestion_run_id and s.nct_id = c.nct_id
where s.sponsor_normalized is not null
