-- Enrollment velocity and trial duration estimation from registry dates.
-- Grain: nct_id + ingestion_run_id.
-- Derives enrollment pace proxies from public date fields. These are
-- registry-listing signals, not actual enrollment counts over time.
with trial_dates as (
    select
        t.ingestion_run_id,
        t.nct_id,
        t.overall_status,
        t.enrollment_count,
        t.enrollment_type,
        t.start_date,
        t.primary_completion_date,
        t.completion_date,
        t.study_first_post_date as first_post_date,
        t.last_update_post_date as last_update_date,
        current_date as as_of_date
    from {{ ref('stg_trials') }} t
),
duration_calc as (
    select
        *,
        datediff('day', start_date, coalesce(primary_completion_date, completion_date))
            as estimated_duration_days,
        datediff('day', start_date, as_of_date) as elapsed_days,
        datediff('day', first_post_date, last_update_date) as registry_activity_span_days,
        case
            when overall_status in ('RECRUITING', 'ENROLLING_BY_INVITATION')
                then 'active_recruiting'
            when overall_status = 'NOT_YET_RECRUITING'
                then 'pending'
            when overall_status in ('COMPLETED', 'ACTIVE_NOT_RECRUITING')
                then 'post_recruitment'
            when overall_status in ('TERMINATED', 'WITHDRAWN', 'SUSPENDED')
                then 'attrited'
            else 'unknown'
        end as enrollment_stage
    from trial_dates
    where start_date is not null
)
select
    *,
    case
        when estimated_duration_days > 0 and enrollment_count > 0
            then round(cast(enrollment_count as double) / estimated_duration_days, 2)
        else null
    end as planned_enrollment_rate_per_day,
    case
        when elapsed_days > 0 and enrollment_count > 0
            and overall_status in ('RECRUITING', 'ENROLLING_BY_INVITATION')
            then round(cast(enrollment_count as double) / elapsed_days, 2)
        else null
    end as estimated_current_rate_per_day,
    case
        when overall_status in ('TERMINATED', 'WITHDRAWN', 'SUSPENDED')
            then true
        else false
    end as attrition_flag,
    case
        when registry_activity_span_days is not null
            and registry_activity_span_days > 365
            then 'stale'
        when registry_activity_span_days is not null
            and registry_activity_span_days > 180
            then 'aging'
        else 'current'
    end as registry_freshness_band
from duration_calc
