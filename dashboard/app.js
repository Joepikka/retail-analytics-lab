import { animate, inView, scroll, stagger } from "https://cdn.jsdelivr.net/npm/motion@11.11.17/+esm";

const D = window.DASHBOARD_DATA;
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
const $ = id => document.getElementById(id);
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const fmtInt = v => Math.round(v).toLocaleString("en-US");
const fmtMoney = v => "$" + (Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(2) + "M" : Math.abs(v) >= 1e3 ? (v / 1e3).toFixed(1) + "k" : v.toFixed(2));
const fmtPct = (v, d = 1) => (v * 100).toFixed(d) + "%";
const sum = (rows, k) => rows.reduce((a, r) => a + (r[k] || 0), 0);

// ---------- headline numbers
const revenue = sum(D.daily, "revenue");
const clean = D.daily.filter(r => !r.tracking_gap);
const conversion = sum(clean, "purchasing_sessions") / sum(clean, "sessions");
const repeatShare = D.repeat.filter(r => r.sort_key > 1).reduce((a, r) => a + r.revenue_share, 0);
const buyers = sum(D.repeat, "buyers");
const icon = p => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
const ICONS = {
  money: icon('<path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>'),
  rows: icon('<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5M3 12c0 1.7 4 3 9 3s9-1.3 9-3"/>'),
  users: icon('<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>'),
  cart: icon('<circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.7 13.4a2 2 0 0 0 2 1.6h9.7a2 2 0 0 0 2-1.6L23 6H6"/>'),
  repeat: icon('<path d="m17 1 4 4-4 4"/><path d="M3 11V9a4 4 0 0 1 4-4h14M7 23l-4-4 4-4"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/>'),
  check: icon('<path d="M22 11.1V12a10 10 0 1 1-5.9-9.1"/><path d="M22 4 12 14l-3-3"/>'),
  alert: icon('<path d="M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/>'),
  tag: icon('<path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L2 12V2h10l8.6 8.6a2 2 0 0 1 0 2.8Z"/><path d="M7 7h.01"/>'),
  layers: icon('<path d="m12 2 10 5-10 5L2 7l10-5Z"/><path d="m2 17 10 5 10-5M2 12l10 5 10-5"/>'),
  trend: icon('<path d="m22 7-8.5 8.5-5-5L2 17"/><path d="M16 7h6v6"/>'),
};

const kpis = [
  { cls: "span-6 feature", icon: ICONS.money, label: "Revenue analysed", value: revenue, fmt: v => "$" + (v / 1e6).toFixed(1) + "M", hint: "Oct–Nov 2019, reconciled to the cent" },
  { cls: "span-3", icon: ICONS.rows, label: "Events processed", value: D.quality[0].staged_rows, fmt: v => (v / 1e6).toFixed(1) + "M", hint: "4.6 GB compressed" },
  { cls: "span-3", icon: ICONS.users, label: "Buyers", value: buyers, fmt: fmtInt, hint: "of 5.3M visitors" },
  { cls: "span-4", icon: ICONS.cart, label: "Session conversion*", value: conversion, fmt: v => fmtPct(v, 2), hint: "*tracking-gap days excluded" },
  { cls: "span-4", icon: ICONS.repeat, label: "Revenue from repeat buyers", value: repeatShare, fmt: v => fmtPct(v, 1), hint: "42% of buyers" },
  { cls: "span-4", icon: ICONS.check, label: "Data tests passing", value: 14, fmt: v => Math.round(v) + " / 14", hint: "rows and revenue reconcile" },
];
$("kpis").innerHTML = kpis.map((k, i) => `
  <div class="card kpi ${k.cls}" data-kpi="${i}">
    <div class="label">${k.icon}${k.label}</div>
    <div class="value" data-value>${k.fmt(k.value)}</div>
    <div class="hint">${k.hint}</div>
  </div>`).join("");

// ---------- charts
Chart.defaults.font.family = css("--font-body");
Chart.defaults.color = css("--text-2");
Chart.defaults.borderColor = css("--grid");
Chart.defaults.plugins.legend.display = false;
Chart.defaults.maintainAspectRatio = false;
if (reduceMotion) Chart.defaults.animation = false;
const bar = { borderRadius: 4, borderSkipped: "start", borderWidth: 0, maxBarThickness: 26 };
const charts = {};  // created lazily when scrolled into view, so their own animation is seen

