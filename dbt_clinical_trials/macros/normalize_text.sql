{#- Mirrors src/utils/text.py normalize_text: lowercase, apostrophes removed,
    punctuation to spaces, whitespace collapsed, empty -> null. -#}
{% macro normalize_text(column) %}
    nullif(
        trim(
            regexp_replace(
                regexp_replace(
                    lower(replace(replace({{ column }}, chr(8217), ''), '''', '')),
                    '[^a-z0-9]+', ' ', 'g'
                ),
                '\s+', ' ', 'g'
            )
        ),
        ''
    )
{% endmacro %}
