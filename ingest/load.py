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
REQUIRED = ["usage_date", "api_key_id", "model", "tokens", "cost_usd"]


def check_columns(files: list[Path]) -> None:
    for path in files:
        with path.open() as f:
            header = next(csv.reader(f))
        missing = [c for c in REQUIRED if c not in header]
        if missing:
            raise SystemExit(f"{path.name}: missing column(s) {', '.join(missing)}; found {', '.join(header)}")


def dedupe_by_day(files: list[Path]) -> list[Path]:
    """Keep one file per usage day. Several files can land for the same day (e.g. a
    retry after a failed feed), named "YYYY-MM-DD.csv" (the plain, original feed) or
    "YYYY-MM-DD-<suffix>.csv" (a corrected or retried landing for that day). A
    suffixed file always supersedes the plain one for its day, since it represents a
    later correction; otherwise both would be loaded and the day's cost
    double-counted. If more than one suffixed file lands for the same day, the one
    that sorts last by filename wins, since filenames are the only ordering signal
    available (e.g. "-retry2" after "-retry").
    """
    by_day: dict[str, Path] = {}
    for f in sorted(files):
        day = f.name[:10]
        is_plain = f.name == f"{day}.csv"
        current = by_day.get(day)
        if current is None or not (is_plain and current.name != f"{day}.csv"):
            by_day[day] = f
    return [by_day[day] for day in sorted(by_day)]


def load(db: str, landing: Path, reference: Path, through: str | None = None) -> int:
    files = sorted(landing.glob("*.csv"))
    if through:
        files = [f for f in files if f.name[:10] <= through]
    if not files:
        raise SystemExit("no landing files to load")
    files = dedupe_by_day(files)
    check_columns(files)

    con = duckdb.connect(db)
    con.execute("create schema if not exists raw")
    con.execute("create schema if not exists finance")
    file_list = ", ".join(f"'{f}'" for f in files)
    con.execute(f"""
        create or replace table raw.azure_openai_usage as
        select usage_date::date as usage_date, api_key_id, model, tokens::bigint as tokens,
               cost_usd::decimal(12, 2) as cost_usd,
               regexp_extract(filename, '([^/]+)\\.csv$', 1) as _load_id
        from read_csv([{file_list}], filename = true, header = true, all_varchar = true)
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