const gapDays = D.daily.filter(r => r.tracking_gap).map(r => r.date_key.slice(5));
const gapRevenue = sum(D.daily.filter(r => r.tracking_gap), "revenue");
$("gapText").textContent = `${D.gap_hours[0].hours} hours on ${gapDays.join(", ")} had normal traffic but zero purchases logged. Then 17 Nov showed $57.8M in one day, about 8× normal: delayed purchases arriving in a batch.`;

charts.daily = () => new Chart($("daily"), {
  type: "line",
  data: {
    labels: D.daily.map(r => r.date_key.slice(5)),
    datasets: [
      { label: "Daily revenue", data: D.daily.map(r => r.revenue), borderColor: css("--series-1"), borderWidth: 2, pointRadius: 0, pointHoverRadius: 5,
        segment: { borderDash: c => (D.daily[c.p1DataIndex]?.tracking_gap ? [4, 4] : undefined) } },
      { label: "7-day average", data: D.daily.map(r => r.revenue_7d_avg), borderColor: css("--series-2"), borderWidth: 2, pointRadius: 0, pointHoverRadius: 5 },
    ],
  },
  options: {
    interaction: { mode: "index", intersect: false },
    plugins: { tooltip: { callbacks: {
      label: c => `${c.dataset.label}: ${fmtMoney(c.raw)}`,
      afterBody: items => (D.daily[items[0].dataIndex].tracking_gap ? "Tracking gap: purchases not fully logged" : ""),
    } } },
    scales: { y: { beginAtZero: true, ticks: { callback: fmtMoney } }, x: { ticks: { maxTicksLimit: 10 } } },
  },
});

const cats = D.categories.slice(0, 12);
charts.categoryRevenue = () => new Chart($("categoryRevenue"), {
  type: "bar",
  data: { labels: cats.map(r => r.main_category), datasets: [{ data: cats.map(r => r.revenue), backgroundColor: css("--series-1"), ...bar }] },
  options: { indexAxis: "y", plugins: { tooltip: { callbacks: { label: c => `${fmtMoney(c.raw)} · ${fmtPct(cats[c.dataIndex].revenue_share)} of revenue` } } },
             scales: { x: { ticks: { callback: fmtMoney } }, y: { grid: { display: false } } } },
});
const unk = D.unknown_category[0];
if (unk) $("unknownNote").textContent = `Not shown: products with no category code, ${fmtMoney(unk.revenue)} (${fmtPct(unk.revenue_share)} of revenue).`;

$("brandSub").textContent = `${D.brands_for_80pct[0].n} of ${fmtInt(D.brand_count[0].n)} brands make up 80% of revenue.`;
charts.brands = () => new Chart($("brands"), {
  type: "bar",
  data: { labels: D.brands.map(r => r.brand), datasets: [{ data: D.brands.map(r => r.revenue_share), backgroundColor: css("--series-1"), ...bar }] },
  options: { indexAxis: "y", plugins: { tooltip: { callbacks: { label: c => `${fmtPct(c.raw)} of revenue · cumulative ${fmtPct(D.brands[c.dataIndex].cumulative_share)}` } } },
             scales: { x: { ticks: { callback: v => fmtPct(v, 0) } }, y: { grid: { display: false } } } },
});

$("funnelTable").innerHTML = "<caption>Sessions by category, Oct–Nov 2019</caption><tr><th>Category</th><th>Viewed</th><th>Bought</th><th>View → buy</th><th>Revenue share</th></tr>" +
  cats.map(r => `<tr><td>${r.main_category}</td><td>${fmtInt(r.sessions_viewed)}</td><td>${fmtInt(r.sessions_purchased)}</td><td>${fmtPct(r.view_to_purchase, 2)}</td><td>${fmtPct(r.revenue_share)}</td></tr>`).join("");

charts.price = () => new Chart($("price"), {
  type: "bar",
  data: { labels: D.price_bands.map(r => r.price_band.slice(3)), datasets: [{ data: D.price_bands.map(r => r.purchases_per_view), backgroundColor: css("--series-1"), ...bar }] },
  options: { plugins: { tooltip: { callbacks: { label: c => `${fmtPct(c.raw, 2)} · ${fmtInt(D.price_bands[c.dataIndex].views)} views` } } },
             scales: { y: { beginAtZero: true, ticks: { callback: v => fmtPct(v, 1) } }, x: { grid: { display: false } } } },
});

