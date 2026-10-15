-- Monthly AI spend by department and tool: what Leadership and Finance read.
select date_trunc('month', date)::date as month, department, tool, sum(cost_usd) as cost_usd
from {{ ref('ai_spend_daily') }}
group by all

union all

select month, department, 'Microsoft 365 Copilot' as tool, cost_usd
from {{ ref('stg_m365_copilot_seats') }}
