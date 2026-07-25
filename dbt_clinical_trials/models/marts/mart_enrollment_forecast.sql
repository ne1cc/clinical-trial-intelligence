-- Enrollment forecasting and trial lifecycle analytics.
-- Grain: condition_group x phase_normalized x enrollment_stage (latest snapshot).
-- Aggregates enrollment velocity signals for portfolio-level planning.
-- These are registry-derived proxies, not actual enrollment measurements.
with latest_run as (
    select max(ingestion_run_id) as ingestion_run_id
    from {{ ref('int_enrollment_velocity') }}
),
velocity as (
    select v.*
    from {{ ref('int_enrollment_velocity') }} v
    inner join latest_run using (ingestion_run_id)
),
condition_map as (
    select distinct
        ingestion_run_id,
        nct_id,
        condition_group
    from {{ ref('int_trial_condition_mapping') }}
),
joined as (
    select
        v.*,
        coalesce(cm.condition_group, 'non_dementia_other') as condition_group
    from velocity v
    left join condition_map cm
        on v.ingestion_run_id = cm.ingestion_run_id and v.nct_id = cm.nct_id
)
select
    condition_group,
    enrollment_stage,
    count(distinct nct_id) as trial_count,
    round(avg(enrollment_count), 0) as avg_target_enrollment,
    round(avg(estimated_duration_days), 0) as avg_planned_duration_days,
    round(avg(elapsed_days), 0) as avg_elapsed_days,
    round(avg(planned_enrollment_rate_per_day), 2) as avg_planned_rate_per_day,
    round(avg(estimated_current_rate_per_day), 2) as avg_estimated_current_rate,
    count(distinct nct_id) filter (attrition_flag) as attrited_trial_count,
    {{ safe_divide(
        'count(distinct nct_id) filter (attrition_flag)',
        'count(distinct nct_id)',
    ) }} as attrition_rate,
    count(distinct nct_id) filter (registry_freshness_band = 'current')
        as fresh_listing_count,
    count(distinct nct_id) filter (registry_freshness_band = 'stale')
        as stale_listing_count,
    case
        when count(distinct nct_id) > 0
        then round(
            cast(count(distinct nct_id) filter (registry_freshness_band = 'stale') as double)
            / count(distinct nct_id) * 100, 1)
        else null
    end as stale_listing_pct
from joined
group by 1, 2
order by condition_group, trial_count desc
