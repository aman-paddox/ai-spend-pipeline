"""Load the landing files into the warehouse's raw tables.

The warehouse is rebuilt from the landing files on every run, so a reload is just a
run "through" a given day. A file that is missing a required column stops the load.

A corrected day lands as an extra file that shares the same YYYY-MM-DD date prefix
(for example a "-retry" suffix). Only the latest-landed file for a date is loaded;
the earlier one is kept on disk for the record but is not summed in, so a retry
replaces a day's usage instead of adding to it.
"""

import argparse
import csv
import re
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = ["usage_date", "api_key_id", "model", "tokens", "cost_usd"]
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(.*)\.csv$")


def latest_files(landing: Path) -> list[Path]:
    """One file per usage date: the latest-landed file wins.

    Files for the same date are distinguished by what follows the date in the
    filename (the empty suffix for the original file, "-retry" and similar for
    a correction). The suffix that sorts last wins, so "-retry" beats the
    original and "-retry2" would beat "-retry".
    """
    by_date: dict[str, Path] = {}
    suffix_of: dict[str, str] = {}
    for f in sorted(landing.glob("*.csv")):
        m = DATE_RE.match(f.name)
        if not m:
            raise SystemExit(f"{f.name}: landing filename must start with YYYY-MM-DD")
        date, suffix = m.groups()
        if date not in by_date or suffix > suffix_of[date]:
            by_date[date] = f
            suffix_of[date] = suffix
    return [by_date[d] for d in sorted(by_date)]


def check_columns(files: list[Path]) -> None:
    for path in files:
        with path.open() as f:
            header = next(csv.reader(f))
        missing = [c for c in REQUIRED if c not in header]
        if missing:
            raise SystemExit(f"{path.name}: missing column(s) {', '.join(missing)}; found {', '.join(header)}")


def load(db: str, landing: Path, reference: Path, through: str | None = None) -> int:
    files = latest_files(landing)
    if through:
        files = [f for f in files if f.name[:10] <= through]
    if not files:
        raise SystemExit("no landing files to load")
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