charts.repeat = () => new Chart($("repeat"), {
  type: "bar",
  data: {
    labels: D.repeat.map(r => r.buyer_segment),
    datasets: [
      { label: "Share of buyers", data: D.repeat.map(r => r.buyer_share), backgroundColor: css("--series-1"), ...bar },
      { label: "Share of revenue", data: D.repeat.map(r => r.revenue_share), backgroundColor: css("--series-2"), ...bar },
    ],
  },
  options: { plugins: { tooltip: { callbacks: { label: c => `${c.dataset.label}: ${fmtPct(c.raw)}` } } },
             scales: { y: { beginAtZero: true, ticks: { callback: v => fmtPct(v, 0) } }, x: { grid: { display: false } } } },
});

// ---------- heatmaps: one-hue ramp, value always printed
const seq = [0, 1, 2, 3, 4, 5].map(i => css("--seq-" + i));
const isDark = () => document.documentElement.dataset.theme === "dark" ||
  (matchMedia("(prefers-color-scheme: dark)").matches && document.documentElement.dataset.theme !== "light");
function heatCell(v, lo, hi, text, title) {
  const i = Math.min(5, Math.floor((hi > lo ? (v - lo) / (hi - lo) : 0) * 6));
  const light = isDark() ? i <= 2 : i >= 4;
  return `<td class="${light ? "ink-light" : ""}" style="background:${seq[i]}" title="${title}">${text}</td>`;
}
const weeks = [...new Set(D.cohorts.map(r => r.cohort_week))].sort();
const maxLag = Math.max(...D.cohorts.map(r => r.weeks_since_first));
const cHi = Math.max(...D.cohorts.filter(r => r.weeks_since_first > 0).map(r => r.retention), 0.01);
let ch = "<tr><th>Cohort</th><th>Buyers</th>" + Array.from({ length: maxLag }, (_, i) => `<th>+${i + 1}w</th>`).join("") + "</tr>";
for (const w of weeks) {
  const rows = D.cohorts.filter(r => r.cohort_week === w);
  ch += `<tr><td>${w.slice(5)}</td><td>${fmtInt(rows[0].cohort_size)}</td>`;
  for (let k = 1; k <= maxLag; k++) {
    const r = rows.find(x => x.weeks_since_first === k);
    ch += r ? heatCell(r.retention, 0, cHi, fmtPct(r.retention), `${fmtInt(r.buyers)} buyers`) : "<td></td>";
  }
  ch += "</tr>";
}
$("cohortTable").insertAdjacentHTML("beforeend", ch);

const days = [...new Map(D.hour_dow.map(r => [r.iso_dow, r.day_name])).entries()].sort((a, b) => a[0] - b[0]);
const conv = D.hour_dow.map(r => r.session_conversion);
const hLo = Math.min(...conv), hHi = Math.max(...conv);
let hh = "<tr><th>Day</th>" + Array.from({ length: 24 }, (_, h) => `<th>${h}</th>`).join("") + "</tr>";
for (const [dow, name] of days) {
  hh += `<tr><td>${name.slice(0, 3)}</td>`;
  for (let h = 0; h < 24; h++) {
    const r = D.hour_dow.find(x => x.iso_dow === dow && x.hour_utc === h);
    hh += r ? heatCell(r.session_conversion, hLo, hHi, (r.session_conversion * 100).toFixed(1), `${name} ${h}:00 UTC · ${fmtInt(r.sessions)} sessions`) : "<td></td>";
  }
  hh += "</tr>";
}
$("hourTable").insertAdjacentHTML("beforeend", hh);

