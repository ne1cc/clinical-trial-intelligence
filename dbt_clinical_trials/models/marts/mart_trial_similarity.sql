-- Deterministic trial-pair comparability. Grain: one row per
-- (nct_id_a, nct_id_b) pair, where nct_id_b is one of nct_id_a's top-25
-- most comparable trials. A structural/design comparability signal --
-- NOT a claim of clinical equivalence, and NOT itself a competition or
-- recruitment signal. Weights live in the similarity_score_weights seed
-- (mirrored in config/similarity_weights.yml).
with weights as (
    select
        max(case when component = 'same_condition' then weight end) as w_condition,
        max(case when component = 'same_phase' then weight end) as w_phase,
        max(case when component = 'geography_overlap' then weight end) as w_geography,
        max(case when component = 'intervention_type_overlap' then weight end) as w_intervention,
        max(case when component = 'study_design_match' then weight end) as w_design,
        max(case when component = 'eligibility_compatible' then weight end) as w_eligibility,
        max(case when component = 'enrollment_band_match' then weight end) as w_enrollment
    from {{ ref('similarity_score_weights') }}
),

pairs as (
    select
        a.nct_id as nct_id_a,
        b.nct_id as nct_id_b,
        a.phase_normalized as a_phase, b.phase_normalized as b_phase,
        a.enrollment_band as a_enrollment_band, b.enrollment_band as b_enrollment_band,
        case when len(list_intersect(a.condition_groups, b.condition_groups)) > 0
            then 1 else 0 end as same_condition,
        case when a.phase_normalized = b.phase_normalized
            then 1 else 0 end as same_phase,
        case when len(list_intersect(a.states, b.states)) > 0
            then 1 else 0 end as geography_overlap,
        case when len(list_intersect(a.intervention_types, b.intervention_types)) > 0
            then 1 else 0 end as intervention_type_overlap,
        case when a.study_type = b.study_type
            and a.allocation = b.allocation
            and a.primary_purpose = b.primary_purpose
            then 1 else 0 end as study_design_match,
        case when (a.sex = b.sex or a.sex = 'ALL' or b.sex = 'ALL')
            and a.healthy_volunteers = b.healthy_volunteers
            and (a.minimum_age_years is null or b.maximum_age_years is null
                 or a.minimum_age_years <= b.maximum_age_years)
            and (b.minimum_age_years is null or a.maximum_age_years is null
                 or b.minimum_age_years <= a.maximum_age_years)
            then 1 else 0 end as eligibility_compatible,
        case when a.enrollment_band = b.enrollment_band
            then 1 else 0 end as enrollment_band_match
    from {{ ref('int_trial_comparability_features') }} a
    inner join {{ ref('int_trial_comparability_features') }} b
        on a.nct_id != b.nct_id
),

scored as (
    select
        p.*,
        w.w_condition as weight_same_condition,
        w.w_phase as weight_same_phase,
        w.w_geography as weight_geography_overlap,
        w.w_intervention as weight_intervention_type_overlap,
        w.w_design as weight_study_design_match,
        w.w_eligibility as weight_eligibility_compatible,
        w.w_enrollment as weight_enrollment_band_match,
        round(w.w_condition * p.same_condition, 4) as weighted_same_condition,
        round(w.w_phase * p.same_phase, 4) as weighted_same_phase,
        round(w.w_geography * p.geography_overlap, 4) as weighted_geography_overlap,
        round(w.w_intervention * p.intervention_type_overlap, 4) as weighted_intervention_type_overlap,
        round(w.w_design * p.study_design_match, 4) as weighted_study_design_match,
        round(w.w_eligibility * p.eligibility_compatible, 4) as weighted_eligibility_compatible,
        round(w.w_enrollment * p.enrollment_band_match, 4) as weighted_enrollment_band_match,
        round(
            w.w_condition * p.same_condition
            + w.w_phase * p.same_phase
            + w.w_geography * p.geography_overlap
            + w.w_intervention * p.intervention_type_overlap
            + w.w_design * p.study_design_match
            + w.w_eligibility * p.eligibility_compatible
            + w.w_enrollment * p.enrollment_band_match,
            4
        ) as similarity_score
    from pairs p
    cross join weights w
)

select
    {{ generate_surrogate_key(['nct_id_a', 'nct_id_b']) }} as trial_similarity_key,
    nct_id_a,
    nct_id_b,
    similarity_score,
    row_number() over (
        partition by nct_id_a order by similarity_score desc, nct_id_b
    ) as similarity_rank,
    same_condition, weight_same_condition, weighted_same_condition,
    same_phase, weight_same_phase, weighted_same_phase,
    geography_overlap, weight_geography_overlap, weighted_geography_overlap,
    intervention_type_overlap, weight_intervention_type_overlap, weighted_intervention_type_overlap,
    study_design_match, weight_study_design_match, weighted_study_design_match,
    eligibility_compatible, weight_eligibility_compatible, weighted_eligibility_compatible,
    enrollment_band_match, weight_enrollment_band_match, weighted_enrollment_band_match,
    concat_ws(
        '; ',
        case when same_condition = 1 then 'shared condition mapping' end,
        case when same_phase = 1 then 'same phase (' || a_phase || ')' end,
        case when geography_overlap = 1 then 'overlapping U.S. states' end,
        case when intervention_type_overlap = 1 then 'shared intervention type' end,
        case when study_design_match = 1 then 'matching study type, allocation, and primary purpose' end,
        case when eligibility_compatible = 1 then 'compatible eligibility criteria' end,
        case when enrollment_band_match = 1 then 'similar enrollment size (' || a_enrollment_band || ')' end
    ) as similarity_explanation
from scored
qualify similarity_rank <= 25
