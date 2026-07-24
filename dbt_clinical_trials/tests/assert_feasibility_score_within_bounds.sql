-- The weighted feasibility score must always land in [0, 1].
select priority_queue_key, feasibility_review_priority_score
from {{ ref('mart_feasibility_priority_queue') }}
where feasibility_review_priority_score < 0
   or feasibility_review_priority_score > 1
