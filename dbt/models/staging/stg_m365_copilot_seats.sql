select month::date as month, department, seats, cost_usd::decimal(12, 2) as cost_usd
from {{ source('raw', 'm365_copilot_seats') }}
