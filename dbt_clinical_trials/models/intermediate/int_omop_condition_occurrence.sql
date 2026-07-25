-- OMOP CDM-inspired condition_occurrence mapping.
-- Grain: nct_id + condition_raw + ingestion_run_id.
-- Maps trial conditions to SNOMED CT concepts via the condition_group taxonomy.
select
    c.ingestion_run_id,
    c.nct_id,
    c.condition_raw,
    c.condition_group,
    c.mapping_confidence,
    coalesce(oc.omop_concept_id, 0) as condition_concept_id,
    coalesce(oc.omop_concept_name, 'Unmapped condition') as condition_concept_name,
    coalesce(oc.snomed_code, '0') as condition_source_value,
    'SNOMED' as condition_vocabulary,
    'Condition' as condition_domain,
    c.dementia_relevance_flag
from {{ ref('stg_trial_conditions') }} c
left join {{ ref('omop_condition_concepts') }} oc
    on c.condition_group = oc.condition_group
