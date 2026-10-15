-- Daily AI spend by department and tool. Seat-based tools are monthly, so only usage-billed ones are here.
select
    u.usage_date as date,
    k.department,
    'Azure OpenAI' as tool,
    sum(u.cost_usd) as cost_usd
from {{ ref('stg_azure_openai_usage') }} u
join {{ ref('stg_api_keys') }} k using (api_key_id)
group by all
