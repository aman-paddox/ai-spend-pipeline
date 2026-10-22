import duckdb
import pytest

from ingest.load import load

HEADER = ["usage_date", "api_key_id", "model", "tokens", "cost_usd"]


def write(path, header, rows):
    import csv

    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


@pytest.fixture
def dirs(tmp_path):
    landing = tmp_path / "landing"
    landing.mkdir()
    reference = tmp_path / "reference"
    reference.mkdir()
    write(reference / "api_keys.csv", ["api_key_id", "department"], [["key-a", "Eng"]])
    write(
        reference / "vendor_invoices.csv",
        ["vendor", "invoice_month", "amount_usd"],
        [["Azure OpenAI", "2026-07-01", "1060.31"]],
    )
    db = str(tmp_path / "warehouse.duckdb")
    return landing, reference, db


def test_loading_all_files_sums_every_row(dirs):
    landing, reference, db = dirs
    write(landing / "2026-07-01.csv", HEADER, [["2026-07-01", "key-a", "gpt-4o", 1000, "0.50"]])
    write(landing / "2026-07-02.csv", HEADER, [["2026-07-02", "key-a", "gpt-4o", 2000, "1.00"]])
    assert load(db, landing, reference) == 2


def test_through_only_loads_files_up_to_that_date(dirs):
    landing, reference, db = dirs
    write(landing / "2026-07-01.csv", HEADER, [["2026-07-01", "key-a", "gpt-4o", 1000, "0.50"]])
    write(landing / "2026-07-02.csv", HEADER, [["2026-07-02", "key-a", "gpt-4o", 2000, "1.00"]])
    assert load(db, landing, reference, through="2026-07-01") == 1


def test_a_file_missing_a_column_stops_the_load_and_says_which(dirs):
    landing, reference, db = dirs
    renamed = ["usage_date", "api_key_id", "model", "tokens", "cost"]
    write(landing / "2026-07-01.csv", renamed, [["2026-07-01", "key-a", "gpt-4o", 1000, "0.50"]])
    with pytest.raises(SystemExit, match="missing column.*cost_usd"):
        load(db, landing, reference)


def test_a_retry_file_replaces_the_original_for_that_day(dirs):
    landing, reference, db = dirs
    write(landing / "2026-07-01.csv", HEADER, [["2026-07-01", "key-a", "gpt-4o", 1000, "0.50"]])
    write(landing / "2026-07-01-retry.csv", HEADER, [["2026-07-01", "key-a", "gpt-4o", 1000, "0.75"]])
    assert load(db, landing, reference) == 1
    cost = duckdb.connect(db).execute("select cost_usd from raw.azure_openai_usage").fetchone()[0]
    assert float(cost) == 0.75
