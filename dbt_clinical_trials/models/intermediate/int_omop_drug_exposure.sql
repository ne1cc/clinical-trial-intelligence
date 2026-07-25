-- OMOP CDM-inspired drug/procedure exposure mapping.
-- Grain: nct_id + intervention_name + ingestion_run_id.
-- Maps trial interventions to RxNorm/SNOMED concepts via name pattern matching.
with best_match as (
    select
        i.ingestion_run_id,
        i.nct_id,
        i.intervention_name,
        i.intervention_type,
        i.intervention_normalized,
        dc.omop_concept_id,
        dc.omop_concept_name,
        dc.omop_vocabulary,
        dc.omop_domain,
        dc.intervention_name_pattern,
        row_number() over (
            partition by i.ingestion_run_id, i.nct_id, i.intervention_name
            order by length(dc.intervention_name_pattern) desc
        ) as match_rank
    from {{ ref('stg_trial_interventions') }} i
    left join {{ ref('omop_drug_concepts') }} dc
        on i.intervention_type = dc.intervention_type
        and lower(i.intervention_name) like '%' || dc.intervention_name_pattern || '%'
)
select
    ingestion_run_id,
    nct_id,
    intervention_name,
    intervention_type,
    intervention_normalized,
    coalesce(omop_concept_id, 0) as drug_concept_id,
    coalesce(omop_concept_name, 'Unmapped intervention') as drug_concept_name,
    coalesce(omop_vocabulary, 'None') as drug_vocabulary,
    coalesce(omop_domain, 'Drug') as drug_domain,
    (omop_concept_id is not null) as concept_mapped_flag
from best_match
where match_rank = 1
