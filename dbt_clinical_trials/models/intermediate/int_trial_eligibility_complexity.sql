-- Per-trial eligibility complexity profile per ingestion run.
-- Grain: nct_id + ingestion_run_id.
with criteria as (
    select * from {{ ref('stg_trial_eligibility_criteria') }}
),
type_pivot as (
    select
        ingestion_run_id,
        nct_id,
        count(*) as total_criteria_count,
        count(*) filter (direction = 'inclusion') as inclusion_count,
        count(*) filter (direction = 'exclusion') as exclusion_count,
        count(*) filter (criterion_type = 'age') as age_criteria_count,
        count(*) filter (criterion_type = 'biomarker') as biomarker_criteria_count,
        count(*) filter (criterion_type = 'condition') as condition_criteria_count,
        count(*) filter (criterion_type = 'medication') as medication_criteria_count,
        count(*) filter (criterion_type = 'procedure') as procedure_criteria_count,
        count(*) filter (criterion_type = 'laboratory') as laboratory_criteria_count,
        count(*) filter (criterion_type = 'demographic') as demographic_criteria_count,
        count(*) filter (criterion_type = 'consent') as consent_criteria_count,
        count(*) filter (criterion_type = 'other') as other_criteria_count,
        count(distinct criterion_type) as distinct_type_count,
        bool_or(parse_quality != 'ok') as has_parse_quality_issue_flag
    from criteria
    group by 1, 2
)
select
    *,
    {{ safe_divide('exclusion_count', 'total_criteria_count') }} as exclusion_ratio,
    {{ safe_divide('distinct_type_count', '9') }} as type_diversity_score,
    case
        when total_criteria_count >= 15 and distinct_type_count >= 5 then 'high'
        when total_criteria_count >= 8 and distinct_type_count >= 3 then 'moderate'
        else 'low'
    end as eligibility_complexity_band
from type_pivot
