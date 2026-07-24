-- U.S.-scope models must only contain normalized two-letter state codes.
-- (Normalization against config/geography_rules.yml happens upstream in
-- Python; this guards the contract at the mart boundary.)
select trial_site_key, nct_id, state_normalized
from {{ ref('fct_trial_site') }}
where state_normalized is null
   or not regexp_matches(state_normalized, '^[A-Z]{2}$')
