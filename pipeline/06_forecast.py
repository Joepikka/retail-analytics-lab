"""Step 6: daily revenue forecast, compared honestly against simple baselines.

Forecast origin: end of 13 Nov 2019 (last clean day before the tracking gap).
Train: 1 Oct - 13 Nov (44 days). Test: 18 - 30 Nov (13 days), forecast all at once.
Gap days (14-17 Nov, purchase logging failed) are in neither set.
Black Friday (29 Nov) is inside the test window; metrics are reported with and without it.
"""
import csv
import json
from datetime import date, timedelta

import numpy as np

from common import REPORTS, connect

TRAIN_END = date(2019, 11, 13)
TEST_START = date(2019, 11, 18)
BLACK_FRIDAY = date(2019, 11, 29)
Z80 = 1.2816  # two-sided 80% prediction interval


def metrics(actual, pred):
    actual, pred = np.asarray(actual, float), np.asarray(pred, float)
    err = pred - actual
    return {"mae": float(np.mean(np.abs(err))),
            "rmse": float(np.sqrt(np.mean(err ** 2))),
            "mape": float(np.mean(np.abs(err) / actual))}


def design_matrix(days, origin):
    """Intercept, linear trend in days, and Monday-based weekday dummies (Sunday = baseline)."""
    rows = []
    for d in days:
        dummies = [1.0 if d.isoweekday() == k else 0.0 for k in range(1, 7)]
        rows.append([1.0, (d - origin).days] + dummies)
    return np.array(rows)


def self_check():
    m = metrics([100, 200], [110, 180])
    assert m["mae"] == 15 and abs(m["mape"] - 0.1) < 1e-12
    # OLS recovers a known trend + weekday effect from noiseless synthetic data.
    origin = date(2019, 10, 1)
    days = [origin + timedelta(i) for i in range(42)]
    y = np.array([1000 + 5 * i + (300 if d.isoweekday() == 6 else 0) for i, d in enumerate(days)])
    beta, *_ = np.linalg.lstsq(design_matrix(days, origin), y, rcond=None)
    assert abs(beta[1] - 5) < 1e-6 and abs(beta[2 + 5] - 300) < 1e-6


def main():
    self_check()
    con = connect()
    rows = con.execute(
        "SELECT date_key, revenue FROM mart_daily_kpis WHERE NOT tracking_gap ORDER BY date_key"
    ).fetchall()
    con.close()
    series = {d: float(r) for d, r in rows}
    train = {d: r for d, r in series.items() if d <= TRAIN_END}
    test = {d: r for d, r in series.items() if d >= TEST_START}
    train_days, test_days = sorted(train), sorted(test)
    y_train = np.array([train[d] for d in train_days])
    origin = train_days[0]

    forecasts = {}
    # 1. Naive: every future day equals the last training day.
    forecasts["naive_last_day"] = [train[train_days[-1]]] * len(test_days)
    # 2. Seasonal naive: same weekday in the last training week.
    last_week = {d.isoweekday(): train[d] for d in train_days[-7:]}
    forecasts["seasonal_naive"] = [last_week[d.isoweekday()] for d in test_days]
    # 3. Mean of the last 28 days for each weekday.
    recent = train_days[-28:]
    weekday_mean = {k: np.mean([train[d] for d in recent if d.isoweekday() == k]) for k in range(1, 8)}
    forecasts["weekday_mean_28d"] = [float(weekday_mean[d.isoweekday()]) for d in test_days]
    # 4. Linear regression: trend + weekday effects, with an 80% prediction interval.
    X_train = design_matrix(train_days, origin)
    beta, *_ = np.linalg.lstsq(X_train, y_train, rcond=None)
    resid_sd = float(np.std(y_train - X_train @ beta, ddof=X_train.shape[1]))
    reg = design_matrix(test_days, origin) @ beta
    forecasts["trend_weekday_regression"] = [float(v) for v in reg]
    lower, upper = reg - Z80 * resid_sd, reg + Z80 * resid_sd

    actual = [test[d] for d in test_days]
    keep = [i for i, d in enumerate(test_days) if d != BLACK_FRIDAY]
    results = {}
    for name, pred in forecasts.items():
        results[name] = {
            "all_test_days": metrics(actual, pred),
            "excluding_black_friday": metrics([actual[i] for i in keep], [pred[i] for i in keep]),
        }
    best = min(results, key=lambda k: results[k]["excluding_black_friday"]["mae"])
    coverage = float(np.mean([lo <= a <= hi for a, lo, hi in zip(actual, lower, upper)]))

    out = {
        "train": [str(train_days[0]), str(train_days[-1]), len(train_days)],
        "test": [str(test_days[0]), str(test_days[-1]), len(test_days)],
        "excluded_gap_days": "14-17 Nov 2019",
        "results": results,
        "best_model_excluding_black_friday": best,
        "regression_80pct_interval_coverage": coverage,
        "black_friday": {"actual": test[BLACK_FRIDAY],
                         "regression_forecast": forecasts["trend_weekday_regression"][test_days.index(BLACK_FRIDAY)]},
        "daily": [{"date": str(d), "actual": actual[i],
                   **{k: v[i] for k, v in forecasts.items()},
                   "regression_lower80": float(lower[i]), "regression_upper80": float(upper[i])}
                  for i, d in enumerate(test_days)],
    }
    (REPORTS / "forecast_results.json").write_text(json.dumps(out, indent=2))
    (REPORTS / "csv").mkdir(parents=True, exist_ok=True)
    with open(REPORTS / "csv" / "forecast_daily.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out["daily"][0]))
        w.writeheader()
        w.writerows(out["daily"])

    print(f"  train {len(train_days)} days, test {len(test_days)} days")
    for name, r in results.items():
        a, b = r["all_test_days"], r["excluding_black_friday"]
        print(f"  {name:26s} MAPE {a['mape']:6.1%} (excl. BF {b['mape']:6.1%})  MAE ${b['mae'] / 1e6:5.2f}M excl. BF")
    print(f"  best (excl. Black Friday): {best}; regression 80% interval coverage {coverage:.0%}")


if __name__ == "__main__":
    main()
