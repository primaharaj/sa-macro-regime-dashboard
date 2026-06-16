import pandas as pd
import numpy as np
from src.signals.normalise import SignalNormaliser, calculate_overdue_days
from src.config import INDICATOR_REGISTRY
from src.resolver import get_macro


class FundamentalSignals:
    def __init__(self, store, norm_window_years=10):
        self.store = store
        self.normaliser = SignalNormaliser(window=norm_window_years * 12, sufficiency_threshold=24)

    # ------------------------------------------------------------------
    # YoY derivation — two paths, chosen by resolver-declared unit
    # ------------------------------------------------------------------

    def _derive_inflation_yoy_mom(self, cpi_series):
        """MoM % → YoY: compound 12 monthly rates. Used for canonical FRED cpi."""
        if len(cpi_series) < 12:
            return pd.Series(dtype=float)
        decimal_mom = cpi_series / 100.0
        yoy = (1 + decimal_mom).rolling(12).apply(np.prod, raw=True) - 1
        return yoy * 100.0

    def _derive_inflation_yoy_index(self, index_series):
        """Index level → YoY: (index_t / index_{t-12} - 1) * 100. Used for cpi_samadb."""
        if len(index_series) < 13:
            return pd.Series(dtype=float)
        return (index_series / index_series.shift(12) - 1) * 100

    # ------------------------------------------------------------------
    # Main compute — routes CPI and repo through the resolver
    # ------------------------------------------------------------------

    def compute(self, as_of_date):
        # --- CPI: resolver picks live (cpi_samadb, index_level) or vintage (cpi, mom_pct) ---
        cpi_packet = get_macro("cpi", as_of_date, self.store)
        cpi_series_df = cpi_packet.get("series", pd.DataFrame())
        if cpi_series_df is None or cpi_series_df.empty:
            return None

        cpi_source = cpi_packet["source"]
        cpi_unit = cpi_packet["unit"]
        # Fail loudly on an unknown unit — do not silently apply the wrong formula.
        assert cpi_unit in ("index_level", "mom_pct"), (
            f"Unexpected CPI unit {cpi_unit!r} from source {cpi_source!r}"
        )

        df_cpi = cpi_series_df.set_index("date")["value"]

        if cpi_unit == "index_level":
            inf_yoy_hist = self._derive_inflation_yoy_index(df_cpi)
        else:
            inf_yoy_hist = self._derive_inflation_yoy_mom(df_cpi)

        if inf_yoy_hist.empty or pd.isna(inf_yoy_hist.iloc[-1]):
            return None

        current_inf = inf_yoy_hist.iloc[-1]

        # --- REPO: resolver returns live repo_mpc scalar or FRED legacy fallback ---
        repo_packet = get_macro("repo", as_of_date, self.store)
        if repo_packet.get("value") is None:
            return None
        current_repo = float(repo_packet["value"])

        # Historical repo series for percentile normalisation.
        # Always use FRED repo_rate — it carries the longest aligned history
        # (decades vs months for repo_mpc).  The current raw value already uses
        # the live scalar; normalisation just needs the historical range.
        df_repo_raw = self.store.get_series("repo_rate", as_of_date)
        if df_repo_raw.empty:
            return None
        df_repo = df_repo_raw.set_index("date")["value"]

        # --- YIELD: always FRED (current to ~Apr 2026) ---
        df_yield_raw = self.store.get_series("yield_10y", as_of_date)
        if df_yield_raw.empty:
            return None
        df_yield = df_yield_raw.set_index("date")["value"]
        current_yield = df_yield.iloc[-1]

        # --- GDP ---
        df_gdp = self.store.get_series("gdp_growth", as_of_date)
        growth_raw = df_gdp["value"].iloc[-1] if not df_gdp.empty else 0
        growth_as_of = df_gdp["date"].iloc[-1] if not df_gdp.empty else None

        # --- Current signal values ---
        real_policy_raw = current_repo - current_inf
        real_yield_raw = current_yield - current_inf
        slope_raw = current_yield - current_repo
        inf_trend_raw = inf_yoy_hist.diff(3).iloc[-1] if len(inf_yoy_hist) > 3 else 0

        # --- Staleness: anchored on the resolved CPI identity's config ---
        # For live path: cpi_samadb has native_freq=31, typical_lag=75.
        # For vintage path: cpi (FRED) has the same values, so the math is identical.
        cpi_config = INDICATOR_REGISTRY[cpi_source]
        underlying_obs_date = df_cpi.index[-1]
        overdue_days = calculate_overdue_days(
            underlying_obs_date,
            as_of_date,
            cpi_config["native_frequency_days"],
            cpi_config["typical_lag_days"],
        )

        # --- Normalisation histories (aligned by pandas index — NaN where series don't overlap) ---
        real_policy_hist = df_repo - inf_yoy_hist
        real_yield_hist = df_yield - inf_yoy_hist
        slope_hist = df_yield - df_repo
        inf_trend_hist = inf_yoy_hist.diff(3)

        overdue_threshold = 10
        policy_norm, policy_conf = self.normaliser.normalise(
            real_policy_raw, real_policy_hist.dropna(), overdue_days, overdue_threshold)
        yield_norm, yield_conf = self.normaliser.normalise(
            real_yield_raw, real_yield_hist.dropna(), overdue_days, overdue_threshold)
        slope_norm, slope_conf = self.normaliser.normalise(
            slope_raw, slope_hist.dropna(), overdue_days, overdue_threshold)
        inf_trend_norm, inf_trend_conf = self.normaliser.normalise(
            inf_trend_raw, inf_trend_hist.dropna(), overdue_days, overdue_threshold)

        # --- GDP normalisation ---
        gdp_config = INDICATOR_REGISTRY["gdp_growth"]
        gdp_overdue = calculate_overdue_days(
            growth_as_of,
            as_of_date,
            gdp_config["native_frequency_days"],
            gdp_config["typical_lag_days"],
        ) if growth_as_of else 999
        gdp_history = df_gdp["value"].dropna() if not df_gdp.empty else pd.Series(dtype=float)
        gdp_norm, gdp_conf = self.normaliser.normalise(growth_raw, gdp_history, gdp_overdue, 90)

        return {
            "real_policy_rate":  {"raw": real_policy_raw,  "normalised": policy_norm,    "confidence": policy_conf},
            "real_long_yield":   {"raw": real_yield_raw,   "normalised": yield_norm,     "confidence": yield_conf},
            "curve_slope":       {"raw": slope_raw,         "normalised": slope_norm,     "confidence": slope_conf},
            "inflation_trend":   {"raw": inf_trend_raw,    "normalised": inf_trend_norm, "confidence": inf_trend_conf},
            "growth_backdrop":   {"raw": growth_raw,        "normalised": gdp_norm,       "confidence": gdp_conf, "tag": "SLOW"},
            "underlying_as_of_date": underlying_obs_date,
            "cpi_source": cpi_source,
            "cpi_boundary": cpi_packet["boundary"],
            "repo_source": repo_packet["source"],
        }
