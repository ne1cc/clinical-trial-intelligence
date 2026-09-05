{% macro similarity_components() %}
    {{ return([
        'same_condition',
        'same_phase',
        'geography_overlap',
        'intervention_type_overlap',
        'study_design_match',
        'eligibility_compatible',
        'enrollment_band_match',
    ]) }}
{% endmacro %}
