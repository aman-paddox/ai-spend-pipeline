"""Load the landing files into the warehouse's raw tables.

The warehouse is rebuilt from the landing files on every run, so a reload is just a
run "through" a given day. A file that is missing a required column stops the load.
"""

import argparse
import csv
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = ["usage_date", "api_key_id", "model", "tokens"]
COST_COLUMNS = ["cost_usd", "cost"]  # Azure renamed cost_usd -> cost from 2026-09-29 onward


def check_columns(files: list[Path]) -> None:
    for path in files:
        with path.open() as f:
            header = next(csv.reader(f))
        missing = [c for c in REQUIRED if c not in header]
        if not any(c in header for c in COST_COLUMNS):
            missing.append("/".join(COST_COLUMNS))
        if missing:
            raise SystemExit(f"{path.name}: missing column(s) {', '.join(missing)}; found {', '.join(header)}")


def load(db: str, landing: Path, reference: Path, through: str | None = None) -> int:
    files = sorted(landing.glob("*.csv"))
    if through:
        files = [f for f in files if f.name[:10] <= through]
    if not files:
        raise SystemExit("no landing files to load")
    check_columns(files)

    present_cost_columns = []
    for col in COST_COLUMNS:
        for path in files:
            with path.open() as f:
                if col in next(csv.reader(f)):
                    present_cost_columns.append(col)
                    break
    cost_expr = "coalesce(" + ", ".join(f"try_cast(src.{c} as decimal(12, 2))" for c in present_cost_columns) + ")"

    con = duckdb.connect(db)
    con.execute("create schema if not exists raw")
    con.execute("create schema if not exists finance")
    file_list = ", ".join(f"'{f}'" for f in files)
    con.execute(f"""
        create or replace table raw.azure_openai_usage as
        select usage_date::date as usage_date, api_key_id, model, tokens::bigint as tokens,
               {cost_expr} as cost_usd,
               regexp_extract(filename, '([^/]+)\\.csv$', 1) as _load_id
        from read_csv([{file_list}], filename = true, header = true, all_varchar = true, union_by_name = true) as src
    """)
    for table, file in [
        ("raw.api_keys", "api_keys.csv"),
        ("raw.m365_copilot_seats", "m365_copilot_seats.csv"),
        ("raw.github_copilot_seats", "github_copilot_seats.csv"),
        ("finance.vendor_invoices", "vendor_invoices.csv"),
    ]:
        con.execute(f"create or replace table {table} as select * from read_csv_auto('{reference / file}')")
    count = con.execute("select count(*) from raw.azure_openai_usage").fetchone()[0]
    con.close()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--through", help="load days up to and including this date (YYYY-MM-DD)")
    parser.add_argument("--db", default=str(ROOT / "warehouse.duckdb"))
    args = parser.parse_args()
    rows = load(args.db, ROOT / "data" / "landing" / "azure_openai_usage", ROOT / "data" / "reference", args.through)
    print(f"loaded {rows} Azure OpenAI rows" + (f" through {args.through}" if args.through else ""))


if __name__ == "__main__":
    sys.exit(main())
