# AI-spend pipeline

Builds the AI-spend report: what the company pays for AI tools (Azure OpenAI, Microsoft 365 Copilot, GitHub Copilot), by department and month. Leadership and Finance read it.

- **How it works, and what to do when a load fails:** [RUNBOOK.md](RUNBOOK.md)
- **Run it locally:**
  ```sh
  pip install -r requirements.txt
  python ingest/load.py
  dbt build --project-dir dbt --profiles-dir dbt
  pytest
  ```
  The warehouse is a local `warehouse.duckdb` file.
- **Nightly load:** `.github/workflows/nightly.yml`. Run it by hand with a `date` to reload up to that day. Failures post to Slack when `SLACK_WEBHOOK_URL` is set.
- **Changes** go through a pull request; the `build` check must pass, and `main` can't be pushed to directly.
