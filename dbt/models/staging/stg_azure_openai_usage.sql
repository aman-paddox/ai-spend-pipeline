-- A day's usage can be re-sent (e.g. a retry after a partial or failed upload). When that
-- happens we get two landing files for the same usage_date, and without this, both get
-- summed and the day is double-counted. Keep one row per (usage_date, api_key_id, model),
-- the one from the most recently landed file (max _load_id), so a resend replaces the
-- original rather than adding to it.
select usage_date, api_key_id, model, tokens, cost_usd, _load_id
from {{ source('raw', 'azure_openai_usage') }}
qualify row_number() over (
    partition by usage_date, api_key_id, model
    order by _load_id desc
) = 1
