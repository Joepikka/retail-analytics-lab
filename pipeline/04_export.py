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
    "dq_duplicates", "dq_tracking_gap_hours", "mart_category_month",
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
    cols, rows = rows_of(con, "SELECT year_month, main_category, units_sold, revenue FROM mart_category_month")
    add_table_sheet(wb, "CategoryMonth", cols, rows, {"revenue": money})

    # Category x month crosstab built with SUMIFS (same result a PivotTable on CategoryMonth gives).
    cats = [r[0] for r in con.execute("SELECT main_category FROM mart_category_funnel ORDER BY revenue DESC").fetchall()]
    months = [r[0] for r in con.execute("SELECT DISTINCT year_month FROM mart_category_month ORDER BY 1").fetchall()]
    xt = wb.create_sheet("CategoryByMonth")
    xt.append(["main_category"] + months + ["Total"])
    for r, cat in enumerate(cats, start=2):
        xt.cell(row=r, column=1, value=cat)
        for c, month in enumerate(months, start=2):
            xt.cell(row=r, column=c, value=f'=SUMIFS(CategoryMonth[revenue],CategoryMonth[main_category],$A{r},CategoryMonth[year_month],{get_column_letter(c)}$1)').number_format = money
        last = get_column_letter(len(months) + 1)
        xt.cell(row=r, column=len(months) + 2, value=f"=SUM(B{r}:{last}{r})").number_format = money
    total_row = len(cats) + 2
    xt.cell(row=total_row, column=1, value="Total").font = Font(bold=True)
    for c in range(2, len(months) + 3):
        col = get_column_letter(c)
        xt.cell(row=total_row, column=c, value=f"=SUM({col}2:{col}{total_row - 1})").number_format = money
    xt.column_dimensions["A"].width = 18
    for c in range(2, len(months) + 3):
        xt.column_dimensions[get_column_letter(c)].width = 18

    # Expected values computed in DuckDB, so Excel's formula results can be checked against SQL.
    expected = con.execute("""
        SELECT
            (SELECT sum(revenue) FROM mart_daily_kpis),
            (SELECT sum(units_sold) FROM mart_daily_kpis),
            (SELECT avg(revenue) FROM mart_daily_kpis WHERE NOT is_weekend AND NOT tracking_gap),
            (SELECT avg(revenue) FROM mart_daily_kpis WHERE is_weekend AND NOT tracking_gap),
            (SELECT sum(revenue) FROM mart_daily_kpis WHERE date_key < DATE '2019-11-01'),
            (SELECT sum(revenue) FROM mart_daily_kpis WHERE date_key >= DATE '2019-11-01'),
            (SELECT revenue_share FROM mart_category_funnel WHERE main_category = 'electronics'),
            (SELECT cart_abandon_rate FROM mart_category_funnel WHERE main_category = 'electronics'),
            (SELECT count(*) + 1 FROM mart_brand_pareto WHERE cumulative_share < 0.8 AND brand_rank <= 50),
            (SELECT sum(revenue) FROM mart_category_month)
    """).fetchone()

    # Summary sheet: live formulas over the tables, each next to the value SQL produced.
    ws = wb.create_sheet("Summary", 1)
    ws["A1"] = "KPI summary (formulas)"
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([])
    ws.append(["Metric", "Excel formula", "Expected (SQL)", "Match?"])
    for cell in ws[3]:
        cell.font = Font(bold=True)
    summary = [
        ("Total revenue", "=SUM(Daily[revenue])", money),
        ("Total units sold", "=SUM(Daily[units_sold])", "#,##0"),
        ("Weekday avg daily revenue (excl. gap days)", '=AVERAGEIFS(Daily[revenue],Daily[is_weekend],FALSE,Daily[tracking_gap],FALSE)', money),
        ("Weekend avg daily revenue (excl. gap days)", '=AVERAGEIFS(Daily[revenue],Daily[is_weekend],TRUE,Daily[tracking_gap],FALSE)', money),
        ("Revenue Oct 2019", '=SUMIFS(Daily[revenue],Daily[date_key],">="&DATE(2019,10,1),Daily[date_key],"<"&DATE(2019,11,1))', money),
        ("Revenue Nov 2019", '=SUMIFS(Daily[revenue],Daily[date_key],">="&DATE(2019,11,1),Daily[date_key],"<"&DATE(2019,12,1))', money),
        ("electronics revenue share (XLOOKUP)", '=_xlfn.XLOOKUP("electronics",Categories[main_category],Categories[revenue_share],"not found")', pct),
        ("electronics cart abandon rate (XLOOKUP)", '=_xlfn.XLOOKUP("electronics",Categories[main_category],Categories[cart_abandon_rate],"not found")', pct),
        ("Brands needed for 80% of revenue", '=COUNTIFS(Brands[cumulative_share],"<"&0.8)+1', "0"),
        ("Crosstab grand total", f"=CategoryByMonth!{get_column_letter(len(months) + 2)}{total_row}", money),
    ]
    for i, ((label, formula, fmt), exp) in enumerate(zip(summary, expected), start=4):
        ws.cell(row=i, column=1, value=label)
        ws.cell(row=i, column=2, value=formula).number_format = fmt
        ws.cell(row=i, column=3, value=float(exp)).number_format = fmt
        ws.cell(row=i, column=4, value=f"=ABS(B{i}-C{i})<=MAX(0.01,ABS(C{i})*1E-9)")
    ws.column_dimensions["A"].width = 44
    for col in "BC":
        ws.column_dimensions[col].width = 20
    ws.column_dimensions["D"].width = 10

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
    for key, filename in [("ab_test", "ab_test_results.json"), ("forecast", "forecast_results.json")]:
        path = REPORTS / filename
        if path.exists():
            data[key] = json.loads(path.read_text())
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
