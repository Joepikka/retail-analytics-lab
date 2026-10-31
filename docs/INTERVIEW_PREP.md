# Interview prep: Retail Analytics Lab

Work through this before you list the project on your resume. Budget about 3 hours. Interviewers will ask you to explain or rewrite parts of this project. If you can't, it does more harm than good.

## 1. The 60-second pitch

> "I built an end-to-end analytics pipeline on 110 million e-commerce events, 4.6 GB compressed, from a multi-category online store. Python loads the raw CSVs into typed Parquet, and SQL in DuckDB models them into a star schema with a fact table for events, a fact table for sessions, and dimensions for products, users and dates. On top of that I built analysis tables for the funnel, cohort retention, repeat buyers and brand concentration, plus 14 data tests that reconcile row counts and revenue from the raw files to every output.
>
> The most useful finding was a data problem. Purchase tracking stopped for most of 14–17 November while page views kept arriving. If you don't catch that, weekends look 53% better than weekdays. With those days excluded, there's no real difference. I added an automatic check for it.
>
> On the business side, electronics is 76% of revenue, Apple and Samsung are 67%, and 42% of buyers produce 79% of revenue. I also designed an A/B test using the real baseline conversion, and built a revenue forecast that only slightly beats a seasonal-naive baseline. I say that openly in the memo."

Practise it out loud until it takes under 70 seconds.

## 2. How each part works

### Ingestion: `pipeline/01_ingest.py`
- DuckDB reads the gzip CSV directly with **explicit column types**, so nothing is guessed.
- It parses `event_time` from text like `2019-10-01 00:00:00 UTC` and writes zstd-compressed Parquet. That turns 1.74 GB of gzip into 0.72 GB of Parquet.
- **Idempotent:** it stores each raw file's SHA-256 hash and row count in `data/manifest.json`. On a rerun, an unchanged file is skipped.
- **Atomic write:** it writes to `.tmp` first and then renames, so a crash never leaves a half-written file.

### Cleaning: `sql/01_quality_and_clean.sql`
- `dq_summary` counts the problems in the data before anything is changed.
- `SELECT DISTINCT` removes exact duplicates: 130,739 rows, of which 126,985 were cart events.
- Missing category or brand becomes `'unknown'`. These are real events, so dropping them would understate traffic.
- A price of 0 or less is flagged and excluded from revenue, but the event is kept.

### Star schema: `sql/02_star_schema.sql`
- **Grain** is the key word. `fact_events` has one row per event. `fact_sessions` has one row per session.
- `dim_product` uses `arg_max(category_code, event_time)`, which takes the most recent value when a product's category changed.
- `dim_date` is generated with `range()`, so dates with no events still exist.

### Marts: `sql/03_marts.sql`. Know these four queries cold.
1. **Rolling 7-day average:** `avg(revenue) OVER (ORDER BY date_key ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)`.
2. **Cohort retention:**
   - Find each user's first purchase week with `min(purchase_week) OVER (PARTITION BY user_id)`.
   - Compute weeks since that first week with `date_diff('week', ...)`.
   - Count buyers per (cohort, weeks since).
   - Divide by the week-0 count, taken with `first_value(...) OVER (PARTITION BY cohort_week ORDER BY weeks_since_first)`.
3. **Pareto:** a running sum `sum(revenue) OVER (ORDER BY revenue DESC ROWS UNBOUNDED PRECEDING)` divided by the total, `sum(revenue) OVER ()`.
4. **Repurchase gap:** `lag(purchase_date) OVER (PARTITION BY user_id ORDER BY purchase_date)`, then the difference in days.

### Tracking-gap detection: also in `sql/03_marts.sql`
- Any hour with more than 10,000 events and 0 purchases is flagged. That found 48 hours on 14–17 Nov.
- Days with a gap are excluded from conversion, the weekday/weekend comparison, the hour heatmap, the A/B baseline and the forecast. They stay in revenue totals, because that money was real, just logged late.

### Data tests: `pipeline/03_data_tests.py`
- **Revenue reconciliation**, the one to explain: *raw purchase revenue − revenue in removed duplicates = revenue in `fact_events`*, to within $0.01. Every summary table must then add back up to that same total. If any join drops or duplicates rows, a test fails.
- The script exits with code 1 on failure, so a scheduler or CI job would stop.

### A/B test: `pipeline/05_ab_test_simulation.py`
- **Sample size** per arm for a two-proportion test: about (z₁₋α/₂·√(2p̄(1−p̄)) + z₁₋β·√(p₁(1−p₁)+p₂(1−p₂)))² / (p₂−p₁)². With a 5.96% baseline, a 5% relative MDE, α = 0.05 and 80% power, that is 101,365 sessions per arm.
- **Minimum 14 days**, even though traffic would fill the sample in one, so weekday patterns are balanced.
- **SRM check:** a chi-square test that the 50/50 split held. A failed SRM means the assignment is broken, so you don't trust the result.
- **A/A test:** both arms are identical, and it should not be significant. Here p = 0.88.
- It is **simulated**. Never claim it as a real experiment result.

