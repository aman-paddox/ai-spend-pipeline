select usage_date, api_key_id, model, tokens, cost_usd, _load_id
from {{ source('raw', 'azure_openai_usage') }}
