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
    """Keep one file per usage day.

    A day can land more than once, e.g. "2026-08-17.csv" and a later correction
    "2026-08-17-retry.csv" that re-sends the whole day. Both carry a full day's rows, so
    loading both double-counts that day. Group by the day prefix (first 10 chars of the
    filename) and keep only the most recently landed file (by mtime), since a correction
    always lands after the file it replaces. Ties (e.g. both checked out together, so mtimes
    match) fall back to the longer filename, since the bare "YYYY-MM-DD.csv" is always the
    original and any suffixed variant ("-retry", "-corrected", ...) is the replacement.
    """
    by_day: dict[str, Path] = {}
    for f in sorted(files, key=lambda p: (p.stat().st_mtime, len(p.name), p.name)):
        day = f.name[:10]
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
