"""Step 0: download the raw files with parallel HTTP range requests.

The host limits each connection to ~150 KB/s, so one stream takes hours.
Parts are resumable: rerunning continues where each part stopped.
"""
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from common import MONTHS, RAW

BASE_URL = "https://data.rees46.com/datasets/marketplace/"
PARTS = 12
BLOCK = 1024 * 1024


def remote_size(url):
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as r:
        return int(r.headers["Content-Length"])


def fetch_part(url, part_path, start, end):
    """Download bytes [start, end] into part_path, resuming from its current length."""
    expected = end - start + 1
    for attempt in range(20):
        have = part_path.stat().st_size if part_path.exists() else 0
        if have >= expected:
            return
        req = urllib.request.Request(url, headers={"Range": f"bytes={start + have}-{end}"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r, open(part_path, "ab") as f:
                while block := r.read(BLOCK):
                    f.write(block)
        except OSError as e:
            print(f"    {part_path.name}: retry {attempt + 1} after {e}", flush=True)
    raise RuntimeError(f"{part_path.name} incomplete after retries")


def download(filename):
    url = BASE_URL + filename
    target = RAW / filename
    size = remote_size(url)
    if target.exists() and target.stat().st_size == size:
        print(f"  {filename}: already complete ({size:,} bytes)")
        return
    chunk = -(-size // PARTS)
    ranges = [(i * chunk, min(size, (i + 1) * chunk) - 1) for i in range(PARTS)]
    parts = [RAW / f"{filename}.part{i:02d}" for i in range(PARTS)]
    print(f"  {filename}: {size:,} bytes in {PARTS} parts", flush=True)
    with ThreadPoolExecutor(PARTS) as pool:
        list(pool.map(lambda a: fetch_part(url, *a), [(p, s, e) for p, (s, e) in zip(parts, ranges)]))

    tmp = target.with_suffix(".gz.tmp")
    with open(tmp, "wb") as out:
        for p in parts:
            out.write(p.read_bytes())
    if tmp.stat().st_size != size:
        sys.exit(f"  {filename}: size mismatch {tmp.stat().st_size} != {size}")
    tmp.replace(target)
    for p in parts:
        p.unlink()
    print(f"  {filename}: complete", flush=True)


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    for filename in MONTHS.values():
        download(filename)


if __name__ == "__main__":
    main()
