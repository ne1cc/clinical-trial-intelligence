-- Grain: one row per trial x condition group (from each trial's latest
-- snapshot, matching dim_trial currency).
with current_trials as (
    select nct_id, ingestion_run_id
    from {{ ref('int_current_trial_status') }}
)

select
    {{ generate_surrogate_key(['m.nct_id', 'm.condition_group']) }}
        as trial_condition_key,
    {{ generate_surrogate_key(['m.nct_id']) }} as trial_key,
    m.nct_id,
    m.condition_group,
    m.dementia_relevance_flag,
    m.mapping_confidence,
    m.source_condition_count
from {{ ref('int_trial_condition_mapping') }} m
inner join current_trials c
    on m.ingestion_run_id = c.ingestion_run_id and m.nct_id = c.nct_id
