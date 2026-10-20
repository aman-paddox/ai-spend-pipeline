import csv
from pathlib import Path

import duckdb
import pytest

from ingest.load import load

HEADER = ["usage_date", "api_key_id", "model", "tokens", "cost_usd"]


def write(path: Path, header, rows):
    with path.open("w", newline="") as f:
        csv.writer(f).writerows([header, *rows])


@pytest.fixture
def dirs(tmp_path):
    landing, reference = tmp_path / "landing", tmp_path / "reference"
    landing.mkdir()
    reference.mkdir()
    write(reference / "api_keys.csv", ["api_key_id", "department"], [["key-a", "Sales"]])
    for name in ["m365_copilot_seats.csv", "github_copilot_seats.csv"]:
        write(reference / name, ["month", "department", "seats", "cost_usd"], [["2026-07-01", "Sales", 1, "30.00"]])
    write(reference / "vendor_invoices.csv", ["vendor", "month", "amount"], [["Azure OpenAI", "2026-07-01", "1.00"]])
    return landing, reference, str(tmp_path / "w.duckdb")


def test_loads_every_day_and_tags_each_row_with_its_file(dirs):
    landing, reference, db = dirs
    write(landing / "2026-07-01.csv", HEADER, [["2026-07-01", "key-a", "gpt-4o", 1000, "0.50"]])
    write(landing / "2026-07-02.csv", HEADER, [["2026-07-02", "key-a", "gpt-4o", 2000, "1.00"]])
    assert load(db, landing, reference) == 2
    ids = duckdb.connect(db).execute("select _load_id from raw.azure_openai_usage order by 1").fetchall()
    assert ids == [("2026-07-01",), ("2026-07-02",)]


def test_through_stops_at_the_given_day(dirs):
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


def test_a_retry_file_replaces_the_original_for_that_day_instead_of_adding_to_it(dirs):
    landing, reference, db = dirs
    write(landing / "2026-07-01.csv", HEADER, [["2026-07-01", "key-a", "gpt-4o", 1000, "0.50"]])
    write(landing / "2026-07-01-retry.csv", HEADER, [["2026-07-01", "key-a", "gpt-4o", 1000, "0.50"]])
    assert load(db, landing, reference) == 1
    ids = duckdb.connect(db).execute("select _load_id from raw.azure_openai_usage order by 1").fetchall()
    assert ids == [("2026-07-01-retry",)]
