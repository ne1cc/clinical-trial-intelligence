-- Feasibility Review Priority Queue.
-- Grain: condition_group x state x phase at the latest complete snapshot.
-- Ranks segments for HUMAN feasibility review using a weighted blend of
-- normalized public-registry signals. This is a triage aid — a potential
-- competition signal, NOT a recruitment forecast and NOT a measure of
-- patient availability. Weights live in the feasibility_score_weights seed
-- (mirrored in config/score_weights.yml).
with latest_snapshot as (
    select max(snapshot_date) as snapshot_date
    from {{ ref('fct_trial_snapshot') }}
),

history_depth as (
    select count(distinct snapshot_date) > 1 as has_multi_snapshot_history
    from {{ ref('fct_trial_snapshot') }}
),

weights as (
    select
        max(case when component = 'normalized_recruiting_trial_count'
            then weight end) as w_density,
        max(case when component = 'normalized_recent_recruiting_growth'
            then weight end) as w_growth,
        max(case when component = 'normalized_sponsor_concentration'
            then weight end) as w_concentration,
        max(case when component = 'normalized_site_overlap'
            then weight end) as w_overlap,
        max(case when component = 'normalized_data_confidence_adjustment'
            then weight end) as w_confidence
    from {{ ref('feasibility_score_weights') }}
),

run_reliability as (
    select usable_location_share
    from {{ ref('mart_data_reliability') }}
    where status = 'success'
    order by snapshot_date desc
    limit 1
),

competition as (
    select c.*
    from {{ ref('mart_recruiting_competition') }} c
    inner join latest_snapshot using (snapshot_date)
),

-- Trials listing at least one facility that also hosts other recruiting
-- trials (best-effort facility identity; a listing signal only).
overlapping_trials as (
    select distinct f.nct_id
    from {{ ref('fct_trial_site') }} f
    inner join latest_snapshot ls on f.snapshot_date = ls.snapshot_date
    inner join {{ ref('mart_site_overlap') }} o
        on o.snapshot_date = f.snapshot_date
        and o.facility_normalized = f.facility_normalized
        and coalesce(o.city_normalized, '') = coalesce(f.city_normalized, '')
        and o.state_normalized = f.state_normalized
    where o.repeated_site_participation_flag
),

segment_trials as (
    select
        a.condition_group,
        a.state_normalized,
        a.phase_normalized,
        count(distinct a.nct_id) as segment_trial_check,
        {{ safe_divide(
            'count(distinct a.nct_id) filter (ot.nct_id is not null)',
            'count(distinct a.nct_id)',
        ) }} as site_overlap_share,
        {{ safe_divide(
            "count(distinct a.nct_id) filter (a.record_quality_flag = 'ok')",
            'count(distinct a.nct_id)',
        ) }} as record_quality_ok_share
    from {{ ref('int_condition_geography_activity') }} a
    inner join latest_snapshot ls on a.snapshot_date = ls.snapshot_date
    left join overlapping_trials ot on a.nct_id = ot.nct_id
    where a.overall_status = 'RECRUITING'
    group by 1, 2, 3
),

inputs as (
    select
        c.condition_group,
        c.state_normalized,
        c.phase_normalized,
        c.snapshot_date,
        c.recruiting_trial_count,
        c.listed_site_count,
        c.new_recruiting_90d,
        c.newly_posted_90d_proxy,
        h.has_multi_snapshot_history,
        -- Until multi-snapshot history accrues, transitions are all zero;
        -- fall back to the registry first-post-date proxy (labeled below).
        case
            when h.has_multi_snapshot_history then c.new_recruiting_90d
            else c.newly_posted_90d_proxy
        end as recent_growth_input,
        c.sponsor_count,
        c.top_sponsor_share,
        c.sponsor_hhi,
        c.competition_signal_band,
        s.site_overlap_share,
        s.record_quality_ok_share,
        0.5 * coalesce(s.record_quality_ok_share, 0)
            + 0.5 * coalesce(r.usable_location_share, 0)
            as data_confidence_input
    from competition c
    inner join segment_trials s
        using (condition_group, state_normalized, phase_normalized)
    cross join history_depth h
    cross join run_reliability r
),

