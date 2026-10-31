"""Step 3: data tests. Fails loudly (non-zero exit) if the warehouse is inconsistent."""
import json
import sys

from common import MANIFEST, connect

TOLERANCE = 0.01  # currency units; floating-point sums over ~100M rows


def check(con, name, sql, expect_true=True):
    value = con.execute(sql).fetchone()[0]
    ok = bool(value) == expect_true
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    return ok


def main():
    con = connect()
    manifest = json.loads(MANIFEST.read_text())
    raw_rows = sum(m["raw_rows"] for m in manifest.values())

    results = [
        check(con, "staged rows == raw rows in manifest",
              f"SELECT staged_rows = {raw_rows} FROM dq_summary"),
        check(con, "clean rows == staged rows - duplicates removed",
              """SELECT (SELECT count(*) FROM events_clean)
                        = (SELECT staged_rows FROM dq_summary)
                          - (SELECT sum(duplicate_rows_removed) FROM dq_duplicates)"""),
        check(con, "only view/cart/purchase event types",
              "SELECT other_event_rows = 0 FROM dq_summary"),
        check(con, "fact_events has no null user_id or event_time",
              "SELECT count(*) = 0 FROM fact_events WHERE user_id IS NULL OR event_time IS NULL"),
        check(con, "dim_product is unique on product_id",
              "SELECT count(*) = count(DISTINCT product_id) FROM dim_product"),
        check(con, "every fact product exists in dim_product",
              "SELECT count(*) = 0 FROM fact_events f ANTI JOIN dim_product p USING (product_id)"),
        check(con, "fact dates covered by dim_date",
              "SELECT count(*) = 0 FROM (SELECT DISTINCT date_key FROM fact_events) f ANTI JOIN dim_date USING (date_key)"),
        check(con, "revenue reconciles: staged - duplicates == fact",
              f"""SELECT abs((SELECT staged_purchase_revenue FROM dq_summary)
                       - (SELECT duplicate_value_removed FROM dq_duplicates WHERE event_type = 'purchase')
                       - (SELECT sum(price) FROM fact_events WHERE event_type = 'purchase' AND NOT is_bad_price))
                     < {TOLERANCE}"""),
        check(con, "daily mart revenue == session fact revenue",
              f"SELECT abs((SELECT sum(revenue) FROM mart_daily_kpis) - (SELECT sum(revenue) FROM fact_sessions)) < {TOLERANCE}"),
        check(con, "category funnel revenue == session-linked purchase revenue",
              f"""SELECT abs((SELECT sum(revenue) FROM mart_category_funnel)
                       - (SELECT sum(price) FROM fact_events
                          WHERE event_type = 'purchase' AND NOT is_bad_price AND session_id IS NOT NULL))
                     < {TOLERANCE}"""),
        check(con, "repeat-buyer mart covers all buyer revenue",
              f"SELECT abs((SELECT sum(revenue) FROM mart_repeat_buyers) - (SELECT sum(revenue) FROM dim_user)) < {TOLERANCE}"),
        check(con, "cohort week-0 retention is 100%",
              "SELECT bool_and(retention = 1) FROM mart_cohort_retention WHERE weeks_since_first = 0"),
        check(con, "funnel rates are between 0 and 1",
              "SELECT bool_and(view_to_purchase BETWEEN 0 AND 1 AND cart_abandon_rate BETWEEN 0 AND 1) FROM mart_category_funnel WHERE sessions_viewed > 0"),
    ]
    con.close()
    passed = sum(results)
    print(f"  {passed}/{len(results)} tests passed")
    if passed != len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
