# ai-spend-pipeline

Data pipeline for the AI-spend report: what the company pays for AI tools (Azure OpenAI, Microsoft 365 Copilot, GitHub Copilot), by department and month. Finance and leadership read the `marts` tables.

## Layout

```
data/
  landing/azure_openai_usage/   one CSV of Azure OpenAI usage per day
  reference/                    API-key owners, Copilot seats, vendor invoices
ingest/load.py                  loads the CSVs into the warehouse's raw and finance schemas
dbt/                            staging and mart models, with tests
tests/                          pytest suite for the loader
.github/workflows/
  build.yml                     runs on every pull request
  nightly.yml                   the nightly load
```

## How it fits together

1. `ingest/load.py` rebuilds `raw` from every file in `data/landing/` (or up to `--through YYYY-MM-DD`) and loads `data/reference/`.
2. `dbt build` builds `staging` and `marts` from `raw` and runs the model tests.

| Schema | Tables |
|---|---|
| `raw` | `azure_openai_usage` (`usage_date`, `api_key_id`, `model`, `tokens`, `cost_usd`, `_load_id`: the file a row came from), `api_keys`, `m365_copilot_seats`, `github_copilot_seats` |
| `finance` | `vendor_invoices` (`vendor`, `month`, `amount`) |
| `marts` | `ai_spend_daily` (`date`, `department`, `tool`, `cost_usd`), `ai_spend_monthly` (`month`, `department`, `tool`, `cost_usd`) |

The warehouse is a local DuckDB file, `warehouse.duckdb`.

## Running locally

```sh
pip install -r requirements.txt
python ingest/load.py
dbt build --project-dir dbt --profiles-dir dbt
pytest
```

## CI

- **build** runs the loader, `dbt build` and `pytest` on every pull request.
- **nightly** runs the load and `dbt build`. It also runs by hand, with an optional `date` input to load up to that day. Failures post to Slack when `SLACK_WEBHOOK_URL` is set.

## Contributing

`main` is protected: changes go through a pull request, and `build` must pass. Report numbers come from the pipeline; don't edit them by hand.
