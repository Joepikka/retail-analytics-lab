"""Step 1: raw gzip CSV -> typed Parquet staging files.

Idempotent: a month is re-staged only when its raw file hash changes.
The raw file hash and row count are written to data/manifest.json.
"""
import hashlib
import json

import duckdb

from common import MANIFEST, MONTHS, RAW, STAGING

RAW_COLUMNS = {
    "event_time": "VARCHAR",  # e.g. '2019-10-01 00:00:00 UTC', parsed below
    "event_type": "VARCHAR",
    "product_id": "BIGINT",
    "category_id": "BIGINT",
    "category_code": "VARCHAR",
    "brand": "VARCHAR",
    "price": "DOUBLE",
    "user_id": "BIGINT",
    "user_session": "VARCHAR",
}


def sha256(path, chunk=8 * 1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def stage_month(key, filename, manifest):
    raw_path = RAW / filename
    out_path = STAGING / f"events_{key}.parquet"
    if not raw_path.exists():
        raise FileNotFoundError(f"missing raw file {raw_path}; download it first (see README)")

    digest = sha256(raw_path)
    previous = manifest.get(key, {})
    if out_path.exists() and previous.get("raw_sha256") == digest:
        print(f"  {key}: unchanged, skipping ({previous['raw_rows']:,} rows)")
        return

    print(f"  {key}: staging {filename} ...")
    tmp_path = out_path.with_suffix(".parquet.tmp")
    con = duckdb.connect()
    con.execute("SET memory_limit = '4GB'")
    con.execute("SET enable_progress_bar = false")
    con.execute(f"""
        COPY (
            SELECT
                strptime(replace(event_time, ' UTC', ''), '%Y-%m-%d %H:%M:%S') AS event_time,
                event_type, product_id, category_id, category_code, brand,
                price, user_id, user_session
            FROM read_csv('{raw_path.as_posix()}', header = true, columns = {RAW_COLUMNS})
        ) TO '{tmp_path.as_posix()}' (FORMAT parquet, COMPRESSION zstd)
    """)
    rows = con.execute(f"SELECT count(*) FROM read_parquet('{tmp_path.as_posix()}')").fetchone()[0]
    con.close()
    # Write to a temp file first so a crash never leaves a half-written staging file.
    tmp_path.replace(out_path)

    manifest[key] = {"raw_file": filename, "raw_sha256": digest, "raw_rows": rows}
    MANIFEST.write_text(json.dumps(manifest, indent=2))
    print(f"  {key}: {rows:,} rows staged")


def main():
    STAGING.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    for key, filename in MONTHS.items():
        stage_month(key, filename, manifest)


if __name__ == "__main__":
    main()
