-- Comparable trial pairs must share the same non-null indication profile.
select trial_similarity_key, nct_id_a, nct_id_b, indication_profile_id
from {{ ref('mart_trial_similarity') }}
where indication_profile_id is null
