# Decision memo: multi-category online store, Oct–Nov 2019

**Data:** 109,950,743 events (104.3M views, 3.96M carts, 1.66M purchases) from 5.3M users across 23.0M sessions, 1 Oct – 30 Nov 2019.
**Revenue definition:** sum of purchase-event prices with price > 0, counting one unit per event. Total: **$505.1M** from 1.66M units.
All figures come from the marts in `reports/csv/`. Each one can be traced to a SQL query in `sql/03_marts.sql`.

## Headline

Revenue depends heavily on **one category** (electronics, 76%), on **two brands** (Apple and Samsung, 67%), and on **repeat buyers** (42% of buyers produce 79% of revenue). Before any growth work, the store has a **measurement problem**. Purchase tracking failed for most of 14–17 Nov, so four days of revenue reporting are unreliable.

## Findings

**1. Purchase tracking failed in mid-November.**
- For 48 hours with real traffic (over 10k events each), zero purchases were logged. The gaps ran from 14 Nov 19:00 to 16 Nov 08:00 UTC, and again from 16 Nov 16:00 to 17 Nov 03:00 UTC. Views kept arriving normally.
- 17 Nov then shows $57.8M of revenue and 15.5% session conversion, against about $7.3M and 6% on a normal day. That looks like delayed purchases being written in a batch, not a real sales peak.
- Effect on the analysis: with those days included, weekends appear to earn 53% more per day than weekdays. With them excluded, weekend and weekday revenue are about the same ($7.08M vs $7.40M per day), and conversion is too (6.08% vs 5.92%).

**2. Cart events are not reliable before mid-October.**
- In October, 54% of sessions that bought something had no cart event. In November it was 16%.
- Carts per purchase jump from about 0.83 to above 1.5 around 14 Oct, which points to a tracking change rather than a change in behaviour.
- So this memo uses **view → purchase** as the main funnel metric. Cart-abandonment rates (55–74% by category) are indicative only.

**3. Electronics is the business.**

| Category | Share of revenue | View → purchase (sessions) |
|---|---|---|
| electronics | 75.6% | 7.6% |
| *no category code* | 10.5% | 4.3% |
| appliances | 6.4% | 5.8% |
| computers | 5.0% | 3.8% |
| apparel | 0.4% | 1.9% |
| furniture | 0.8% | 2.1% |

- 32% of events (35.4M) have no category code, so one-tenth of revenue cannot be attributed to any category.
- Apparel and furniture get plenty of attention but convert at a quarter of the electronics rate. Apparel has 1.08M viewing sessions and furniture 0.86M.

**4. Two brands carry two-thirds of revenue.**
- Apple has 47.3% of revenue and Samsung 20.1%.
- Just 7 of 2,738 brands make up 80% of revenue.
- Any supply or pricing change at Apple or Samsung directly hits half the store.

**5. Repeat buyers are where the money is.**

| Purchases per buyer | Share of buyers | Share of revenue |
|---|---|---|
| 1 | 57.7% | 21.3% |
| 2–3 | 28.4% | 25.0% |
| 4–10 | 11.5% | 28.0% |
| 11+ | 2.4% | 25.7% |

- 2.4% of buyers (16,773 people) produce a quarter of revenue in just two months. That pattern suggests resellers or business buyers. I cannot confirm it without account data.
- Among repeat purchases, 65.5% happen within 7 days of the buyer's previous purchase day.
- In the first full cohorts, 11–20% of new buyers buy again the following week.

**6. Conversion fell in November while traffic grew.**
- November had 49% more sessions than October (13.8M vs 9.2M).
- Session conversion fell from 6.81% to 5.21%, even with the gap days excluded.
- Revenue per normal day was almost flat: $7.42M in October vs $7.19M in November.
- So the extra November traffic brought few extra sales. The data has no traffic-source field, so I cannot tell which channel brought those low-intent visitors.

**7. Timing and price.**
- Conversion peaks from 07:00 to 09:00 UTC at about 7.3%, and is lowest from 17:00 to 20:00 UTC at 4–5%.
- By weekday, conversion only varies between 5.7% and 6.1%.
- Purchases per view are highest for products priced $100–250 (1.86%) and lowest under $25 (1.18%).

## Recommendations

1. **Monitor purchase tracking automatically. Do this first.** The pipeline's check for an hour with real traffic but no purchases (`dq_tracking_gap_hours`) can run as an hourly alert. Four days went unnoticed here, and every revenue and conversion number depends on this one event.
2. **Require a category code on every product in the product feed.** Doing so would let the 10.5% of revenue that cannot be attributed today be assigned to a category. It is a data fix with no customer-facing risk.
3. **Find out who the 11+ purchase buyers are.** If they are resellers, give them a B2B or wholesale path. If they are consumers, a loyalty offer aimed at the 2–3 purchase group could move more buyers into the high-value segments. Test either change with a controlled experiment rather than rolling it out store-wide.
4. **Before scaling acquisition, start recording traffic source.** November's extra 4.5M sessions added almost no revenue. Spend cannot be judged without knowing where visitors come from.
5. **Use a low-converting, high-traffic category as the first experiment target.** Apparel and furniture fit. A test sized like the one below could show whether a change to the product page or checkout closes part of the gap with electronics.

## Can daily revenue be forecast?

`pipeline/06_forecast.py` trains on 44 clean days (1 Oct – 13 Nov) and forecasts 13 days ahead (18–30 Nov) from a single origin. The tracking-gap days are excluded from both sets.

| Model | MAPE, all test days | MAPE, excl. Black Friday |
|---|---|---|
| Trend + weekday regression | 7.0% | **5.6%** |
| Seasonal naive (same weekday last week) | 7.0% | 5.9% |
| Weekday mean of the last 28 days | 7.3% | 6.1% |
| Naive (last day repeated) | 8.1% | 6.3% |

- The regression is the best model, but only just. A 0.3-point edge over the seasonal-naive baseline on 13 days is not strong evidence. Daily revenue is stable enough that a one-line baseline gets you most of the way.
- The 80% prediction interval covered 85% of test days, so its uncertainty estimate is about right.
- Black Friday (29 Nov) came in at $9.63M against a $7.36M forecast. The models have no feature for promotional events, so planning for known sale days has to come from a separate uplift estimate.

## How a test should be run (simulated design)

The historical data is not an experiment, so it cannot show what causes what. `pipeline/05_ab_test_simulation.py` uses the real baseline (5.96% session conversion, gap days excluded) to design a test of a cart-page change:
- Detecting a 5% relative lift with α = 0.05 and 80% power needs **101,365 sessions per arm**. Traffic alone would supply that in about a day, but the test should still run **at least 14 days**, so both weekly cycles are balanced.
- Checks run on every result: a sample-ratio-mismatch test (expecting a 50/50 split), a two-proportion z-test, a 95% confidence interval for the difference, and an A/A control.
- The simulation injected a known 4% lift and measured +5.3% (p = 0.003, CI covering the true effect). This is a **simulation that shows the method works**. It is not a result about this store.

## Limitations

- The data covers two months of one store in 2019. Black Friday week (29 Nov) is the only seasonal signal, and it falls right at the end of the data. The forecast test window is only 13 days, too short to rank models with confidence.
- There are no costs, margins, or returns, so these findings are about revenue, not profit.
- Each purchase event is counted as one unit. If an event can hold more than one unit, revenue is understated.
- "First purchase" means the first purchase seen since 1 Oct. Buyers from before October look like new buyers.
- Times are in UTC. The store's local time zone is not documented.
