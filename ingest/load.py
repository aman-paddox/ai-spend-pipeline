from __future__ import annotations

import argparse
import csv
from pathlib import Path

import duckdb

REQUIRED_COLUMNS = ["usage_date", "api_key_id", "model", "tokens", "cost_usd"]


def check_columns(files: list[Path]) -> None:
    for path in files:
        with open(path, newline="") as fh:
            header = next(csv.reader(fh))
        missing = [c for c in REQUIRED_COLUMNS if c not in header]
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
    con.execute(
        """
        create or replace table raw.azure_openai_usage as
        select *, filename as _load_id
        from read_csv_auto(?, union_by_name=true, filename=true)
        """,
        [[str(f) for f in files]],
    )
    row_count = con.execute("select count(*) from raw.azure_openai_usage").fetchone()[0]

    con.execute("create schema if not exists ref")
    con.execute(
        "create or replace table ref.api_keys as select * from read_csv_auto(?)",
        [str(reference / "api_keys.csv")],
    )
    con.execute(
        "create or replace table ref.vendor_invoices as select * from read_csv_auto(?)",
        [str(reference / "vendor_invoices.csv")],
    )
    con.close()
    return row_count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="warehouse.duckdb")
    parser.add_argument("--landing", default="data/landing/azure_openai_usage")
    parser.add_argument("--reference", default="data/reference")
    parser.add_argument("--through", default=None, help="Only load files with date prefix <= this value (YYYY-MM-DD)")
    args = parser.parse_args()

    n = load(args.db, Path(args.landing), Path(args.reference), args.through)
    print(f"loaded {n} Azure OpenAI rows")


if __name__ == "__main__":
    main()
