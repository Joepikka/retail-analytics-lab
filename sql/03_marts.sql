-- Step 2c: analysis marts. Each answers one business question and is exported for the dashboard.
-- Revenue = sum of purchase-event prices with price > 0 (one unit per purchase event).

-- Tracking gaps: hours with real traffic (>10k events) but zero purchases logged.
-- In this data purchase logging stops on 14-17 Nov 2019 while views continue, and
-- 17 Nov then shows a catch-up spike. Days with a gap are excluded from time comparisons.
CREATE OR REPLACE TABLE dq_tracking_gap_hours AS
SELECT date_trunc('hour', event_time) AS gap_hour, count(*) AS events
FROM fact_events
GROUP BY 1
HAVING count(*) > 10000 AND count(*) FILTER (WHERE event_type = 'purchase') = 0
ORDER BY 1;

CREATE OR REPLACE TABLE dq_tracking_gap_days AS
SELECT DISTINCT gap_hour::DATE AS date_key FROM dq_tracking_gap_hours;

-- Q1. How do traffic, conversion and revenue move day by day?
CREATE OR REPLACE TABLE mart_daily_kpis AS
WITH daily AS (
    SELECT
        s.date_key,
        count(*)                                  AS sessions,
        count(DISTINCT s.user_id)                 AS active_users,
        count(*) FILTER (WHERE s.has_purchase)    AS purchasing_sessions,
        sum(s.purchases)                          AS units_sold,
        sum(s.revenue)                            AS revenue
    FROM fact_sessions s
    GROUP BY s.date_key
)
SELECT
    d.*,
    dd.day_name,
    dd.is_weekend,
    d.date_key IN (SELECT date_key FROM dq_tracking_gap_days) AS tracking_gap,
    purchasing_sessions / sessions                AS session_conversion,
    revenue / nullif(units_sold, 0)               AS avg_unit_price,
    avg(revenue) OVER (ORDER BY d.date_key ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS revenue_7d_avg
FROM daily d JOIN dim_date dd USING (date_key)
ORDER BY d.date_key;

-- Q2. Where in the funnel does each category lose shoppers?
-- Unit = (session, main category): did the session view / cart / buy something in that category?
CREATE OR REPLACE TABLE mart_category_funnel AS
WITH session_category AS (
    SELECT
        f.session_id,
        p.main_category,
        bool_or(f.event_type = 'view')     AS viewed,
        bool_or(f.event_type = 'cart')     AS carted,
        bool_or(f.event_type = 'purchase') AS purchased,
        coalesce(sum(f.price) FILTER (WHERE f.event_type = 'purchase' AND NOT f.is_bad_price), 0) AS revenue
    FROM fact_events f JOIN dim_product p USING (product_id)
    WHERE f.session_id IS NOT NULL
    GROUP BY f.session_id, p.main_category
)
SELECT
    main_category,
    count(*) FILTER (WHERE viewed)                    AS sessions_viewed,
    count(*) FILTER (WHERE carted)                    AS sessions_carted,
    count(*) FILTER (WHERE purchased)                 AS sessions_purchased,
    count(*) FILTER (WHERE carted AND NOT purchased)  AS sessions_cart_abandoned,
    count(*) FILTER (WHERE carted) / nullif(count(*) FILTER (WHERE viewed), 0)    AS view_to_cart,
    count(*) FILTER (WHERE purchased) / nullif(count(*) FILTER (WHERE viewed), 0) AS view_to_purchase,
    count(*) FILTER (WHERE carted AND NOT purchased) / nullif(count(*) FILTER (WHERE carted), 0) AS cart_abandon_rate,
    sum(revenue)                                      AS revenue,
    sum(revenue) / sum(sum(revenue)) OVER ()          AS revenue_share,
    rank() OVER (ORDER BY sum(revenue) DESC)          AS revenue_rank
FROM session_category
GROUP BY main_category
ORDER BY revenue DESC;

-- Q3. Do first-time buyers come back? Weekly cohorts by week of first purchase.
-- The data starts on 1 Oct 2019, so "first purchase" means first purchase seen in this window.
CREATE OR REPLACE TABLE mart_cohort_retention AS
WITH buyer_weeks AS (
    SELECT DISTINCT user_id, date_trunc('week', event_time)::DATE AS purchase_week
    FROM fact_events
    WHERE event_type = 'purchase'
), cohorts AS (
    SELECT user_id, purchase_week,
           min(purchase_week) OVER (PARTITION BY user_id) AS cohort_week
    FROM buyer_weeks
), counts AS (
    SELECT cohort_week,
           date_diff('week', cohort_week, purchase_week) AS weeks_since_first,
           count(*) AS buyers
    FROM cohorts
    GROUP BY ALL
)
SELECT
    cohort_week,
    weeks_since_first,
    buyers,
    first_value(buyers) OVER (PARTITION BY cohort_week ORDER BY weeks_since_first) AS cohort_size,
    buyers / first_value(buyers) OVER (PARTITION BY cohort_week ORDER BY weeks_since_first) AS retention
FROM counts
ORDER BY cohort_week, weeks_since_first;

-- Q4. How much revenue comes from repeat buyers?
CREATE OR REPLACE TABLE mart_repeat_buyers AS
SELECT
    CASE WHEN purchases = 1 THEN '1 purchase'
         WHEN purchases <= 3 THEN '2-3 purchases'
         WHEN purchases <= 10 THEN '4-10 purchases'
         ELSE '11+ purchases' END              AS buyer_segment,
    min(purchases)                             AS sort_key,
    count(*)                                   AS buyers,
    sum(revenue)                               AS revenue,
    sum(revenue) / sum(sum(revenue)) OVER ()   AS revenue_share,
    count(*) / sum(count(*)) OVER ()           AS buyer_share
FROM dim_user
WHERE purchases > 0
GROUP BY buyer_segment
ORDER BY sort_key;

-- Q5. Which brands carry the revenue? Pareto with cumulative share.
CREATE OR REPLACE TABLE mart_brand_pareto AS
WITH brand_rev AS (
    SELECT p.brand,
           count(*) AS units_sold,
           sum(f.price) AS revenue
    FROM fact_events f JOIN dim_product p USING (product_id)
    WHERE f.event_type = 'purchase' AND NOT f.is_bad_price
    GROUP BY p.brand
)
SELECT
    brand,
    units_sold,
    revenue,
    revenue / sum(revenue) OVER ()                                         AS revenue_share,
    sum(revenue) OVER (ORDER BY revenue DESC ROWS UNBOUNDED PRECEDING)
        / sum(revenue) OVER ()                                             AS cumulative_share,
    row_number() OVER (ORDER BY revenue DESC)                              AS brand_rank
FROM brand_rev
ORDER BY revenue DESC;

-- Q6. When do sessions convert? Day-of-week x hour (UTC, as in the source). Gap days excluded.
CREATE OR REPLACE TABLE mart_hour_dow AS
SELECT
    isodow(session_start)                       AS iso_dow,
    dayname(session_start)                      AS day_name,
    hour(session_start)                         AS hour_utc,
    count(*)                                    AS sessions,
    count(*) FILTER (WHERE has_purchase) / count(*) AS session_conversion,
    sum(revenue)                                AS revenue
FROM fact_sessions
WHERE date_key NOT IN (SELECT date_key FROM dq_tracking_gap_days)
GROUP BY ALL
ORDER BY iso_dow, hour_utc;

-- Q7. How quickly do repeat buyers return? Gap between consecutive purchase days.
CREATE OR REPLACE TABLE mart_repurchase_gap AS
WITH purchase_days AS (
    SELECT DISTINCT user_id, event_time::DATE AS purchase_date
    FROM fact_events WHERE event_type = 'purchase'
), gaps AS (
    SELECT date_diff('day', lag(purchase_date) OVER (PARTITION BY user_id ORDER BY purchase_date),
                     purchase_date) AS days_since_previous
    FROM purchase_days
)
SELECT days_since_previous, count(*) AS repeat_purchase_days
FROM gaps
WHERE days_since_previous IS NOT NULL
GROUP BY days_since_previous
ORDER BY days_since_previous;

-- Q8. Does conversion depend on price level? Price bands of viewed products.
CREATE OR REPLACE TABLE mart_price_band AS
WITH banded AS (
    SELECT
        CASE WHEN price < 25 THEN '1: <25'
             WHEN price < 50 THEN '2: 25-50'
             WHEN price < 100 THEN '3: 50-100'
             WHEN price < 250 THEN '4: 100-250'
             WHEN price < 500 THEN '5: 250-500'
             ELSE '6: 500+' END AS price_band,
        event_type
    FROM fact_events
    WHERE NOT is_bad_price
)
SELECT
    price_band,
    count(*) FILTER (WHERE event_type = 'view')     AS views,
    count(*) FILTER (WHERE event_type = 'cart')     AS carts,
    count(*) FILTER (WHERE event_type = 'purchase') AS purchases,
    count(*) FILTER (WHERE event_type = 'purchase')
        / nullif(count(*) FILTER (WHERE event_type = 'view'), 0) AS purchases_per_view
FROM banded
GROUP BY price_band
ORDER BY price_band;