### Forecast: `pipeline/06_forecast.py`
- Train on 1 Oct – 13 Nov, then forecast 18–30 Nov from that one point. That's a chronological split, which means no leakage from the future.
- The models are a naive last value, a seasonal naive (same weekday last week), a 28-day weekday mean, and an OLS regression with a trend term plus weekday dummies.
- Regression MAPE is 5.6% against 5.9% for seasonal naive, excluding Black Friday. **The edge is small**, so state that honestly.
- The 80% prediction interval (±1.28 × residual standard deviation) covered 85% of test days, so it is well calibrated.

## 3. Questions you will likely get

**"Why DuckDB and not PostgreSQL?"**
DuckDB is a columnar, in-process database, so analytical scans over 110M rows are fast on a laptop with no server to run. The SQL is standard and would move to BigQuery or Snowflake almost unchanged. For an application that does many small transactions, I'd use PostgreSQL.

**"What's the grain of your fact table?"**
`fact_events` has one row per cleaned event. `fact_sessions` has one row per session. Getting the grain wrong causes double counting.

**"How do you know your numbers are right?"**
Fourteen tests reconcile rows and revenue from the raw files through every table, check keys, and check ranges. The Excel Summary sheet also compares every formula result with the SQL value.

**"Tell me about a data quality issue."**
The purchase tracking gap. Views kept flowing while purchases stopped for 48 hours, and then 17 Nov showed a 15.5% conversion spike. The first clue was that the weekend effect looked too large, so I checked hourly event counts.

**"Cart abandonment is 55–74%. Is that real?"**
Not reliable for October. 54% of buying sessions in October had no cart event, against 16% in November, which points to a tracking change around 14 Oct. So I used view → purchase as the main funnel metric.

**"Correlation vs causation: can you say the November traffic caused lower conversion?"**
No. It's observational data with no traffic-source field. That's why I recommend recording the source and running a controlled test.

**"Why is MAPE a reasonable metric here, and when isn't it?"**
Daily revenue is never near zero, so percentage error is stable and easy to explain. MAPE breaks down when actual values are close to zero, and it penalises over-forecasts and under-forecasts asymmetrically.

**"What would you do with more time?"**
- Get traffic source and margin data.
- Add a promotion or holiday feature to the forecast.
- Schedule the pipeline with an alert on the tracking-gap test.
- Use more than 13 days for backtesting, with a rolling origin.

**"Did you use AI tools?"**
Answer honestly. For example: "Yes, I used an AI coding assistant to help write parts of the code. I checked every number with the reconciliation tests, and I can walk you through any query." Then be ready to prove it.

## 4. Practice exercises (do these without looking)

1. Write the query for **daily revenue with a 7-day rolling average** from `fact_events`. (15 min)
2. Write **weekly cohort retention** from `fact_events`, then compare it with `mart_cohort_retention`. (30 min)
3. Write a query for the **top 3 brands per category by revenue**, using `row_number() OVER (PARTITION BY ...)`. This isn't in the project yet. (20 min)
4. In Python, compute a **two-proportion z-test** for 1,000/20,000 vs 1,100/20,000 by hand, then check it with `two_proportion_test()`. (20 min)
5. **Explain on a whiteboard** why `Session Conversion` divides the sums instead of averaging the daily rates. (5 min)
6. **Break a test on purpose:** change `JOIN` to `LEFT JOIN` in one mart, or remove `DISTINCT`. Watch which test fails and explain why. (20 min)

To run queries yourself:

```bash
python -c "import duckdb; con = duckdb.connect('data/warehouse/retail.duckdb', read_only=True); print(con.sql('SELECT * FROM mart_repeat_buyers').df())"
```

## 5. Resume bullet (copy once you can defend it)

**Retail Analytics Lab** | Python, SQL (DuckDB), Parquet, Excel, Chart.js | [live dashboard](https://joepikka.github.io/retail-analytics-lab/dashboard/)
- Built a reproducible pipeline and star schema over 110M e-commerce events (4.6 GB). Added 14 data tests that reconcile row counts and $505M of revenue from the raw files to every output.
- Detected a 48-hour purchase-tracking outage that inflated the apparent weekend revenue effect by 53%. Added automated gap detection and excluded the affected days from conversion analysis.
- Found that 42% of buyers produce 79% of revenue and that 7 of 2,738 brands make up 80%. Wrote a decision memo with 5 recommendations, an A/B test design (101k sessions per arm, at least 14 days), and a 13-day forecast at 5.6% MAPE against a 5.9% seasonal-naive baseline.
