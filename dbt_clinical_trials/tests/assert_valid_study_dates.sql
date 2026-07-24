-- Registry data can legitimately contain odd dates; warn, don't fail.
{{ config(severity='warn') }}

select nct_id, ingestion_run_id, start_date, completion_date
from {{ ref('stg_trials') }}
where start_date is not null
  and completion_date is not null
  and start_date > completion_date
