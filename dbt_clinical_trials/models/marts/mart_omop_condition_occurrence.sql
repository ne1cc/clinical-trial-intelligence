-- OMOP CDM condition_occurrence table (adapted for clinical trial registry data).
-- Grain: nct_id + condition_raw + ingestion_run_id.
-- Each row represents a condition listed on a trial protocol mapped to a
-- SNOMED CT concept. This is a registry-listing signal, not a patient diagnosis.
select
    {{ generate_surrogate_key([
        'nct_id', 'condition_raw', 'ingestion_run_id'
    ]) }} as condition_occurrence_key,
    {{ generate_surrogate_key(['nct_id']) }} as trial_key,
    nct_id as person_source_value,
    condition_concept_id,
    condition_concept_name,
    condition_source_value,
    condition_vocabulary,
    condition_domain,
    condition_group,
    mapping_confidence,
    dementia_relevance_flag,
    ingestion_run_id
from {{ ref('int_omop_condition_occurrence') }}
