"""Run the whole pipeline in order. Safe to rerun: every step is idempotent."""
import runpy
import sys
import time
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent / "pipeline"
STEPS = ["01_ingest.py", "02_build_warehouse.py", "03_data_tests.py",
         "05_ab_test_simulation.py", "04_export.py"]  # A/B before export so the dashboard gets it

sys.path.insert(0, str(PIPELINE))
for step in STEPS:
    print(f"== {step}")
    start = time.time()
    runpy.run_path(str(PIPELINE / step), run_name="__main__")
    print(f"   {time.time() - start:,.0f}s")
