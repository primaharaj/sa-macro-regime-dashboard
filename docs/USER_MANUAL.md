# SA Macro Regime & Divergence Engine — User Manual

> **This is an analytical research tool, not financial advice. No claim of predictive edge is made.**
> See [Section 7 — Responsible Interpretation](#7-responsible-interpretation) before acting on any output.

---

## Contents

1. [What This Is](#1-what-this-is)
2. [Quick Start](#2-quick-start)
3. [Signal Families](#3-signal-families)
4. [Confidence & Point-in-Time Discipline](#4-confidence--point-in-time-discipline)
5. [Live Data Edge](#5-live-data-edge)
6. [Divergence Detector](#6-divergence-detector)
7. [Responsible Interpretation](#7-responsible-interpretation)
8. [Known Limitations & Data Seams](#8-known-limitations--data-seams)
9. [Methodology Reference](#9-methodology-reference)

---

## 1. What This Is

The SA Macro Regime & Divergence Engine is a research tool that monitors South African macroeconomic conditions and compares them against the technical posture (price trend and momentum) of SA-related instruments. Its purpose is to surface situations where price is doing something that the macro backdrop does not justify — or vice versa.

**What it does not do:**

- It does not predict whether a trade will make money.
- It does not cover assets outside the configured instrument list.
- It does not make recommendations. It surfaces disagreements and lets you investigate them.
- Historical regime descriptions are not forecasts of what the same regime will produce in the future.

The tool is designed for institutional or analytical research where the user already has domain knowledge and is using the engine as a structured cross-check, not an oracle.

### Methodology

The engine has two signal families (Fundamental and Technical), a confidence layer, a live data resolver, and a divergence detector. All historical signals are computed strictly on data that was available at the measurement date — no future information bleeds back. This property is called **Point-in-Time (PIT) discipline** and is described in [Section 4](#4-confidence--point-in-time-discipline).

The single validated historical window where both signal families are simultaneously at HIGH confidence is **2014-12-01 to 2017-06-25**. Outside this window, one or both families will carry reduced confidence, and the UI will indicate this.

---

## 2. Quick Start

**Prerequisites**

- Python 3.10+
- `FRED_API_KEY` environment variable set ([obtain free key at FRED](https://fred.stlouisfed.org/))
- Dependencies installed: `pip install -r requirements.txt`

**First run**

```bash
# 1. Populate the local DuckDB from FRED, World Bank, Yahoo Finance
python -m src.vintage_store

# 2. Launch the dashboard
streamlit run app.py
```

The database file is written to `data/macro_data.db`. Repopulating is idempotent: all inserts are `INSERT OR IGNORE`.

**Refreshing live data**

The live-edge sources (CPI from SAMADB, repo rate from the manual MPC table) are not fetched automatically on every run. To refresh them:

```python
from src.vintage_store import VintageStore
store = VintageStore()
store.populate_live()
```

This fetches the latest SAMADB CPI index and re-reads the MPC decisions from `src/sources/mpc_repo.py`. The manual MPC table must be updated by hand within one business day of each SARB announcement (roughly six times per year).

**Dashboard pages**

- **Home / Signals**: Technical and fundamental signal panel for each instrument.
- **Signal Divergence** (`pages/2_Signal_Divergence.py`): Tech-vs-macro divergence chart with flag shading, divergence series, and single-date detail packets.

---

## 3. Signal Families

### 3.1 Fundamental Signals (SA Macro Backdrop)

In plain terms, these five signals describe the SA monetary and growth environment. Together they answer: *Is the SA macro backdrop currently supportive or hostile for risk assets and ZAR?*

| Signal | What it measures | High value means |
|---|---|---|
| `real_policy_rate` | Repo rate minus inflation (YoY) | SA monetary policy is tight / hawkish |
| `real_long_yield` | 10-year SA bond yield minus inflation | Long real rates are elevated |
| `curve_slope` | 10-year yield minus repo rate | Yield curve is steep (positive) |
| `inflation_trend` | 3-month change in YoY inflation | Inflation is accelerating |
| `growth_backdrop` | Annual GDP growth (World Bank) | SA economy is expanding |

Each signal is expressed in two forms:

- **Raw**: the underlying number in its natural unit (%, percentage points, etc.)
- **Normalised (0–100)**: where the current reading sits in its own 10-year history. 50 = median. 100 = all-time high within the window.

Normalised values are what drive both the dashboard displays and the divergence engine. Raw values are shown for diagnostic purposes.

#### Methodology

**real_policy_rate** = `repo_rate − inflation_yoy`

- `repo_rate`: sourced from the macro resolver (see [Section 5](#5-live-data-edge)).
- `inflation_yoy`: derived from CPI series via the resolver-declared unit:
  - If `cpi_samadb` (index level, base Dec 2024=100): `(index_t / index_{t-12} − 1) × 100`
  - If `cpi` (FRED ALFRED, MoM %): `(∏ᵢ₌₁¹² (1 + MoMᵢ/100)) − 1`, compounded annually

**real_long_yield** = `yield_10y − inflation_yoy`

**curve_slope** = `yield_10y − repo_rate`

**inflation_trend** = `inflation_yoy.diff(3)` — 3-month change in the YoY rate, capturing acceleration or deceleration rather than level.

**growth_backdrop** = Annual GDP growth rate (World Bank `NY.GDP.MKTP.KD.ZG`), forward-filled at monthly frequency.

Normalisation window: 120 months (10 years). Percentile is computed as `(history < current_value).mean() × 100`, consistent across all normalised fields.

---

### 3.2 Technical Signals (Price Posture)

These signals describe what prices are doing, independent of why. They answer: *Is this instrument currently trending and/or accelerating beyond its own recent history?*

| Signal | Window | What it measures |
|---|---|---|
| `trend` | 252-day MA | `(price / MA_252) − 1` — deviation from one-year moving average |
| `momentum` | 21-day | `(price / price.shift(21)) − 1` — one-month rate of change |
| `volatility` | 63-day | Rolling std of log returns × √252 — annualised realised vol |

All three are normalised to [0, 100] using the same percentile method as fundamentals, but over a 252-day trailing window.

**Volatility informs confidence and context; it does not enter the directional posture calculation.** A high-vol environment raises uncertainty about trend and momentum persistence; it is not itself bullish or bearish.

#### Methodology

```
trend_raw   = (P_t / MA_252(P)_t) − 1
momentum_raw = (P_t / P_{t−21}) − 1
vol_raw     = std(log(P_t / P_{t−1}), window=63) × √252
```

All series are read through the PIT store (`store.get_series(name, as_of_date)`) which enforces `observation_date ≤ as_of_date` for market prices (NOT_REVISED class). No future price can enter a historical signal computation.

---

## 4. Confidence & Point-in-Time Discipline

### Confidence Labels

Every signal carries a confidence label — **HIGH**, **MEDIUM**, or **LOW** — based on two independent dimensions:

1. **Sufficiency**: How much history is available for normalisation relative to the required window?
   - Fundamental signals need 24+ months of history. Below 50% of that: LOW. Below 80%: MEDIUM.
   - Technical signals need 24+ data points (same thresholds).

2. **Staleness**: Is the underlying observation overdue?
   - Staleness is measured as *days past the expected next release*, not days since the last observation.
   - This prevents the "monthly flicker" where a signal would drop to MEDIUM immediately after a release just because the next one is due in 30 days.

**Staleness formula:**
```
overdue_days = max(0, as_of_date − (observation_date + native_frequency + typical_lag))
```

**Confidence thresholds** (applied to both sufficiency and staleness, worst-of rule):
- HIGH: sufficiency ≥ 80% AND overdue_days ≤ lag_threshold
- MEDIUM: sufficiency ≥ 50% AND overdue_days ≤ 2 × lag_threshold
- LOW: either below MEDIUM threshold

**Instrument-specific lag thresholds:**
- Market data (prices): `lag_threshold = 2 days` (prices are daily; if you haven't seen a close in 2 days, something is wrong)
- CPI / repo: `lag_threshold = 10 days`
- GDP: `lag_threshold = 90 days` (annual release; 90 days past expected = genuinely stale)

**The divergence confidence rule**: `confidence = min(tech_confidence, macro_confidence)`. A divergence flag built on LOW-confidence inputs is itself LOW-confidence and is marked `actionable = False` regardless of how large the posture gap is.

### Point-in-Time Discipline

The store is a DuckDB table with primary key `(canonical_name, observation_date, as_of_date)`. Every query for historical data adds the constraint `as_of_date ≤ T` so that signals computed at date T cannot see data that was published after T.

**Three vintage classes control how PIT queries work:**

| Class | Examples | PIT mechanism |
|---|---|---|
| `BACKFILLABLE` | CPI (FRED ALFRED), repo rate (FRED ALFRED), 10-year yield (FRED ALFRED) | ALFRED stores every revision. Query: latest `as_of_date ≤ T` for each `observation_date`. |
| `NOT_REVISED` | USD/ZAR, JSE ALSI, EZA, SPY, US 10Y | Market prices are never revised. `as_of_date = observation_date`. Query: `observation_date ≤ T`. |
| `REVISED_NO_VINTAGE` | GDP (World Bank), CPI (SAMADB), Repo (MPC table) | No vintage API. Data is stamped with today's date on ingest. Returns empty if `T < first_capture_date`. |

**The no-look-ahead guarantee is proven in the test suite.** `tests/test_signals.py::test_truncation_leak` and `tests/test_divergence.py::test_pit_survival` each:
1. Compute a signal at date T with the full DB.
2. Open a transaction and delete all rows where `observation_date > T OR as_of_date > T`.
3. Recompute at T.
4. Assert the results are numerically identical (to 10 decimal places).
5. Roll back the transaction.

If any look-ahead exists, step 3 would produce a different number. Both tests pass on every run.

---

## 5. Live Data Edge

The SA macro data landscape has a structural lag problem: FRED publishes SA indicators 4–6 months after the StatsSA release date. The engine resolves this with a live-edge layer that routes macro concepts to the best available source for each `as_of_date`.

### CPI

**Before `first_capture_date` of `cpi_samadb`:** Uses FRED ALFRED series `CPALTT01ZAM657N` (monthly MoM %). YoY is derived by compounding 12 monthly rates.

**From `first_capture_date` onwards:** Uses SAMADB series `CPS00000` (index level, base Dec 2024 = 100). YoY is derived as `(index_t / index_{t−12} − 1) × 100`. The two sources are never mixed — the formula is selected by the `unit` field declared by the resolver.

Validation: `test_signals.py::test_cpi_derivation` confirms that at `as_of_date = 2024-05-01`, the derived `inflation_yoy ≈ 5.55%`, matching the StatsSA Feb 2024 headline of 5.6%.

### Repo Rate

FRED `IRSTCB01ZAM156N` is frozen at Dec 2023 (8.25%). SAMADB `KBP1401M` is frozen at Oct 2023 (8.25%). Neither tracks MPC decisions after that date.

The resolver always uses `repo_mpc` — a manually maintained step-function table in `src/sources/mpc_repo.py`. Current state as of the last DB populate:

| Decision date | Effective date | Action | Rate |
|---|---|---|---|
| 2025-11-20 | 2025-11-21 | cut | 6.75% |
| 2026-01-29 | 2026-01-30 | hold | 6.75% |
| 2026-03-26 | 2026-03-27 | hold | 6.75% |
| 2026-05-28 | 2026-05-29 | hike | 7.00% |

**This table must be updated manually after each MPC announcement.** Next scheduled MPC meeting: ~23 July 2026.

For historical queries (T < `first_capture_date` of `repo_mpc`), the resolver falls back to FRED `repo_rate` for the normalisation history, but always uses the live scalar from `repo_mpc` as the current reading.

### 10-Year Yield

Always FRED `IRLTLT01ZAM156N`. Current to approximately April 2026. No live substitute has been implemented. When this series goes stale, `real_long_yield` and `curve_slope` will carry LOW confidence.

### Live Boundary Marker

The Signal Divergence page draws a dashed vertical line at the `first_capture_date` of `cpi_samadb`. Data to the left of this line uses FRED vintages; data to the right uses live SAMADB + manual MPC sources. The live region is less historically validated: the normalisation percentiles for the live signals are based on a shorter SAMADB history than the FRED ALFRED multi-decade series.

---

## 6. Divergence Detector

### What It Does (Plain Language)

The divergence detector asks: *Is the price of this instrument doing something that the SA macro backdrop cannot justify?*

It computes two numbers on a 0–100 scale:

- **Tech posture**: where the instrument's price trend and momentum sit relative to the past year. 100 = price has never been this far above its moving average and rising this fast. 0 = the opposite.
- **Macro posture**: where the SA macro backdrop sits, oriented so that HIGH means "macro is supportive of this instrument's price level."

The **divergence** = tech posture − macro posture.

If the absolute divergence is larger than it has been for 80% of the past year (i.e., in the top quintile of the trailing distribution), the detector raises a **flag**.

A flag does not say *what* will happen. It says that price and macro are unusually far apart, and one of them is probably wrong.

**Outlier family** tells you which side is doing the unusual thing:
- `technicals`: price moved more than macro can explain.
- `macro`: macro moved more than price has reflected.
- `both`: both are simultaneously unusual.
- `aligned`: no clear outlier (e.g., a genuine trend where both sides are elevated together).

### Per-Instrument Orientation

The macro posture is signed differently for each instrument so that HIGH always means "macro is supportive of a higher price level."

**JSE ALSI** — `macro_posture HIGH = SA macro is supportive for equity`:

| Sub-signal | Direction | Rationale |
|---|---|---|
| `growth_backdrop` | +1 (direct) | High growth → earnings positive |
| `real_policy_rate` | −1 (inverted) | Low real rate → easy credit, low discount rate → bullish |
| `inflation_trend` | −1 (inverted) | Falling inflation → less CB tightening → bullish |

**USD/ZAR** — `macro_posture HIGH = macro justifies ZAR weakness (high USDZAR)`:

| Sub-signal | Direction | Rationale |
|---|---|---|
| `growth_backdrop` | −1 (inverted) | Low SA growth → ZAR weak → high USDZAR supported |
| `real_policy_rate` | −1 (inverted) | Low real rate → less hawkish → ZAR weak |
| `inflation_trend` | +1 (direct) | Rising inflation → ZAR erodes → high USDZAR supported |

> **CRITICAL — USDZAR sign**: A hawkish/high-real-rate backdrop is **ZAR-supportive**, arguing for **lower** USDZAR, which maps to a **LOW** macro_posture for USDZAR. The direction=−1 assignment on `real_policy_rate` achieves this: `contribution = 100 − normalised_value`. When real rates are high (normalised near 100), contribution = 100 − 100 = 0 (macro_posture LOW = macro argues against USDZAR rising). When real rates are low (normalised near 0), contribution = 100 − 0 = 100 (macro_posture HIGH = macro supports USDZAR rising). **If this sign were reversed, every ZAR divergence result would be backwards.**
>
> Proof: At 2019-07-01 (hawkish peak, normalised ≈ 89.2), `real_policy_rate` contribution = 100 − 89.2 = 10.8 → macro_posture LOW (≈ 45.6) — correct, macro argues against USDZAR rising. At 2021-07-01 (dovish floor, normalised ≈ 5.0), contribution = 100 − 5.0 = 95.0 → macro_posture HIGH (≈ 80.8) — correct, macro supports USDZAR rising.

**SAF Equity ETF (EZA)** — same orientation as JSE ALSI. Secondary target: EZA is USD-denominated; USD/ZAR movements affect the ETF price independently of SA macro. The SA macro_posture does not capture the USD channel, so EZA divergences may partly reflect currency effects.

### Validated Case: Dec 2015 Nene Shock

On 9 December 2015 (evening), President Zuma fired Finance Minister Nhlanhla Nene without notice. USDZAR spiked roughly 13% in three days. This event is the primary acceptance test for the divergence detector.

**At 2015-12-11** (first full trading session after the announcement):
- tech_posture ≈ 99.2 (price well above its 252-day MA, 21-day momentum extreme)
- macro_posture ≈ 45.3 (SA macro unchanged — monthly data does not revise in response to a 3-day political shock)
- divergence ≈ 53.9
- percentile ≈ 84.5 → **FLAGGED** (above 80th percentile threshold)
- outlier_family = `technicals` (price spiked; macro did not move)

By 2016-08-01 (calm control period), USDZAR had partially normalised and SA macro was stable. The detector does **not** flag at that date (percentile ≈ 67.5 < 80th), confirming it discriminates between genuine divergences and ordinary volatility.

Both cases are codified in `tests/test_divergence.py`.

### Methodology

**Tech posture (vectorized)**:
```
ma_252          = prices.rolling(252).mean()
trend_pct       = rolling_percentile(prices/ma_252 − 1, window=252)
momentum_pct    = rolling_percentile(prices/prices.shift(21) − 1, window=252)
tech_posture    = (trend_pct + momentum_pct) / 2
```

`rolling_percentile(series, window)` uses `lambda x: (x[:-1] < x[-1]).mean() × 100`, excluding the current value from its own comparison (consistent with `calculate_percentile` in `normalise.py`).

**Macro posture (current date, from SignalAPI)**:
```
for each sub_signal, direction in instrument_components:
    normalised = sub_signal["normalised"]
    contribution = normalised if direction == +1 else 100 − normalised
macro_posture = mean(contributions)
```

Sub-signals with `staleness_days ≥ 500` are excluded from the confidence minimum (but their normalised value still enters the posture mean). This prevents `gdp_growth` — which is REVISED_NO_VINTAGE and returns empty for all dates before its first_capture_date — from dragging every historical macro confidence to LOW.

**Flagging**:
```
trailing_abs = abs(divergence_series).iloc[−252:]
percentile   = (trailing_abs < abs_current_divergence).mean() × 100
flagged      = percentile ≥ 80.0
```

The trailing window is **252 trading days (one year)**. A 3-year window would include the Jan 2014 rand shock, which would inflate the threshold enough that the Dec 2015 Nene peak barely clears it — wrong behaviour for a detector that should calibrate to the current volatility regime.

**Attribution (outlier_family)**:
```
tech_z  = |tech_posture  − trailing_mean(tech)| / trailing_std(tech)
macro_z = |macro_posture − trailing_mean(macro)| / trailing_std(macro)

if tech_z > macro_z × 1.5:  outlier = "technicals"
elif macro_z > tech_z × 1.5: outlier = "macro"
elif tech_z > 1.5 and macro_z > 1.5: outlier = "both"
else: outlier = "aligned"
```

---

## 7. Responsible Interpretation

### This is NOT financial advice

The output of this engine — signals, postures, divergence flags, confidence labels — is analytical context, not a recommendation to buy, sell, or hold any instrument. Past macro regimes and their association with price movements do not guarantee future outcomes.

### What flags mean and do not mean

A flag means the absolute divergence between tech posture and macro posture is in the top quintile of the past year's distribution. It does not mean:

- The divergence will close. Both price and macro could remain where they are.
- The outlier family will "correct". Macro can move toward price just as easily as price can move toward macro.
- The timing of any convergence is knowable.

Flags in the live region (after the `cpi_samadb` first capture date) are additionally limited by the shorter normalisation history of live data sources.

### Confidence labels are substantive

LOW confidence is not a cosmetic warning. A LOW-confidence divergence packet has `actionable = False`. The detector does not distinguish between "LOW because data is slightly stale" and "LOW because the fundamental normalisation history is only 8 months old." If the label is LOW, the signal should not be used to support a decision.

### Orientation must be checked before interpreting direction

For USDZAR, a **high** tech posture with a **low** macro posture means price has risen (ZAR weakened) more than the SA macro backdrop justifies. This is a `technicals` outlier — price outran macro. Misreading the orientation of macro_posture for USDZAR (treating HIGH as "macro is hawkish/ZAR-supportive" rather than "macro supports a weak ZAR") inverts every divergence conclusion. The UI expander "Macro posture orientation for this instrument" explains the sign for each instrument.

---

## 8. Known Limitations & Data Seams

The following are known boundaries of the engine's reliability. They are not bugs — they are documented constraints.

### FRED ALFRED coverage starts around 2013 for SA series

ALFRED's `realtime_start` parameter requests all historical vintages. However, FRED's SA coverage has gaps before 2013 for some series. Signals computed before 2013 may have sparse normalisation histories and will carry MEDIUM or LOW confidence.

### FRED CPI series vs StatsSA

The FRED CPI series (`CPALTT01ZAM657N`) is sourced from OECD and may not match StatsSA headline CPI exactly. A known anomaly exists around 2023-01-01 where the derived `real_policy_rate.raw ≈ −6.86%`, which is implausible given SA actual rates. The suspected cause is a StatsSA CPI rebasing (base 2016 → 2021) in 2022 that created a discontinuity in the FRED/OECD series. This anomaly has been noted but not investigated. Users doing analysis through 2022–2024 on the FRED vintage path should verify CPI-derived signals against StatsSA published rates.

### Repo rate normalisation gap: Dec 2023 to Nov 2025

FRED `repo_rate` (ALFRED) is frozen at December 2023 (8.25%). The manual MPC table (`repo_mpc`) covers decisions from November 2025 onwards. The gap between December 2023 and November 2025 is not covered by a live source. For historical queries in this window, the FRED legacy value (8.25%) is used as the fallback — which was **not** the actual repo rate throughout 2024–2025 (the SARB cut rates during this period). Any signal computed with `as_of_date` in this gap will have an incorrect `repo_rate` input.

The November 2025 effective date in the MPC table is marked as estimated (±1 week). If precise historical reconstruction at that date matters, verify against SAnews/SARB records.

### SAMADB and repo_mpc have no vintage history

Both `cpi_samadb` and `repo_mpc` are REVISED_NO_VINTAGE: their data is stamped with the date of the populate call, not the original publication dates. This means:

- You cannot reconstruct what the SAMADB CPI index looked like as it was known on a specific historical date.
- Any revision to the underlying StatsSA data will silently overwrite the stored values on the next `populate_live()` call.
- The live-region normalisation percentiles use the current values for all historical observation dates, not the values as they were reported at the time.

For the validated historical window (2014–2017), neither `cpi_samadb` nor `repo_mpc` are used — the engine routes to FRED ALFRED vintage data, which does carry genuine PIT discipline for that period.

### GDP (World Bank) is always REVISED_NO_VINTAGE

GDP growth is annual (World Bank `NY.GDP.MKTP.KD.ZG`) and has no vintage API. The `growth_backdrop` signal at any historical date reflects the most recent World Bank revision available at the time of the last `populate()` call, not the vintage that was available at that date. GDP staleness at historical dates before the first populate call will show `staleness_days = 999` and confidence = LOW; the divergence engine excludes these LOW confidence labels from the posture confidence minimum specifically to avoid this placeholder dragging all historical packets to LOW.

### Validation window is 2014–2017

The acceptance tests (`test_divergence.py`, `test_signals.py`) are anchored in the 2014-12-01 to 2017-06-25 window where FRED ALFRED (for macro) and Yahoo Finance (for prices) are both confirmed HIGH-confidence. No systematic validation has been done outside this window. Results outside it may be correct, but they have not been checked against a known benchmark event.

---

## 9. Methodology Reference

### Core formulas

**YoY CPI from SAMADB index level:**
```
CPI_YoY_t = (index_t / index_{t−12} − 1) × 100
```

**YoY CPI from FRED ALFRED MoM% (compounded):**
```
CPI_YoY_t = (∏ᵢ₌₁¹² (1 + MoM_{t−i+1}/100)) − 1, expressed as %
```

**Real policy rate:**
```
real_policy_rate = repo_rate − CPI_YoY
```

**Overdue staleness:**
```
overdue_days = max(0, as_of_date − (observation_date + native_frequency_days + typical_lag_days))
```

**Confidence thresholds:**
```
sufficiency = min(1.0, point_count / sufficiency_threshold)
label = HIGH   if sufficiency ≥ 0.8 AND overdue_days ≤ lag_threshold
      = MEDIUM if sufficiency ≥ 0.5 AND overdue_days ≤ 2 × lag_threshold
      = LOW    otherwise
```

**Rolling percentile (excludes self):**
```
pct(series, window) = rolling(window).apply(λ x: (x[:-1] < x[-1]).mean() × 100)
```

**Tech posture:**
```
tech_posture = mean(rolling_pct(price/MA_252 − 1, 252), rolling_pct(price/price.shift(21) − 1, 252))
```

**Macro posture (per instrument):**
```
contribution_i = normalised_i          if direction_i = +1
               = 100 − normalised_i    if direction_i = −1
macro_posture  = mean(contribution_i for all sub-signals i)
```

**Divergence and flagging:**
```
divergence     = tech_posture − macro_posture
abs_divergence = |divergence|
percentile     = (trailing_abs_252 < abs_divergence).mean() × 100
flagged        = percentile ≥ 80.0
```

**Attribution z-scores:**
```
tech_z  = |tech_posture  − mean(tech_252)| / std(tech_252)
macro_z = |macro_posture − mean(macro_252)| / std(macro_252)
```

### Source registry

| Canonical name | Source | FRED series / ticker | Vintage class |
|---|---|---|---|
| `usd_zar` | Yahoo Finance | `USDZAR=X` | NOT_REVISED |
| `jse_alsi` | Yahoo Finance | `^J203.JO` | NOT_REVISED |
| `saf_equity_etf` | Yahoo Finance | `EZA` | NOT_REVISED |
| `cpi` | FRED ALFRED | `CPALTT01ZAM657N` | BACKFILLABLE |
| `repo_rate` | FRED ALFRED | `IRSTCB01ZAM156N` | BACKFILLABLE |
| `yield_10y` | FRED ALFRED | `IRLTLT01ZAM156N` | BACKFILLABLE |
| `gdp_growth` | World Bank | `NY.GDP.MKTP.KD.ZG` | REVISED_NO_VINTAGE |
| `cpi_samadb` | SAMADB | `CPS00000` (dataset: `CPI_ANL_SERIES`) | REVISED_NO_VINTAGE |
| `repo_mpc` | Manual MPC table | `src/sources/mpc_repo.py` | REVISED_NO_VINTAGE |

### Files

| File | Purpose |
|---|---|
| `src/vintage_store.py` | DuckDB PIT store — schema, queries, vintage class dispatch |
| `src/config.py` | Indicator registry — canonical names, sources, native frequency, lag |
| `src/resolver.py` | Live-edge router — `get_macro(concept, as_of_date, store)` |
| `src/signals/fundamentals.py` | Five fundamental sub-signals via resolver |
| `src/signals/technicals.py` | Three technical sub-signals from price series |
| `src/signals/normalise.py` | Confidence and percentile functions |
| `src/signals/api.py` | `SignalAPI` — unified entry point for both families |
| `src/divergence.py` | `DivergenceDetector` — posture, flagging, attribution |
| `src/sources/mpc_repo.py` | Manual SARB MPC decision table (requires human maintenance) |
| `tests/test_signals.py` | PIT leak test, confidence test, CPI derivation, live rewire test |
| `tests/test_divergence.py` | Nene shock, quiet period control, confidence propagation, PIT survival |

---

*Not financial advice. Past macro regime behaviour does not guarantee future market returns.*
