# Retail Analytics Lab

An end-to-end analytics project. It processes 4.6 GB of compressed e-commerce clickstream data (about 110M events, Oct–Nov 2019) through a reproducible pipeline: ingestion and quality checks, a DuckDB star schema, SQL analysis marts with data tests, a dashboard, an Excel KPI workbook, an A/B test design, and a written decision memo.

**[Live dashboard](https://joepikka.github.io/retail-analytics-lab/dashboard/)** · **[Decision memo](reports/decision_memo.md)**

**Business questions**
1. How do traffic, conversion and revenue move over time?
2. Where in the view → cart → purchase funnel does each category lose shoppers?
3. Do first-time buyers come back, and how much revenue depends on repeat buyers?
4. How concentrated is revenue across brands?
5. How would we test a change to the checkout properly before rolling it out?
6. How well can next fortnight's daily revenue be forecast, and does a model beat simple baselines?

The answers are in [`reports/decision_memo.md`](reports/decision_memo.md).

## Data

[eCommerce behavior data from multi category store](https://www.kaggle.com/datasets/mkechinov/ecommerce-behavior-data-from-multi-category-store), from the REES46 Open CDP project. Two monthly files:

| File | Compressed | Rows |
|---|---|---|
| `2019-Oct.csv.gz` | 1.74 GB | 42,448,764 |
| `2019-Nov.csv.gz` | 2.89 GB | 67,501,979 |

Columns: `event_time` (UTC), `event_type` (view/cart/purchase), `product_id`, `category_id`, `category_code`, `brand`, `price`, `user_id`, `user_session`.

## Pipeline

```
raw .csv.gz ──01_ingest──▶ typed Parquet (zstd) ──02_build──▶ DuckDB warehouse ──03_tests──▶ pass/fail
                                                                     │
                                       05_ab_test_simulation ◀───────┤
                                                                     ▼
                                              04_export ──▶ CSV marts · Excel workbook · dashboard data
```

| Step | File | What it does |
|---|---|---|
| 0 | `pipeline/00_download.py` | Parallel, resumable range download (the host throttles single connections) |
| 1 | `pipeline/01_ingest.py` | Gzip CSV → typed Parquet. Records each file's SHA-256 and row count in `data/manifest.json`. A month is skipped when its hash is unchanged. |
| 2 | `pipeline/02_build_warehouse.py` | Runs `sql/01_quality_and_clean.sql`, `02_star_schema.sql`, `03_marts.sql` |
| 3 | `pipeline/03_data_tests.py` | 14 data tests covering row reconciliation, revenue reconciliation, keys, ranges. Exits non-zero on failure. |
| 4 | `pipeline/05_ab_test_simulation.py` | Power analysis and a **simulated** A/B test built on the real baseline conversion |
| 5 | `pipeline/06_forecast.py` | 13-day daily revenue forecast: trend + weekday regression vs three baselines, with an 80% prediction interval |
| 6 | `pipeline/04_export.py` | CSVs for Power BI/Tableau, `reports/retail_kpis.xlsx` (Tables, a SUMIFS category × month crosstab, and a Summary sheet whose Match column checks every formula against SQL), `dashboard/data.js` |

### Star schema

- `fact_events`: one row per cleaned event (grain: event)
- `fact_sessions`: one row per session, with view/cart/purchase flags and revenue
- `dim_product`: product → category code, main category, brand (latest values)
- `dim_user`: first seen, first purchase, purchase count, revenue
- `dim_date`: calendar attributes
- `mart_*`: one table per business question; `dq_*`: data-quality audit

The SQL uses CTEs, `FILTER` aggregates, and window functions: rolling averages, `rank`, `row_number`, `first_value`, `lag`, and running sums for the Pareto analysis.

## Data decisions

1. Exact duplicate rows (all nine columns identical) are removed and counted in `dq_duplicates`.
2. A missing `category_code` or `brand` becomes `unknown`. These are real events, so they are kept.
3. Events with `price <= 0` are kept but flagged, and revenue excludes them.
4. Events without `user_session` are kept, but session metrics skip them.
5. The source has no quantity column, so each purchase event counts as one unit.
6. A product's category or brand can change over time. `dim_product` keeps the most recent value.
7. Hours are UTC, as in the source. The store's local time zone is not documented.
8. Cohorts start on 1 Oct 2019, so a "first purchase" means the first purchase **seen in this window**.
9. **Tracking gaps** are detected from the data: any hour with more than 10k events but zero purchases. This finds 48 hours on 14–17 Nov 2019 (`dq_tracking_gap_hours`). Revenue totals keep those days. Conversion, the weekday/weekend comparison, the hour heatmap and the A/B baseline exclude them.
10. Cart events look under-logged before about 14 Oct 2019: 54% of October buying sessions have no cart event, against 16% in November. View → purchase is therefore the main funnel metric.

**Run time** on an 8 GB laptop: ingest about 2 min, warehouse about 13 min, tests, A/B and export about 1 min.

## Run it

```bash
pip install -r requirements.txt
python pipeline/00_download.py   # ~4.6 GB; about 1 hour with parallel parts
python run_all.py                # ingest → warehouse → tests → A/B → export
python -m http.server 8000 --directory dashboard   # open http://localhost:8000
```

Every step can be rerun safely. Ingest skips unchanged files, and all SQL uses `CREATE OR REPLACE`. DuckDB is capped at 4 GB RAM and spills to `data/tmp`, so the pipeline runs on an 8 GB laptop.

## Outputs

- `dashboard/index.html`: KPI tiles, daily revenue, category revenue and funnel, cart abandonment, cohort retention heatmap, hour × weekday conversion, repeat buyers, brand concentration, price bands, A/B design, data quality
- `reports/retail_kpis.xlsx`: Excel Tables plus a Summary sheet built with `SUMIFS`, `AVERAGEIFS`, `XLOOKUP` and `COUNTIFS`
- `reports/csv/*.csv`: every mart, ready to load into Power BI or Tableau
- `reports/decision_memo.md`: findings and recommendations
- `docs/POWER_BI_GUIDE.md`: step-by-step rebuild of the dashboard in Power BI, with the data model and DAX measures
- `docs/INTERVIEW_PREP.md`: how each part works, likely interview questions, and practice exercises

## Limitations

- Two months of data from one store, from 2019. Seasonality beyond Black Friday week cannot be judged.
- No costs or margins, so recommendations are about revenue and conversion, not profit.
- Cart events appear under-recorded relative to purchases (see the memo), so cart abandonment rates are indicative only.
- Purchase logging failed on 14–17 Nov 2019. The 17 Nov revenue spike looks like a catch-up, not real demand.
- The A/B section is a **simulation** to demonstrate test design. It is not a finding about this store.
