-- One row per NCT ID (current record from latest snapshot): the fields
-- needed to score pairwise trial comparability against another trial.
-- Presentation-neutral -- assembles inputs only; mart_trial_similarity
-- does the actual pairwise scoring.
with current_trials as (
    select ingestion_run_id, nct_id
    from {{ ref('int_current_trial_status') }}
),

trial_fields as (
    select
        t.nct_id,
        t.phase_normalized,
        t.study_type,
        t.allocation,
        t.primary_purpose,
        t.enrollment_count,
        case
            when t.enrollment_count is null then null
            when t.enrollment_count < 50 then 'small'
            when t.enrollment_count <= 200 then 'medium'
            else 'large'
        end as enrollment_band,
        t.healthy_volunteers,
        t.sex,
        {{ parse_age_years('t.minimum_age') }} as minimum_age_years,
        {{ parse_age_years('t.maximum_age') }} as maximum_age_years,
        t.start_date,
        t.completion_date
    from {{ ref('stg_trials') }} t
    inner join current_trials c
        on t.ingestion_run_id = c.ingestion_run_id and t.nct_id = c.nct_id
),

conditions as (
    select nct_id, list(distinct condition_group) as condition_groups
    from {{ ref('bridge_trial_condition') }}
    group by nct_id
),

interventions as (
    select i.nct_id, list(distinct i.intervention_type) as intervention_types
    from {{ ref('stg_trial_interventions') }} i
    inner join current_trials c
        on i.ingestion_run_id = c.ingestion_run_id and i.nct_id = c.nct_id
    where i.intervention_type is not null
    group by i.nct_id
),

latest_site_snapshot as (
    select max(snapshot_date) as snapshot_date from {{ ref('fct_trial_site') }}
),

geography as (
    select f.nct_id, list(distinct f.state_normalized) as states
    from {{ ref('fct_trial_site') }} f
    inner join latest_site_snapshot ls on f.snapshot_date = ls.snapshot_date
    where f.state_normalized is not null
    group by f.nct_id
)

select
    tf.*,
    coalesce(co.condition_groups, []) as condition_groups,
    coalesce(iv.intervention_types, []) as intervention_types,
    coalesce(g.states, []) as states
from trial_fields tf
left join conditions co on tf.nct_id = co.nct_id
left join interventions iv on tf.nct_id = iv.nct_id
left join geography g on tf.nct_id = g.nct_id
