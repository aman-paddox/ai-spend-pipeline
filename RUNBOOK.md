# Runbook: the AI-spend report

The report tells Leadership and Finance what the company pays for AI tools, by department and month. It is the `marts` tables in the warehouse.

## How data gets there
1. Each night a file of Azure OpenAI usage lands in `data/landing/azure_openai_usage/`, one file per day.
2. The nightly workflow (`.github/workflows/nightly.yml`) runs `ingest/load.py`, which rebuilds `raw` from every landing file, then `dbt build`, which builds `staging` and `marts` and runs the tests.
3. Seats for Microsoft 365 Copilot and GitHub Copilot, the API-key owners, and the vendors' invoices live in `data/reference/`.

| Schema | Tables |
|---|---|
| `raw` | `azure_openai_usage` (`usage_date`, `api_key_id`, `model`, `tokens`, `cost_usd`, `_load_id` = the file it came from), `api_keys`, `m365_copilot_seats`, `github_copilot_seats` |
| `finance` | `vendor_invoices` (`vendor`, `month`, `amount`) |
| `marts` | `ai_spend_daily` (`date`, `department`, `tool`, `cost_usd`), `ai_spend_monthly` (`month`, `department`, `tool`, `cost_usd`) |

## When the nightly load fails
1. Open the failed run and read the error. The loader names the file and the column it couldn't find.
2. Fix the cause in a branch and open a pull request. Its build must pass.
3. Once it's merged, reload the missed day: run the **nightly** workflow by hand with that `date`.

## Checking the report against the invoices
`finance.vendor_invoices` holds what each vendor billed per month. A month in `marts.ai_spend_monthly` should match its invoice. If it doesn't, look in `raw.azure_openai_usage` for days loaded more than once (`_load_id`).

## Working here
- Run it yourself: `pip install -r requirements.txt`, `python ingest/load.py`, `dbt build --project-dir dbt --profiles-dir dbt`, `pytest`. The warehouse is a local `warehouse.duckdb` file.
- Every change goes through a pull request. `main` can't be pushed to directly, by anyone.
- Never change a number in `marts` by hand. Fix the cause and let the pipeline rebuild it.
