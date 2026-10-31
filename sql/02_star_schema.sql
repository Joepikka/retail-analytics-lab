-- Step 2b: star schema. Grain of fact_events = one cleaned event.

-- A product's category/brand can differ between events; keep the most recent values.
CREATE OR REPLACE TABLE dim_product AS
SELECT
    product_id,
    arg_max(category_id, event_time)   AS category_id,
    arg_max(category_code, event_time) AS category_code,
    split_part(arg_max(category_code, event_time), '.', 1) AS main_category,
    arg_max(brand, event_time)         AS brand,
    count(DISTINCT category_code)      AS category_code_versions
FROM events_clean
GROUP BY product_id;

CREATE OR REPLACE TABLE dim_date AS
SELECT
    d::DATE                         AS date_key,
    dayname(d)                      AS day_name,
    isodow(d)                       AS iso_dow,
    isodow(d) IN (6, 7)             AS is_weekend,
    date_trunc('week', d)::DATE     AS week_start,
    strftime(d, '%Y-%m')            AS year_month
FROM range(
    (SELECT min(event_time)::DATE FROM events_clean),
    (SELECT max(event_time)::DATE FROM events_clean) + 1,
    INTERVAL 1 DAY
) t(d);

CREATE OR REPLACE TABLE fact_events AS
SELECT
    event_time,
    event_time::DATE         AS date_key,
    hour(event_time)         AS event_hour,
    event_type,
    product_id,
    price,
    is_bad_price,
    user_id,
    user_session             AS session_id
FROM events_clean;

-- One row per session: what the shopper did in that visit.
CREATE OR REPLACE TABLE fact_sessions AS
SELECT
    session_id,
    any_value(user_id)                                    AS user_id,
    min(event_time)                                       AS session_start,
    min(event_time)::DATE                                 AS date_key,
    count(*)                                              AS events,
    bool_or(event_type = 'view')                          AS has_view,
    bool_or(event_type = 'cart')                          AS has_cart,
    bool_or(event_type = 'purchase')                      AS has_purchase,
    count(*) FILTER (WHERE event_type = 'purchase')       AS purchases,
    coalesce(sum(price) FILTER (WHERE event_type = 'purchase' AND NOT is_bad_price), 0) AS revenue
FROM fact_events
WHERE session_id IS NOT NULL
GROUP BY session_id;

CREATE OR REPLACE TABLE dim_user AS
SELECT
    user_id,
    min(event_time)                                            AS first_seen,
    min(event_time) FILTER (WHERE event_type = 'purchase')     AS first_purchase,
    count(*) FILTER (WHERE event_type = 'purchase')            AS purchases,
    coalesce(sum(price) FILTER (WHERE event_type = 'purchase' AND NOT is_bad_price), 0) AS revenue
FROM fact_events
GROUP BY user_id;