// ---------- forecast
const F = D.forecast;
if (F) {
  $("fcSub").textContent = `Trained on ${F.train[2]} clean days, then forecast ${F.test[2]} days ahead from 13 Nov. Compared honestly against three simple baselines.`;
  charts.forecastChart = () => new Chart($("forecastChart"), {
    type: "line",
    data: {
      labels: F.daily.map(r => r.date.slice(5)),
      datasets: [
        { label: "80% upper", data: F.daily.map(r => r.regression_upper80), borderWidth: 0, pointRadius: 0, fill: "+1", backgroundColor: css("--series-2") + "24" },
        { label: "80% lower", data: F.daily.map(r => r.regression_lower80), borderWidth: 0, pointRadius: 0, fill: false },
        { label: "Actual", data: F.daily.map(r => r.actual), borderColor: css("--series-1"), borderWidth: 2, pointRadius: 3 },
        { label: "Regression", data: F.daily.map(r => r.trend_weekday_regression), borderColor: css("--series-2"), borderWidth: 2, pointRadius: 0, pointHoverRadius: 5 },
        { label: "Seasonal naive", data: F.daily.map(r => r.seasonal_naive), borderColor: css("--series-3"), borderWidth: 2, borderDash: [5, 4], pointRadius: 0, pointHoverRadius: 5 },
      ],
    },
    options: {
      interaction: { mode: "index", intersect: false },
      plugins: { tooltip: { filter: i => !i.dataset.label.startsWith("80%"), callbacks: { label: c => `${c.dataset.label}: ${fmtMoney(c.raw)}` } } },
      scales: { y: { beginAtZero: true, ticks: { callback: fmtMoney } } },
    },
  });
  const names = { trend_weekday_regression: "Trend + weekday regression", seasonal_naive: "Seasonal naive",
                  weekday_mean_28d: "Weekday mean, 28 days", naive_last_day: "Naive (last day)" };
  $("fcTable").innerHTML = "<caption>Error on 18–30 Nov (lower is better)</caption><tr><th>Model</th><th>MAPE</th><th>excl. Black Friday</th></tr>" +
    Object.entries(F.results).sort((a, b) => a[1].excluding_black_friday.mae - b[1].excluding_black_friday.mae)
      .map(([k, r]) => `<tr><td>${names[k] || k}</td><td>${fmtPct(r.all_test_days.mape)}</td><td>${fmtPct(r.excluding_black_friday.mape)}</td></tr>`).join("");
  $("fcNote").textContent = `The 80% interval covered ${fmtPct(F.regression_80pct_interval_coverage, 0)} of days. Black Friday: ${fmtMoney(F.black_friday.actual)} actual vs ${fmtMoney(F.black_friday.regression_forecast)} forecast, because the model has no promotion feature.`;
}

const t = D.ab_test;
$("ab").innerHTML = !t ? "" : `
  <p class="sub">${t.hypothesis}. The history is observational, so the real baseline is used to size and analyse a <strong>simulated</strong> test.</p>
  <div class="bento" style="gap:12px">
    ${[["Baseline conversion", fmtPct(t.baseline_session_conversion, 2)],
       ["Sessions per arm", fmtInt(t.sessions_per_arm_required)],
       ["Minimum run", `${t.days_needed_at_full_traffic} days`],
       ["Sample-ratio check p", t.srm_p_value.toFixed(3)],
       ["Measured lift (true 4%)", fmtPct(t.rel_lift, 2)],
       ["p-value · A/A p", `${t.p_value.toFixed(4)} · ${t.aa_p_value.toFixed(2)}`]]
      .map(([k, v]) => `<div class="span-4" style="grid-column:span 4"><div class="sub" style="margin:0">${k}</div><div class="mono" style="font-size:22px;font-weight:600">${v}</div></div>`).join("")}
  </div>
  <p class="note">Design: α = ${t.alpha}, power = ${t.power}, minimum detectable lift ${fmtPct(t.mde_relative, 0)}. ${t.decision}</p>`;

