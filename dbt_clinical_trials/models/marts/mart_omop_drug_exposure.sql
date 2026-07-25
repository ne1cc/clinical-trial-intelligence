-- OMOP CDM drug_exposure / procedure_occurrence table (adapted for registry data).
-- Grain: nct_id + intervention_name + ingestion_run_id.
-- Each row represents an intervention listed on a trial protocol mapped to an
-- RxNorm or SNOMED concept. This is a protocol listing, not a patient exposure.
select
    {{ generate_surrogate_key([
        'nct_id', 'intervention_name', 'ingestion_run_id'
    ]) }} as drug_exposure_key,
    {{ generate_surrogate_key(['nct_id']) }} as trial_key,
    nct_id as person_source_value,
    drug_concept_id,
    drug_concept_name,
    drug_vocabulary,
    drug_domain,
    intervention_name as drug_source_value,
    intervention_type,
    concept_mapped_flag,
    ingestion_run_id
from {{ ref('int_omop_drug_exposure') }}
