{#- ClinicalTrials.gov ages are free text like "18 Years" or "N/A".
    Extracts the leading integer; non-numeric input (missing/unbounded)
    returns null, which callers must treat as "no restriction," not
    zero. Verified: try_cast(regexp_extract('18 Years', '(\d+)', 1) as
    integer) -> 18; same on 'N/A' -> null. -#}
{% macro parse_age_years(column) %}
    try_cast(regexp_extract({{ column }}, '(\d+)', 1) as integer)
{% endmacro %}
