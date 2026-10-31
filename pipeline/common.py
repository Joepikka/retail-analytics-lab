"""Shared paths and DuckDB connection settings for every pipeline step."""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
STAGING = ROOT / "data" / "staging"
WAREHOUSE_DB = ROOT / "data" / "warehouse" / "retail.duckdb"
SQL = ROOT / "sql"
REPORTS = ROOT / "reports"
MANIFEST = ROOT / "data" / "manifest.json"

# Source files: REES46 multi-category store, Open CDP project.
MONTHS = {"2019_10": "2019-Oct.csv.gz", "2019_11": "2019-Nov.csv.gz"}


def connect(db_path=WAREHOUSE_DB):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    # Machine has ~8 GB RAM: cap DuckDB and let large sorts/joins spill to disk.
    con.execute("SET memory_limit = '4GB'")
    con.execute(f"SET temp_directory = '{(ROOT / 'data' / 'tmp').as_posix()}'")
    con.execute("SET preserve_insertion_order = false")
    con.execute("SET enable_progress_bar = false")
    return con


def run_sql_file(con, path):
    print(f"  running {path.name}")
    con.execute(path.read_text(encoding="utf-8"))
