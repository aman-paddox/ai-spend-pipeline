-- Use the schema as written (marts, staging) rather than dbt's default "main_marts".
{% macro generate_schema_name(custom_schema_name, node) -%}
  {{ custom_schema_name or target.schema }}
{%- endmacro %}