// ---------- business impact
const unknownRev = unk ? unk.revenue : 0;
const topRepeat = D.repeat.find(r => r.sort_key >= 11);
const brandTop2 = D.brands.slice(0, 2).reduce((a, r) => a + r.revenue_share, 0);
const impact = [
  { icon: ICONS.alert, title: "Alert on broken tracking", finding: `${gapDays.length} days of revenue reporting are unreliable: ${fmtMoney(gapRevenue)} was reported on them, much of it late.`,
    action: "Run the hourly zero-purchase check as an alert.", value: "Every revenue and conversion number depends on this one event." },
  { icon: ICONS.tag, title: "Fix product categories", finding: `${fmtMoney(unknownRev)} (${fmtPct(unk ? unk.revenue_share : 0)}) of revenue has no category.`,
    action: "Require a category code in the product feed.", value: "Makes one-tenth of revenue reportable at no customer-facing risk." },
  { icon: ICONS.users, title: "Find the power buyers", finding: `${fmtInt(topRepeat.buyers)} buyers (${fmtPct(topRepeat.buyer_share)}) produced ${fmtPct(topRepeat.revenue_share)} of revenue.`,
    action: "Check if they are resellers. Test a B2B path or a loyalty offer.", value: "Protects the most valuable quarter of revenue." },
  { icon: ICONS.layers, title: "Reduce brand dependency", finding: `Two brands are ${fmtPct(brandTop2)} of revenue.`,
    action: "Grow appliances and computers, the next categories by revenue.", value: "Limits the damage from one supplier or price change." },
  { icon: ICONS.trend, title: "Track where traffic comes from", finding: "November brought 49% more sessions, but conversion fell from 6.8% to 5.2%.",
    action: "Record the traffic source before spending more on acquisition.", value: "Stops paying for visitors who don't buy." },
];
$("impactGrid").innerHTML = impact.map((c, i) => `
  <article class="card ${i < 2 ? "span-6" : "span-4"}" data-reveal>
    <div class="kpi"><div class="label">${c.icon}<span class="mono">0${i + 1}</span></div></div>
    <h3 style="margin-top:10px">${c.title}</h3>
    <p class="sub" style="margin:6px 0">${c.finding}</p>
    <p style="margin:0 0 6px"><strong>Do:</strong> ${c.action}</p>
    <p class="note" style="margin:0">${c.value}</p>
  </article>`).join("");

// ---------- data quality
const q = D.quality[0];
$("dqTable").innerHTML = [
  ["Staged rows", fmtInt(q.staged_rows)], ["Exact duplicates removed", fmtInt(sum(D.duplicates, "duplicate_rows_removed"))],
  ["Missing category code", fmtPct(q.missing_category_code / q.staged_rows)], ["Missing brand", fmtPct(q.missing_brand / q.staged_rows)],
  ["Price ≤ 0 (excluded from revenue)", fmtInt(q.non_positive_price)], ["Hours with traffic, zero purchases", fmtInt(D.gap_hours[0].hours)],
].map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("");

// ---------- nav state
const nav = $("nav");
const setNav = () => nav.classList.toggle("solid", scrollY > innerHeight * 0.6);
setNav();
addEventListener("scroll", setNav, { passive: true });
const links = [...document.querySelectorAll(".nav-links a")];
for (const a of links) {
  inView(a.getAttribute("href"), () => {
    links.forEach(l => l.classList.toggle("active", l === a));
  }, { amount: 0.25 });
}

// ---------- charts render when first seen
for (const [id, make] of Object.entries(charts)) {
  inView("#" + id, () => { make(); }, { amount: 0.1 });
}

// ---------- motion (skipped entirely for reduced motion)
if (!reduceMotion) {
  scroll(animate("#progress", { scaleX: [0, 1] }, { ease: "linear" }));

  // Motion's animate() does not persist the end state, so commit it inline first;
  // otherwise the CSS start state (opacity 0) returns when the animation ends.
  inView("[data-reveal]", ({ target: el }) => {  // Motion 11 passes the IntersectionObserverEntry
    el.style.opacity = "1";
    el.style.transform = "none";
    animate(el, { opacity: [0, 1], transform: ["translateY(24px)", "translateY(0px)"] }, { duration: 0.6, ease: [0.22, 1, 0.36, 1] });
  }, { amount: 0.15 });

  inView("#kpis", () => {
    animate("#kpis .card", { opacity: [0, 1], transform: ["translateY(20px) scale(0.97)", "translateY(0px) scale(1)"] }, { delay: stagger(0.07), duration: 0.5, ease: [0.22, 1, 0.36, 1] });
    document.querySelectorAll("#kpis [data-kpi]").forEach(card => {
      const k = kpis[+card.dataset.kpi];
      const out = card.querySelector("[data-value]");
      animate(0, k.value, { duration: 1.4, ease: [0.16, 1, 0.3, 1], onUpdate: v => { out.textContent = k.fmt(v); } });
    });
  }, { amount: 0.3 });

  inView("#pipeline", () => {
    animate("#pipeLine", { strokeDashoffset: [100, 0] }, { duration: 1.2, ease: "easeInOut" });
    animate("#pipeline [data-step]", { opacity: [0, 1], transform: ["translateY(16px)", "translateY(0px)"] }, { delay: stagger(0.12), duration: 0.45 });
  }, { amount: 0.3 });

  inView("#testRing", () => {
    animate("#testRing", { strokeDasharray: ["0 100", "100 100"] }, { duration: 1.2, ease: [0.16, 1, 0.3, 1] });
  });
}
