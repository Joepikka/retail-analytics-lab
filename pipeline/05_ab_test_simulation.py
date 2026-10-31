"""Step 5: A/B test design and analysis on SIMULATED data.

The historical events are not an experiment, so no causal claim is made from them.
Instead the real baseline session conversion rate is used to (1) size a hypothetical
test, (2) simulate one with a known true effect, and (3) analyse it the way a real
test would be analysed: sample-ratio check, two-proportion z-test, confidence interval.

Hypothetical change: a "free delivery over threshold" banner on the cart page.
"""
import json
import math

import numpy as np
from scipy import stats

from common import REPORTS, connect

SEED = 20191001
ALPHA = 0.05
POWER = 0.80
MDE_RELATIVE = 0.05        # smallest relative lift worth detecting (5%)
TRUE_LIFT_RELATIVE = 0.04  # the effect the simulation actually injects (unknown in real life)
MIN_DAYS = 14              # minimum test length: two full weekly cycles


def sample_size_per_arm(p_base, mde_rel, alpha=ALPHA, power=POWER):
    """Sessions per arm for a two-sided two-proportion test."""
    p_new = p_base * (1 + mde_rel)
    z_a = stats.norm.ppf(1 - alpha / 2)
    z_b = stats.norm.ppf(power)
    p_bar = (p_base + p_new) / 2
    num = (z_a * math.sqrt(2 * p_bar * (1 - p_bar))
           + z_b * math.sqrt(p_base * (1 - p_base) + p_new * (1 - p_new))) ** 2
    return math.ceil(num / (p_new - p_base) ** 2)


def two_proportion_test(conv_a, n_a, conv_b, n_b, alpha=ALPHA):
    p_a, p_b = conv_a / n_a, conv_b / n_b
    pooled = (conv_a + conv_b) / (n_a + n_b)
    se_pooled = math.sqrt(pooled * (1 - pooled) * (1 / n_a + 1 / n_b))
    z = (p_b - p_a) / se_pooled
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))
    se_diff = math.sqrt(p_a * (1 - p_a) / n_a + p_b * (1 - p_b) / n_b)
    margin = stats.norm.ppf(1 - alpha / 2) * se_diff
    return {"p_control": p_a, "p_treatment": p_b, "abs_diff": p_b - p_a,
            "rel_lift": (p_b - p_a) / p_a, "z": z, "p_value": p_value,
            "ci_low": p_b - p_a - margin, "ci_high": p_b - p_a + margin}


def srm_p_value(n_a, n_b):
    """Chi-square sample-ratio-mismatch check against an intended 50/50 split."""
    return stats.chisquare([n_a, n_b]).pvalue


def self_check():
    # Textbook case: 200/2000 vs 260/2000 -> z ~ 2.97, significant.
    r = two_proportion_test(200, 2000, 260, 2000)
    assert abs(r["z"] - 2.97) < 0.02 and r["p_value"] < 0.01
    # A 52/48 split on 100k units is a clear SRM; 50/50 is not.
    assert srm_p_value(52_000, 48_000) < 1e-6 and srm_p_value(50_000, 50_000) == 1.0
    # Smaller MDE needs more sessions.
    assert sample_size_per_arm(0.05, 0.05) > sample_size_per_arm(0.05, 0.10)


def main():
    self_check()
    con = connect()
    sessions, buyers, days = con.execute(
        """SELECT count(*), count(*) FILTER (WHERE has_purchase), count(DISTINCT date_key)
           FROM fact_sessions
           WHERE date_key NOT IN (SELECT date_key FROM dq_tracking_gap_days)"""
    ).fetchone()
    con.close()
    p_base = buyers / sessions
    n_per_arm = sample_size_per_arm(p_base, MDE_RELATIVE)
    daily_sessions = sessions / days
    # Traffic alone would finish in ~1 day; run whole weeks so weekday/weekend behaviour is balanced.
    days_needed = max(MIN_DAYS, math.ceil(2 * n_per_arm / daily_sessions))

    rng = np.random.default_rng(SEED)
    total = 2 * n_per_arm
    n_treat = int(rng.binomial(total, 0.5))       # random 50/50 assignment
    n_ctrl = total - n_treat
    conv_ctrl = int(rng.binomial(n_ctrl, p_base))
    conv_treat = int(rng.binomial(n_treat, p_base * (1 + TRUE_LIFT_RELATIVE)))
    result = two_proportion_test(conv_ctrl, n_ctrl, conv_treat, n_treat)
    srm = srm_p_value(n_ctrl, n_treat)

    # A/A test: same rate in both arms; should usually NOT be significant.
    aa_ctrl = int(rng.binomial(n_ctrl, p_base))
    aa_treat = int(rng.binomial(n_treat, p_base))
    aa = two_proportion_test(aa_ctrl, n_ctrl, aa_treat, n_treat)

    significant = result["p_value"] < ALPHA and srm >= 0.001
    decision = ("Ship: lift is statistically significant and the split is healthy."
                if significant else
                "Do not ship yet: the result is not significant at the planned sample size. "
                "The CI includes effects too small to matter; rerun with a larger MDE budget or a stronger change.")

    out = {
        "label": "SIMULATED experiment - not a result from the historical data",
        "hypothesis": "Cart-page free-delivery banner raises session purchase conversion",
        "baseline_session_conversion": p_base,
        "alpha": ALPHA, "power": POWER, "mde_relative": MDE_RELATIVE,
        "sessions_per_arm_required": n_per_arm,
        "avg_daily_sessions": daily_sessions,
        "days_needed_at_full_traffic": days_needed,
        "min_days_rule": MIN_DAYS,
        "true_lift_injected": TRUE_LIFT_RELATIVE,
        "n_control": n_ctrl, "n_treatment": n_treat, "srm_p_value": srm,
        "conv_control": conv_ctrl, "conv_treatment": conv_treat,
        **result,
        "aa_p_value": aa["p_value"],
        "decision": decision,
    }
    (REPORTS / "ab_test_results.json").write_text(json.dumps(out, indent=2))
    print(f"  baseline conversion {p_base:.4%}; need {n_per_arm:,} sessions/arm (~{days_needed} days)")
    print(f"  simulated lift {result['rel_lift']:+.2%}, p={result['p_value']:.4f}, SRM p={srm:.3f}, A/A p={aa['p_value']:.3f}")
    print(f"  decision: {decision}")


if __name__ == "__main__":
    main()
