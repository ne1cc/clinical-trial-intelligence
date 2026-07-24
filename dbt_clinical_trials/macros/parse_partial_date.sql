{#- ClinicalTrials.gov dates may be partial: YYYY, YYYY-MM, or YYYY-MM-DD.
    Missing parts default to the first day/month (mirrors src/utils/dates.py). -#}
{% macro parse_partial_date(column) %}
    cast(
        coalesce(
            try_strptime({{ column }}, '%Y-%m-%d'),
            try_strptime({{ column }}, '%Y-%m'),
            try_strptime({{ column }}, '%Y')
        ) as date
    )
{% endmacro %}
