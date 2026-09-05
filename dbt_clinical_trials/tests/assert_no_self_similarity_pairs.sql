-- A trial must never be listed as comparable to itself.
select trial_similarity_key, nct_id_a, nct_id_b
from {{ ref('mart_trial_similarity') }}
where nct_id_a = nct_id_b
