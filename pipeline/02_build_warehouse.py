"""Step 2: build the DuckDB warehouse (quality audit, star schema, marts) from staged Parquet.

Every statement is CREATE OR REPLACE, so a rerun rebuilds the same tables.
"""
import os
import time

from common import ROOT, SQL, connect, run_sql_file


def main():
    os.chdir(ROOT)  # SQL files use project-relative paths
    con = connect()
    for name in ["01_quality_and_clean.sql", "02_star_schema.sql", "03_marts.sql"]:
        start = time.time()
        run_sql_file(con, SQL / name)
        print(f"    done in {time.time() - start:,.0f}s")
    con.close()


if __name__ == "__main__":
    main()
