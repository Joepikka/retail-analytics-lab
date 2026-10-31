# Power BI guide: rebuild the dashboard

This guide rebuilds the project dashboard in Power BI Desktop from the CSV marts in `reports/csv/`. Plan on about 60–90 minutes for the first build. Build it yourself, because interviewers ask how a Power BI model is set up and why.

**You need:** Windows, plus [Power BI Desktop](https://www.microsoft.com/power-bi/desktop), which is free from the Microsoft Store. You also need `reports/csv/`, which you already have after `python run_all.py`.

**Save as:** `powerbi/retail_analytics.pbix`. To keep the report readable in git, also use *File → Save as → Power BI project (.pbip)*.

---

## 1. Load the data (10 min)

1. Open Power BI Desktop and go to *Home → Get data → Text/CSV*.
2. Load these files, one at a time, from `reports/csv/`:
   - `mart_daily_kpis.csv`
   - `mart_category_funnel.csv`
   - `mart_category_month.csv`
   - `mart_brand_pareto.csv`
   - `mart_cohort_retention.csv`
   - `mart_hour_dow.csv`
   - `mart_repeat_buyers.csv`
   - `forecast_daily.csv`
3. For each file, click **Transform Data** (not Load). In Power Query, check the column types:
   - `date_key`, `cohort_week` and `date` → **Date**
   - `revenue`, the `*_share` columns, the rates and the forecast columns → **Decimal number**
   - `sessions`, `units_sold`, `buyers` and `views` → **Whole number**
   - `is_weekend` and `tracking_gap` → **True/False**
4. Rename the queries without the `mart_` prefix: `daily_kpis`, `category_funnel`, and so on.
5. Click *Close & Apply*.

> Interview point: you type the columns in Power Query, so the model never guesses. A date loaded as text breaks every time-intelligence measure.

## 2. Build a date table (5 min)

*Modeling → New table*:

```DAX
Date =
ADDCOLUMNS (
    CALENDAR ( DATE ( 2019, 10, 1 ), DATE ( 2019, 11, 30 ) ),
    "Month", FORMAT ( [Date], "yyyy-mm" ),
    "Weekday", FORMAT ( [Date], "ddd" ),
    "Weekday No", WEEKDAY ( [Date], 2 ),
    "Is Weekend", WEEKDAY ( [Date], 2 ) >= 6
)
```

Then:
- Select the table and choose *Mark as date table*, using the `Date` column.
- Sort `Weekday` by `Weekday No` (*Column tools → Sort by column*).

## 3. Relationships (5 min)

In *Model view*, drag to create:

| From (many) | To (one) | Cardinality | Filter direction |
|---|---|---|---|
| `daily_kpis[date_key]` | `Date[Date]` | Many-to-one | Single |
| `forecast_daily[date]` | `Date[Date]` | Many-to-one | Single |

The other tables are already aggregated summaries. Leave them unrelated and use them as standalone visuals.

> Interview point: this is a star schema. `Date` is a dimension and `daily_kpis` is a fact at one-row-per-day grain. A single filter direction avoids ambiguous filter paths.

## 4. Measures (15 min)

Create a table to hold the measures: *Home → Enter data*, name it `_Measures`, then delete its column. Add each measure with *New measure*.

```DAX
Revenue = SUM ( daily_kpis[revenue] )

Units Sold = SUM ( daily_kpis[units_sold] )

Sessions = SUM ( daily_kpis[sessions] )

-- Conversion excludes 14-17 Nov, when purchase logging failed
Session Conversion =
DIVIDE (
    CALCULATE ( SUM ( daily_kpis[purchasing_sessions] ), daily_kpis[tracking_gap] = FALSE () ),
    CALCULATE ( SUM ( daily_kpis[sessions] ), daily_kpis[tracking_gap] = FALSE () )
)

Avg Daily Revenue (clean days) =
AVERAGEX (
    FILTER ( daily_kpis, daily_kpis[tracking_gap] = FALSE () ),
    daily_kpis[revenue]
)

Revenue 7d Avg =
AVERAGEX (
    DATESINPERIOD ( 'Date'[Date], MAX ( 'Date'[Date] ), -7, DAY ),
    CALCULATE ( SUM ( daily_kpis[revenue] ) )
)

Revenue MoM % =
VAR CurrentMonth = [Revenue]
VAR PriorMonth = CALCULATE ( [Revenue], DATEADD ( 'Date'[Date], -1, MONTH ) )
RETURN DIVIDE ( CurrentMonth - PriorMonth, PriorMonth )

Repeat Buyer Revenue Share =
CALCULATE (
    SUM ( repeat_buyers[revenue_share] ),
    repeat_buyers[buyer_segment] <> "1 purchase"
)

Forecast Abs Error % =
AVERAGEX (
    forecast_daily,
    DIVIDE ( ABS ( forecast_daily[trend_weekday_regression] - forecast_daily[actual] ), forecast_daily[actual] )
)
```

Format `Revenue` and `Avg Daily Revenue` as currency with 0 decimals. Format the rates and shares as percentages.

**Check your numbers against the Excel Summary sheet:**
- `Revenue` = **$505.1M**
- `Session Conversion` = **5.96%**
- `Repeat Buyer Revenue Share` = **78.7%**
- `Forecast Abs Error %` = **7.0%**

If any of these differ, a column type or filter is wrong.

> Interview point: `Session Conversion` divides the sums, not the average of the daily rates. Averaging the daily ratios would give a quiet day the same weight as a busy day.

## 5. Report pages (30–45 min)

**Page 1: Overview**
- **Cards:** Revenue, Units Sold, Sessions, Session Conversion, Repeat Buyer Revenue Share.
- **Line chart:** X = `Date[Date]`, Y = `Revenue` and `Revenue 7d Avg`. Add the text box: *"14–17 Nov: purchase logging failed; 17 Nov spike is a catch-up."*
- **Slicer:** `Date[Month]`.

**Page 2: Categories**
- **Clustered bar chart:** `category_funnel[main_category]` by `revenue`, sorted descending, with the `unknown` category filtered out (filter pane).
- **Table:** category, `sessions_viewed`, `sessions_purchased`, `view_to_purchase`. Conditional formatting: *Background color → Gradient* on `view_to_purchase`.
- **Matrix:** rows = `category_month[main_category]`, columns = `year_month`, values = `revenue`. This is the Power BI version of the Excel crosstab.

**Page 3: Customers**
- **Clustered column chart:** `repeat_buyers[buyer_segment]` with `buyer_share` and `revenue_share`. Sort the axis by `sort_key`.
- **Matrix heatmap:** rows = `cohort_retention[cohort_week]`, columns = `weeks_since_first`, values = `retention`. Use *Background color* gradient conditional formatting, and filter `weeks_since_first > 0`.

**Page 4: Timing & brands**
- **Matrix heatmap:** rows = `hour_dow[day_name]` (sorted by `iso_dow`), columns = `hour_utc`, values = `session_conversion`.
- **Bar chart:** `brand_pareto[brand]` by `revenue_share`, filtered to `brand_rank <= 15`.

**Page 5: Forecast**
- **Line chart:** X = `forecast_daily[date]`, Y = `actual`, `trend_weekday_regression`, `seasonal_naive`.
- **Card:** `Forecast Abs Error %`.

**Design rules:**
- One accent color for single-series charts.
- No 3D or pie charts.
- Every page gets a title that states the takeaway, for example *"Electronics is 76% of revenue"*, not just *"Categories"*.

## 6. Publish (optional, 5 min)

*Home → Publish* needs a work or school Power BI account. If you only have a personal account, you can't publish, so do this instead:
- Screenshot each page into `powerbi/screenshots/`.
- Add those images to the README.
- Commit the `.pbip` folder so reviewers can open the model.

## What to say in an interview

"I loaded the SQL marts into Power BI and added a marked date table, so time-intelligence measures like the 7-day average and month-over-month change work. Conversion is a measure that divides sums and excludes the four days when purchase tracking failed. I checked every total against the SQL output before building any visuals."
