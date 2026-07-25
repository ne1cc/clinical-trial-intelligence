-- One row per NCT ID + criterion index + ingestion run.
-- Structured eligibility criteria parsed from free-text in silver.
select
    ingestion_run_id,
    nct_id,
    criterion_index,
    direction,
    criterion_type,
    criterion_text,
    section_label,
    parse_quality,
    source_json_hash
from {{ source('silver', 'silver_trial_eligibility_criteria') }}
where nct_id is not null