normalized as (
    select
        *,
        coalesce({{ safe_divide(
            'recruiting_trial_count - min(recruiting_trial_count) over ()',
            'max(recruiting_trial_count) over ()'
            ' - min(recruiting_trial_count) over ()',
        ) }}, 0) as normalized_recruiting_trial_count,
        coalesce({{ safe_divide(
            'recent_growth_input - min(recent_growth_input) over ()',
            'max(recent_growth_input) over ()'
            ' - min(recent_growth_input) over ()',
        ) }}, 0) as normalized_recent_recruiting_growth,
        coalesce({{ safe_divide(
            'sponsor_hhi - min(sponsor_hhi) over ()',
            'max(sponsor_hhi) over () - min(sponsor_hhi) over ()',
        ) }}, 0) as normalized_sponsor_concentration,
        coalesce({{ safe_divide(
            'site_overlap_share - min(site_overlap_share) over ()',
            'max(site_overlap_share) over ()'
            ' - min(site_overlap_share) over ()',
        ) }}, 0) as normalized_site_overlap,
        coalesce({{ safe_divide(
            'data_confidence_input - min(data_confidence_input) over ()',
            'max(data_confidence_input) over ()'
            ' - min(data_confidence_input) over ()',
        ) }}, 0) as normalized_data_confidence_adjustment
    from inputs
),

scored as (
    select
        n.*,
        round(
            w.w_density * n.normalized_recruiting_trial_count
            + w.w_growth * n.normalized_recent_recruiting_growth
            + w.w_concentration * n.normalized_sponsor_concentration
            + w.w_overlap * n.normalized_site_overlap
            + w.w_confidence * n.normalized_data_confidence_adjustment,
            4
        ) as feasibility_review_priority_score
    from normalized n
    cross join weights w
)

select
    {{ generate_surrogate_key([
        'condition_group', 'state_normalized', 'phase_normalized',
        'snapshot_date',
    ]) }} as priority_queue_key,
    snapshot_date,
    condition_group,
    state_normalized,
    phase_normalized,
    feasibility_review_priority_score,
    case
        when feasibility_review_priority_score
            >= {{ var('feasibility_band_priority_threshold') }}
            then 'priority_review'
        when feasibility_review_priority_score
            >= {{ var('feasibility_band_review_threshold') }}
            then 'review'
        else 'watch'
    end as priority_band,
    rank() over (order by feasibility_review_priority_score desc)
        as priority_rank,
    recruiting_trial_count,
    listed_site_count,
    new_recruiting_90d,
    newly_posted_90d_proxy,
    has_multi_snapshot_history,
    recent_growth_input,
    (not has_multi_snapshot_history) as growth_uses_registry_proxy_flag,
    sponsor_count,
    top_sponsor_share,
    sponsor_hhi,
    competition_signal_band,
    site_overlap_share,
    record_quality_ok_share,
    data_confidence_input as data_confidence_share,
    normalized_recruiting_trial_count,
    normalized_recent_recruiting_growth,
    normalized_sponsor_concentration,
    normalized_site_overlap,
    normalized_data_confidence_adjustment,
    -- Deterministic explanation assembled from fixed component phrases.
    concat_ws(
        '; ',
        recruiting_trial_count || ' recruiting listing(s) in segment ('
            || case
                when normalized_recruiting_trial_count >= 0.7 then 'high'
                when normalized_recruiting_trial_count >= 0.4 then 'moderate'
                else 'low'
            end || ' relative density)',
        case
            when growth_uses_registry_proxy_flag then
                newly_posted_90d_proxy
                || ' first posted within 90 days (registry-date proxy;'
                || ' snapshot history not yet accrued)'
            else new_recruiting_90d
                || ' newly recruiting in 90 days (snapshot transitions)'
        end,
        'sponsor concentration HHI ' || round(sponsor_hhi, 2)
            || ' across ' || sponsor_count || ' sponsor(s)',
        round(coalesce(site_overlap_share, 0) * 100)
            || '% of trials share a multi-trial facility listing',
        'data confidence ' || round(data_confidence_share * 100) || '%'
    ) as priority_explanation,
    'Potential competition signal from public registry listings.'
        || ' Not a recruitment forecast; requires human feasibility review.'
        as interpretation_note
from scored
