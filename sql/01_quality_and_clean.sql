-- Step 2a: data-quality audit of the staged events, then the cleaned base table.
-- Cleaning rules (documented in README "Data decisions"):
--   1. Exact duplicate rows (all 9 columns identical) are removed.
--   2. Missing category_code / brand become 'unknown' (kept: they are real events).
--   3. Events with price <= 0 are kept but flagged; revenue measures exclude them.
--   4. Events with no user_session are kept; session-level metrics skip them.
--   5. Each purchase event is one unit sold (the source has no quantity column).

CREATE OR REPLACE VIEW stg_events AS
SELECT * FROM read_parquet('data/staging/events_*.parquet');

CREATE OR REPLACE TABLE dq_summary AS
SELECT
    count(*)                                              AS staged_rows,
    count(*) FILTER (WHERE event_type = 'view')           AS view_rows,
    count(*) FILTER (WHERE event_type = 'cart')           AS cart_rows,
    count(*) FILTER (WHERE event_type = 'purchase')       AS purchase_rows,
    count(*) FILTER (WHERE event_type NOT IN ('view', 'cart', 'purchase')) AS other_event_rows,
    count(*) FILTER (WHERE category_code IS NULL)         AS missing_category_code,
    count(*) FILTER (WHERE brand IS NULL)                 AS missing_brand,
    count(*) FILTER (WHERE user_session IS NULL)          AS missing_session,
    count(*) FILTER (WHERE price <= 0)                    AS non_positive_price,
    min(event_time)                                       AS first_event,
    max(event_time)                                       AS last_event,
    sum(price) FILTER (WHERE event_type = 'purchase' AND price > 0) AS staged_purchase_revenue
FROM stg_events;

CREATE OR REPLACE TABLE events_clean AS
SELECT DISTINCT
    event_time,
    event_type,
    product_id,
    category_id,
    coalesce(category_code, 'unknown') AS category_code,
    coalesce(brand, 'unknown')         AS brand,
    price,
    user_id,
    user_session,
    price <= 0                         AS is_bad_price
FROM stg_events;

-- How many rows the de-duplication removed, by event type, so revenue can be reconciled.
CREATE OR REPLACE TABLE dq_duplicates AS
WITH staged AS (
    SELECT event_type, count(*) AS rows_staged,
           sum(price) FILTER (WHERE price > 0) AS value_staged
    FROM stg_events GROUP BY event_type
), cleaned AS (
    SELECT event_type, count(*) AS rows_clean,
           sum(price) FILTER (WHERE price > 0) AS value_clean
    FROM events_clean GROUP BY event_type
)
SELECT s.event_type, s.rows_staged, c.rows_clean,
       s.rows_staged - c.rows_clean   AS duplicate_rows_removed,
       s.value_staged - c.value_clean AS duplicate_value_removed
FROM staged s JOIN cleaned c USING (event_type);
