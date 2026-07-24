-- Deliberately empty by design (clinical interpretation guardrail):
-- site contacts, emails, phone numbers, and investigator names are never
-- extracted from the registry payload and never surfaced in this project.
-- This model exists so the guardrail is explicit and testable.
select
    cast(null as varchar) as ingestion_run_id,
    cast(null as varchar) as nct_id,
    cast(null as varchar) as contact_role,
    cast(null as varchar) as excluded_reason
where 1 = 0
