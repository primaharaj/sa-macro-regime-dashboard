"""
Divergence Detector — flags where an SA instrument's technical posture
diverges from what the SA macro backdrop justifies.

Design contract
───────────────
tech_posture   : mean of rolling percentile-ranked trend (price/MA_252 − 1)
                 and momentum (price/price.shift(21) − 1) on [0, 100].
                 Volatility informs confidence/context, NOT directional posture.
macro_posture  : signed mean of normalised macro sub-signals on [0, 100],
                 oriented per-instrument so that HIGH = macro is supportive
                 for that instrument's price level.
divergence     : tech_posture − macro_posture (signed).
abs_divergence : |divergence|.
flagging       : |divergence| > 80th percentile of trailing 756-day
                 |divergence| distribution (self-calibrated, no hardcoded constant).
confidence     : min(tech_confidence, macro_confidence).
                 A flag built on a LOW-confidence input is LOW-confidence
                 and non-actionable, regardless of gap magnitude.
PIT property   : all data read through VintageStore PIT path;
                 divergence inherits the no-look-ahead guarantee.

Per-instrument macro orientation
──────────────────────────────────
jse_alsi:
  HIGH posture = SA macro is supportive for equity prices.
  growth_backdrop(+): high growth → equity-supportive.
  real_policy_rate(−): low real rate → easy credit + low discount rate → bullish.
  inflation_trend(−): falling inflation → less CB tightening pressure → bullish.

usd_zar (CRITICAL — read before modifying):
  HIGH posture = macro justifies ZAR WEAKNESS (high USDZAR).
  Per spec: "HAWKISH/high-real-rate backdrop is ZAR-SUPPORTIVE → argues
  for LOWER USDZAR → LOW macro_posture for USDZAR."
  growth_backdrop(−): low SA growth → ZAR weak → high USDZAR supported.
  real_policy_rate(−): low real rate → less hawkish → ZAR weak (spec-mandated).
  inflation_trend(+): rising inflation → ZAR erodes → high USDZAR supported.

saf_equity_etf (secondary):
  Same orientation as jse_alsi. USD denomination muddies the SA-macro
  comparison (USD/ZAR effects are not captured in the SA macro_posture).
"""

import numpy as np
import pandas as pd
from src.signals.normalise import get_confidence, calculate_overdue_days

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LABEL_RANK = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}

_TRAILING_WINDOW = 252   # 1 year of trading days — calibrates to the current volatility
                          # regime, not the 3-year trend that preceded every shock
_FLAG_PERCENTILE = 80.0  # flag if |divergence| > 80th percentile of trailing window

