-- A resent landing file for a day already loaded must replace that day's rows, not add to
-- them. This fails if stg_azure_openai_usage ever has more than one row for the same
-- (usage_date, api_key_id, model), which is what caused August's Azure OpenAI spend to be
-- double-counted after a retry file landed for 2026-08-17.
select usage_date, api_key_id, model, count(*) as n
from {{ ref('stg_azure_openai_usage') }}
group by all
having count(*) > 1
