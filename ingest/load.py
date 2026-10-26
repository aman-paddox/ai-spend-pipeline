"""Load the landing files into the warehouse's raw tables.

The warehouse is rebuilt from the landing files on every run, so a reload is just a
run "through" a given day. A file that is missing a required column stops the load.
A day that lands more than once (e.g. a retried upload) is deduped if every copy for
that day has identical content; if the copies differ, the load stops so a person
decides which one is correct instead of silently picking one or double-counting.
"""

import argparse
import csv
import hashlib
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


def dedupe_by_date(files: list[Path]) -> list[Path]:
    """Collapse multiple landing files for the same day into one.

    Landing files are named with the day as the first 10 characters (e.g.
    "2026-08-17.csv" or "2026-08-17-retry.csv"), so a retry lands alongside the
    original instead of replacing it. If every file for a day is byte-identical,
    keep a single copy so the day isn't counted twice. If they differ, stop the
    load rather than guess which one is right.
    """
    by_date: dict[str, list[Path]] = {}
    for f in files:
        by_date.setdefault(f.name[:10], []).append(f)

    deduped = []
    for date, group in sorted(by_date.items()):
        if len(group) == 1:
            deduped.append(group[0])
            continue
        hashes = {hashlib.sha256(f.read_bytes()).hexdigest() for f in group}
        if len(hashes) > 1:
            names = ", ".join(f.name for f in sorted(group))
            raise SystemExit(f"{date}: {len(group)} landing files with different content ({names}); resolve by hand")
        plain = [f for f in group if f.name == f"{date}.csv"]
        deduped.append(plain[0] if plain else sorted(group)[0])
    return deduped


def load(db: str, landing: Path, reference: Path, through: str | None = None) -> int:
    files = sorted(landing.glob("*.csv"))
    if through:
        files = [f for f in files if f.name[:10] <= through]
    if not files:
        raise SystemExit("no landing files to load")
    files = dedupe_by_date(files)
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