_INSTRUMENT_CONFIG = {
    "jse_alsi": {
        "macro_components": [
            ("growth_backdrop",  +1),
            ("real_policy_rate", -1),
            ("inflation_trend",  -1),
        ],
    },
    "usd_zar": {
        "macro_components": [
            ("growth_backdrop",  -1),
            ("real_policy_rate", -1),
            ("inflation_trend",  +1),
        ],
    },
    "saf_equity_etf": {
        "macro_components": [
            ("growth_backdrop",  +1),
            ("real_policy_rate", -1),
            ("inflation_trend",  -1),
        ],
    },
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _rolling_pct(series, window):
    """
    Rolling percentile rank of the most recent value within the trailing window.
    Returns a Series on [0, 100]. Consistent with normalise.calculate_percentile
    (excludes self from comparison: x[:-1] < x[-1]).
    """
    return series.rolling(window).apply(
        lambda x: (x[:-1] < x[-1]).mean() * 100.0,
        raw=True,
    )


def _label_min(*labels):
    return min(labels, key=lambda lbl: _LABEL_RANK.get(lbl, 0))


def _macro_posture_series(components, as_of_date, store):
    """
    Build a monthly macro_posture series from FRED/WB data in the store.
    Used to calibrate the divergence percentile distribution.
    All data read through VintageStore PIT path (store.get_series).
    """
    sub_names = {name for name, _ in components}
    directions = {name: d for name, d in components}

    def _load(name):
        df = store.get_series(name, as_of_date)
        if df.empty:
            return pd.Series(dtype=float)
        s = df.set_index("date")["value"].sort_index()
        s.index = pd.to_datetime(s.index)
        return s

    cpi_mom = _load("cpi")
    repo    = _load("repo_rate")

    if cpi_mom.empty or repo.empty:
        return pd.Series(dtype=float)

    # CPI MoM% → compound YoY%
    decimal_mom = cpi_mom / 100.0
    cpi_yoy = ((1 + decimal_mom).rolling(12).apply(np.prod, raw=True) - 1) * 100.0

    derived = {}
    if "real_policy_rate" in sub_names:
        derived["real_policy_rate"] = (repo - cpi_yoy).dropna()
    if "inflation_trend" in sub_names:
        derived["inflation_trend"] = cpi_yoy.diff(3).dropna()
    if "growth_backdrop" in sub_names:
        gdp_raw = _load("gdp_growth")
        if not gdp_raw.empty:
            # Annual → resample to month-end + forward-fill
            derived["growth_backdrop"] = gdp_raw.resample("ME").last().ffill()

    used = [name for name, _ in components if name in derived]
    if not used:
        return pd.Series(dtype=float)

    monthly = pd.concat([derived[n].rename(n) for n in used], axis=1, sort=True)
    # Require core series (non-GDP) to be present
    core = [n for n in used if n != "growth_backdrop"]
    monthly = monthly.dropna(subset=core)

    # Rolling percentile rank per sub-signal (120 months = 10-year window,
    # consistent with FundamentalSignals norm_window_years=10)
    norm_window = 120
    parts = []
    for name in used:
        s = monthly[name].dropna()
        if len(s) < norm_window:
            continue
        pct = _rolling_pct(s, norm_window)
        parts.append(pct if directions[name] == +1 else (100.0 - pct))

    if not parts:
        return pd.Series(dtype=float)

    combined = pd.concat(parts, axis=1).dropna()
    posture = combined.mean(axis=1)
    posture.name = "macro_posture"
    return posture


def _current_macro_posture(macro_sigs, components):
    """
    Extract current macro_posture (0–100) and min confidence from a macro signal packet.
    macro_sigs: the "signals" dict from SignalAPI.get_signal("fundamentals", "SA", T).

    Sub-signals with staleness_days >= 500 are treated as "not yet captured" placeholders
    (e.g., gdp_growth at historical dates before its first_capture_date).  Their normalised
    value is included in the posture (neutral 50.0) but their LOW confidence label is NOT
    included in the min-confidence calculation — it would unfairly drag historical dates to
    LOW solely because the DB hadn't been seeded yet.
    """
    values, conf_labels = [], []
    for sub_name, direction in components:
        sig = macro_sigs.get(sub_name)
        if sig is None:
            continue
        norm = sig.get("normalised")
        if norm is None or (isinstance(norm, float) and np.isnan(norm)):
            continue
        values.append(float(norm) if direction == +1 else 100.0 - float(norm))
        conf = sig.get("confidence", {})
        # Exclude confidence from "not yet captured" placeholders (staleness >= 500 days
        # indicates the data was never retrieved for this as_of_date, not that it's stale).
        if conf.get("staleness_days", 0) < 500:
            conf_labels.append(conf.get("confidence_label", "LOW"))

    if not values:
        return None, "LOW"
    if not conf_labels:
        return sum(values) / len(values), "LOW"
    return sum(values) / len(values), _label_min(*conf_labels)


def _current_tech_conf(prices, as_of_date):
    """Confidence label for the technical signal based on price data staleness."""
    if prices.empty:
        return "LOW"
    underlying_obs_date = prices.index[-1]
    overdue_days = calculate_overdue_days(
        underlying_obs_date, as_of_date,
        native_frequency_days=1,
        typical_lag_days=1,
    )
    conf = get_confidence(len(prices), sufficiency_threshold=24,
                          staleness_days=overdue_days, lag_threshold=2)
    return conf["confidence_label"]


# ---------------------------------------------------------------------------
# DivergenceDetector
# ---------------------------------------------------------------------------

class DivergenceDetector:
    """
    Detects divergence between an instrument's technical posture and the SA
    macro backdrop.

    Primary divergence targets: jse_alsi, usd_zar.
    Secondary (USD-muddied): saf_equity_etf.
    sp500, us_10y: correlates only — NOT divergence targets.
    """

    def __init__(self, api):
        """api: SignalAPI instance."""
        self.api = api
        self.store = api.store

    def compute(self, instrument, as_of_date):
        """
        Compute the divergence packet for `instrument` at `as_of_date`.

        Returns a dict with keys:
          instrument, date, tech_posture, macro_posture, divergence,
          abs_divergence, percentile, flagged, outlier_family,
          confidence, actionable, tech_confidence, macro_confidence,
          tech_source, macro_source, macro_boundary.
        Returns None if insufficient data.
        """
        config = _INSTRUMENT_CONFIG.get(instrument)
        if config is None:
            raise ValueError(
                f"Unknown instrument: {instrument!r}. Valid: {list(_INSTRUMENT_CONFIG)}"
            )
        components = config["macro_components"]

        # ── 1. Price series (PIT) ─────────────────────────────────────────
        price_df = self.store.get_series(instrument, as_of_date)
        if price_df.empty or len(price_df) < 30:
            return None
        prices = price_df.set_index("date")["value"].sort_index()
        prices.index = pd.to_datetime(prices.index)

        # ── 2. Tech posture series (vectorized) ──────────────────────────
        ma        = prices.rolling(252).mean()
        trend_raw = (prices / ma) - 1.0
        mom_raw   = (prices / prices.shift(21)) - 1.0

        trend_pct  = _rolling_pct(trend_raw, 252)
        mom_pct    = _rolling_pct(mom_raw, 252)
        tech_series = ((trend_pct + mom_pct) / 2.0).dropna()

        if tech_series.empty:
            return None
        current_tech_posture = float(tech_series.iloc[-1])

        # ── 3. Current macro posture from live path (SignalAPI) ──────────
        macro_sig = self.api.get_signal("fundamentals", "SA", as_of_date)
        if macro_sig is None:
            return None
        macro_sigs = macro_sig["signals"]
        current_macro_posture, macro_conf = _current_macro_posture(macro_sigs, components)
        if current_macro_posture is None:
            return None

        # ── 4. Historical macro posture series (for distribution) ─────────
        macro_hist = _macro_posture_series(components, as_of_date, self.store)

        # ── 5. Divergence series (daily, macro forward-filled) ────────────
        if not macro_hist.empty:
            combined_idx  = tech_series.index.union(macro_hist.index)
            tech_aligned  = tech_series.reindex(combined_idx).ffill()
            macro_aligned = macro_hist.reindex(combined_idx).ffill()
            div_series    = (tech_aligned - macro_aligned).dropna()
        else:
            div_series = pd.Series(dtype=float)

        current_divergence = current_tech_posture - current_macro_posture
        abs_current = abs(current_divergence)

        # ── 6. Percentile vs trailing window ─────────────────────────────
        if not div_series.empty:
            trailing_abs = div_series.abs().iloc[-_TRAILING_WINDOW:]
            percentile = float((trailing_abs < abs_current).mean() * 100.0)
        else:
            percentile = 50.0
        flagged = percentile >= _FLAG_PERCENTILE

        # ── 7. Attribution: which family is the outlier ───────────────────
        tech_trailing = tech_series.iloc[-_TRAILING_WINDOW:]
        tech_mean = float(tech_trailing.mean())
        tech_std  = max(float(tech_trailing.std()), 1e-6)
        tech_z    = abs(current_tech_posture - tech_mean) / tech_std

        if not macro_hist.empty:
            m_trail    = macro_hist.iloc[-_TRAILING_WINDOW:]
            macro_mean = float(m_trail.mean())
            macro_std  = max(float(m_trail.std()), 1e-6)
        else:
            macro_mean, macro_std = 50.0, 1e-6
        macro_z = abs(current_macro_posture - macro_mean) / macro_std

        if tech_z > macro_z * 1.5:
            outlier_family = "technicals"
        elif macro_z > tech_z * 1.5:
            outlier_family = "macro"
        elif tech_z > 1.5 and macro_z > 1.5:
            outlier_family = "both"
        else:
            outlier_family = "aligned"

        # ── 8. Confidence = min(tech, macro) ──────────────────────────────
        tech_conf    = _current_tech_conf(prices, as_of_date)
        overall_conf = _label_min(tech_conf, macro_conf)
        actionable   = (overall_conf in ("HIGH", "MEDIUM")) and flagged

        return {
            "instrument":       instrument,
            "date":             as_of_date,
            "tech_posture":     current_tech_posture,
            "macro_posture":    current_macro_posture,
            "divergence":       current_divergence,
            "abs_divergence":   abs_current,
            "percentile":       percentile,
            "flagged":          flagged,
            "outlier_family":   outlier_family,
            "confidence":       overall_conf,
            "actionable":       actionable,
            "tech_confidence":  tech_conf,
            "macro_confidence": macro_conf,
            "tech_source":      instrument,
            "macro_source":     macro_sigs.get("cpi_source", "unknown"),
            "macro_boundary":   macro_sigs.get("cpi_boundary", "unknown"),
        }

    def compute_series(self, instrument, start_date, end_date):
        """
        Compute divergence time series for a date range, using `end_date`
        as the as_of_date (most recent DB state).

        Returns a DataFrame indexed by date with columns:
          tech_posture, macro_posture, divergence, abs_divergence,
          flagged, rolling_80th_pct_threshold.
        Efficient: fully vectorized, no per-date signal API calls.
        """
        config = _INSTRUMENT_CONFIG.get(instrument)
        if config is None:
            return pd.DataFrame()
        components = config["macro_components"]

        price_df = self.store.get_series(instrument, end_date)
        if price_df.empty:
            return pd.DataFrame()
        prices = price_df.set_index("date")["value"].sort_index()
        prices.index = pd.to_datetime(prices.index)

        # Tech posture
        ma        = prices.rolling(252).mean()
        trend_raw = (prices / ma) - 1.0
        mom_raw   = (prices / prices.shift(21)) - 1.0
        trend_pct = _rolling_pct(trend_raw, 252)
        mom_pct   = _rolling_pct(mom_raw, 252)
        tech_series = (trend_pct + mom_pct) / 2.0

        # Historical macro posture
        macro_hist = _macro_posture_series(components, end_date, self.store)
        if macro_hist.empty:
            return pd.DataFrame()

        # Align at daily frequency (macro forward-filled)
        combined_idx  = tech_series.index.union(macro_hist.index)
        tech_aligned  = tech_series.reindex(combined_idx).ffill()
        macro_aligned = macro_hist.reindex(combined_idx).ffill()
        div_series    = (tech_aligned - macro_aligned)

        abs_div = div_series.abs()
        # Rolling 80th percentile threshold (uses pandas fast quantile path)
        rolling_threshold = abs_div.rolling(_TRAILING_WINDOW, min_periods=20).quantile(0.80)
        flagged_series    = abs_div > rolling_threshold

        result = pd.DataFrame({
            "tech_posture":            tech_aligned,
            "macro_posture":           macro_aligned,
            "divergence":              div_series,
            "abs_divergence":          abs_div,
            "flagged":                 flagged_series,
            "rolling_80th_pct_thresh": rolling_threshold,
        }).dropna(subset=["tech_posture", "macro_posture"])

        start_dt = pd.Timestamp(start_date)
        end_dt   = pd.Timestamp(end_date)
        return result.loc[start_dt:end_dt]
