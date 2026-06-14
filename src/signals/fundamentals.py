import pandas as pd
import numpy as np
from src.signals.normalise import SignalNormaliser, calculate_overdue_days
from src.config import INDICATOR_REGISTRY

class FundamentalSignals:
    def __init__(self, store, norm_window_years=10):
        self.store = store
        self.normaliser = SignalNormaliser(window=norm_window_years * 12, sufficiency_threshold=24)

    def _derive_inflation_yoy(self, cpi_series):
        """
        Derives YoY inflation from the CPI MoM rate series.
        CPI is confirmed as a monthly growth rate (%).
        """
        if len(cpi_series) < 12:
            return pd.Series(dtype=float)
        
        # Convert % to decimal: 1.0 -> 0.01
        decimal_mom = cpi_series / 100.0
        
        # Compound: (1+r1)(1+r2)...(1+r12) - 1
        yoy = (1 + decimal_mom).rolling(12).apply(np.prod, raw=True) - 1
        return yoy * 100.0

    def compute(self, as_of_date):
        # 1. Fetch data through PIT API
        df_cpi = self.store.get_series("cpi", as_of_date)
        df_repo = self.store.get_series("repo_rate", as_of_date)
        df_yield = self.store.get_series("yield_10y", as_of_date)
        df_gdp = self.store.get_series("gdp_growth", as_of_date)

        if df_cpi.empty or df_repo.empty or df_yield.empty:
            return None

        # Align series by date
        df_cpi = df_cpi.set_index('date')['value']
        df_repo = df_repo.set_index('date')['value']
        df_yield = df_yield.set_index('date')['value']
        
        # Calculate Inflation YoY
        inf_yoy_hist = self._derive_inflation_yoy(df_cpi)
        if inf_yoy_hist.empty or pd.isna(inf_yoy_hist.iloc[-1]):
            return None
            
        current_inf = inf_yoy_hist.iloc[-1]
        current_repo = df_repo.iloc[-1]
        current_yield = df_yield.iloc[-1]
        
        # Derived Signals
        real_policy_raw = current_repo - current_inf
        real_yield_raw = current_yield - current_inf
        slope_raw = current_yield - current_repo
        
        # Inflation Trend (Change in YoY over last 3 months)
        inf_trend_raw = inf_yoy_hist.diff(3).iloc[-1] if len(inf_yoy_hist) > 3 else 0
        
        # Growth Backdrop (Annual GDP)
        growth_raw = df_gdp['value'].iloc[-1] if not df_gdp.empty else 0
        growth_as_of = df_gdp['date'].iloc[-1] if not df_gdp.empty else None
        
        # Staleness: measure time past expected next release
        # Use CPI as anchor for core monthly macro
        cpi_config = INDICATOR_REGISTRY["cpi"]
        underlying_obs_date = df_cpi.index[-1]
        overdue_days = calculate_overdue_days(
            underlying_obs_date, 
            as_of_date, 
            cpi_config["native_frequency_days"], 
            cpi_config["typical_lag_days"]
        )
        
        # Normalise
        # Note: We compute history of features for normalisation
        real_policy_hist = df_repo - inf_yoy_hist
        real_yield_hist = df_yield - inf_yoy_hist
        slope_hist = df_yield - df_repo
        inf_trend_hist = inf_yoy_hist.diff(3)
        
        # Grace period for overdue: 10 days before MEDIUM, 30 days before LOW
        overdue_threshold = 10
        policy_norm, policy_conf = self.normaliser.normalise(real_policy_raw, real_policy_hist.dropna(), overdue_days, overdue_threshold)
        yield_norm, yield_conf = self.normaliser.normalise(real_yield_raw, real_yield_hist.dropna(), overdue_days, overdue_threshold)
        slope_norm, slope_conf = self.normaliser.normalise(slope_raw, slope_hist.dropna(), overdue_days, overdue_threshold)
        inf_trend_norm, inf_trend_conf = self.normaliser.normalise(inf_trend_raw, inf_trend_hist.dropna(), overdue_days, overdue_threshold)
        
        # GDP Normalisation (Stale by definition)
        gdp_config = INDICATOR_REGISTRY["gdp_growth"]
        gdp_overdue = calculate_overdue_days(
            growth_as_of, 
            as_of_date, 
            gdp_config["native_frequency_days"], 
            gdp_config["typical_lag_days"]
        ) if growth_as_of else 999
        
        gdp_history = df_gdp['value'].dropna() if not df_gdp.empty else pd.Series(dtype=float)
        # Annual grace: 90 days before MEDIUM
        gdp_norm, gdp_conf = self.normaliser.normalise(growth_raw, gdp_history, gdp_overdue, 90)

        return {
            "real_policy_rate": {"raw": real_policy_raw, "normalised": policy_norm, "confidence": policy_conf},
            "real_long_yield": {"raw": real_yield_raw, "normalised": yield_norm, "confidence": yield_conf},
            "curve_slope": {"raw": slope_raw, "normalised": slope_norm, "confidence": slope_conf},
            "inflation_trend": {"raw": inf_trend_raw, "normalised": inf_trend_norm, "confidence": inf_trend_conf},
            "growth_backdrop": {"raw": growth_raw, "normalised": gdp_norm, "confidence": gdp_conf, "tag": "SLOW"},
            "underlying_as_of_date": underlying_obs_date
        }
