-- Every trial-site row must reference a trial known to dim_trial.
select f.trial_site_key, f.nct_id
from {{ ref('fct_trial_site') }} f
left join {{ ref('dim_trial') }} d using (trial_key)
where d.trial_key is null
