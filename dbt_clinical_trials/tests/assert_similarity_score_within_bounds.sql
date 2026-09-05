-- The weighted similarity score must always land in [0, 1].
select trial_similarity_key, similarity_score
from {{ ref('mart_trial_similarity') }}
where similarity_score < 0
   or similarity_score > 1
