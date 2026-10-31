"""Step 4: export marts as CSV (for Power BI/Tableau), an Excel workbook and dashboard data."""
import json
from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from common import REPORTS, ROOT, connect

MARTS = [
    "mart_daily_kpis", "mart_category_funnel", "mart_cohort_retention", "mart_repeat_buyers",
    "mart_brand_pareto", "mart_hour_dow", "mart_repurchase_gap", "mart_price_band", "dq_summary",
    "dq_duplicates", "dq_tracking_gap_hours",
]


def rows_of(con, sql):
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return cols, cur.fetchall()


def to_json_value(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def export_csv(con):
    out = REPORTS / "csv"
    out.mkdir(parents=True, exist_ok=True)
    for name in MARTS:
        con.execute(f"COPY {name} TO '{(out / f'{name}.csv').as_posix()}' (HEADER)")
    print(f"  {len(MARTS)} CSV files -> {out.relative_to(ROOT)}")


def add_table_sheet(wb, title, cols, rows, formats=None):
    ws = wb.create_sheet(title)
    ws.append(cols)
    for r in rows:
        ws.append(list(r))
    ref = f"A1:{get_column_letter(len(cols))}{len(rows) + 1}"
    table = Table(displayName=title.replace(" ", "_"), ref=ref)
    table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    ws.add_table(table)
    for i, col in enumerate(cols, start=1):
        ws.column_dimensions[get_column_letter(i)].width = max(12, len(col) + 2)
        fmt = (formats or {}).get(col)
        if fmt:
            for row in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                row[0].number_format = fmt
    return ws


def export_excel(con):
    wb = Workbook()
    readme = wb.active
    readme.title = "README"
    notes = [
        "Retail Analytics Lab - KPI workbook",
        "Source: REES46 multi-category store events, Oct-Nov 2019 (Open CDP project).",
        "Revenue = sum of purchase-event prices with price > 0; one unit per purchase event.",
        "Sheets are Excel Tables: Insert > PivotTable on any of them to slice further.",
        "Summary sheet uses SUMIFS / AVERAGEIFS / XLOOKUP formulas over the tables.",
        "tracking_gap = TRUE marks 14-17 Nov 2019, when purchase logging stopped; averages exclude them.",
    ]
    for line in notes:
        readme.append([line])
    readme["A1"].font = Font(bold=True, size=14)
    readme.column_dimensions["A"].width = 90

    pct, money = "0.00%", "#,##0.00"
    cols, rows = rows_of(con, "SELECT date_key, day_name, is_weekend, tracking_gap, sessions, active_users, purchasing_sessions, units_sold, revenue, session_conversion, revenue_7d_avg FROM mart_daily_kpis")
    add_table_sheet(wb, "Daily", cols, rows, {"revenue": money, "revenue_7d_avg": money, "session_conversion": pct, "date_key": "yyyy-mm-dd"})
    cols, rows = rows_of(con, "SELECT main_category, sessions_viewed, sessions_carted, sessions_purchased, view_to_cart, view_to_purchase, cart_abandon_rate, revenue, revenue_share FROM mart_category_funnel")
    add_table_sheet(wb, "Categories", cols, rows, {c: pct for c in ["view_to_cart", "view_to_purchase", "cart_abandon_rate", "revenue_share"]} | {"revenue": money})
    cols, rows = rows_of(con, "SELECT brand_rank, brand, units_sold, revenue, revenue_share, cumulative_share FROM mart_brand_pareto WHERE brand_rank <= 50")
    add_table_sheet(wb, "Brands", cols, rows, {"revenue": money, "revenue_share": pct, "cumulative_share": pct})

    # Summary sheet: live formulas over the tables, so the numbers can be checked in Excel.
    ws = wb.create_sheet("Summary", 1)
    ws["A1"] = "KPI summary (formulas)"
    ws["A1"].font = Font(bold=True, size=14)
    summary = [
        ("Total revenue", "=SUM(Daily[revenue])", money),
        ("Total units sold", "=SUM(Daily[units_sold])", "#,##0"),
        ("Weekday avg daily revenue (excl. gap days)", '=AVERAGEIFS(Daily[revenue],Daily[is_weekend],FALSE,Daily[tracking_gap],FALSE)', money),
        ("Weekend avg daily revenue (excl. gap days)", '=AVERAGEIFS(Daily[revenue],Daily[is_weekend],TRUE,Daily[tracking_gap],FALSE)', money),
        ("Revenue Oct 2019", '=SUMIFS(Daily[revenue],Daily[date_key],">="&DATE(2019,10,1),Daily[date_key],"<"&DATE(2019,11,1))', money),
        ("Revenue Nov 2019", '=SUMIFS(Daily[revenue],Daily[date_key],">="&DATE(2019,11,1),Daily[date_key],"<"&DATE(2019,12,1))', money),
        ("Category to look up", "electronics", None),
        ("  its revenue share", '=_xlfn.XLOOKUP(B9,Categories[main_category],Categories[revenue_share],"not found")', pct),
        ("  its cart abandon rate", '=_xlfn.XLOOKUP(B9,Categories[main_category],Categories[cart_abandon_rate],"not found")', pct),
        ("Brands needed for 80% of revenue", '=COUNTIFS(Brands[cumulative_share],"<0.8")+1', "0"),
    ]
    for i, (label, formula, fmt) in enumerate(summary, start=3):
        ws.cell(row=i, column=1, value=label)
        cell = ws.cell(row=i, column=2, value=formula)
        if fmt:
            cell.number_format = fmt
    ws.column_dimensions["A"].width = 36
    ws.column_dimensions["B"].width = 20

    path = REPORTS / "retail_kpis.xlsx"
    wb.save(path)
    print(f"  Excel workbook -> {path.relative_to(ROOT)}")


def export_dashboard_data(con):
    data = {}
    queries = {
        "daily": "SELECT * FROM mart_daily_kpis",
        "categories": "SELECT * FROM mart_category_funnel WHERE main_category <> 'unknown' ORDER BY revenue DESC",
        "unknown_category": "SELECT * FROM mart_category_funnel WHERE main_category = 'unknown'",
        "cohorts": "SELECT * FROM mart_cohort_retention",
        "repeat": "SELECT * FROM mart_repeat_buyers",
        "brands": "SELECT * FROM mart_brand_pareto WHERE brand_rank <= 15",
        "brands_for_80pct": "SELECT count(*) + 1 AS n FROM mart_brand_pareto WHERE cumulative_share < 0.8",
        "brand_count": "SELECT count(*) AS n FROM mart_brand_pareto",
        "hour_dow": "SELECT * FROM mart_hour_dow",
        "gaps": "SELECT * FROM mart_repurchase_gap WHERE days_since_previous <= 30",
        "price_bands": "SELECT * FROM mart_price_band",
        "quality": "SELECT * FROM dq_summary",
        "duplicates": "SELECT * FROM dq_duplicates",
        "gap_hours": "SELECT count(*) AS hours, min(gap_hour) AS first_hour, max(gap_hour) AS last_hour FROM dq_tracking_gap_hours",
    }
    for key, sql in queries.items():
        cols, rows = rows_of(con, sql)
        data[key] = [{c: to_json_value(v) for c, v in zip(cols, r)} for r in rows]
    ab_path = REPORTS / "ab_test_results.json"
    if ab_path.exists():
        data["ab_test"] = json.loads(ab_path.read_text())
    out = ROOT / "dashboard" / "data.js"
    out.write_text("window.DASHBOARD_DATA = " + json.dumps(data, default=str) + ";\n", encoding="utf-8")
    print(f"  dashboard data -> {out.relative_to(ROOT)}")


def main():
    con = connect()
    export_csv(con)
    export_excel(con)
    export_dashboard_data(con)
    con.close()


if __name__ == "__main__":
    main()
