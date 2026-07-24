-- Every trial must have at most one current record in fct_trial_snapshot.
select nct_id, count(*) as current_record_count
from {{ ref('fct_trial_snapshot') }}
where current_record_flag
group by nct_id
having count(*) > 1
