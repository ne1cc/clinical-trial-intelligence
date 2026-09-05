-- The five weighted score components must sum to the final displayed
-- score within a small rounding tolerance -- this is what makes the
-- score's "explainable breakdown" a verified claim, not just a UI label.
select
    priority_queue_key,
    feasibility_review_priority_score,
    weighted_recruiting_trial_count
        + weighted_recent_recruiting_growth
        + weighted_sponsor_concentration
        + weighted_site_overlap
        + weighted_data_confidence_adjustment
        as weighted_components_sum
from {{ ref('mart_feasibility_priority_queue') }}
where abs(
    feasibility_review_priority_score
    - (
        weighted_recruiting_trial_count
        + weighted_recent_recruiting_growth
        + weighted_sponsor_concentration
        + weighted_site_overlap
        + weighted_data_confidence_adjustment
    )
) > 0.001
