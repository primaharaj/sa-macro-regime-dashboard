import pandas as pd
import numpy as np
from src.signals.normalise import SignalNormaliser, calculate_overdue_days
from src.config import INDICATOR_REGISTRY

class TechnicalSignals:
    def __init__(self, store, window_ma=252, window_roc=21, window_vol=63, norm_window=252):
        self.store = store
        self.window_ma = window_ma
        self.window_roc = window_roc
        self.window_vol = window_vol
        self.normaliser = SignalNormaliser(window=norm_window)

    def compute(self, name, as_of_date):
        # Determine the maximum history needed
        max_lookback = max(self.window_ma, self.window_roc, self.window_vol) + self.normaliser.window
        
        # Read series from PIT store
        df = self.store.get_series(name, as_of_date)
        if df.empty or len(df) < 5:
            return None

        df = df.set_index('date')
        prices = df['value']
        current_price = prices.iloc[-1]
        underlying_obs_date = prices.index[-1]
        
        # Staleness: measure time past expected next release
        config = INDICATOR_REGISTRY.get(name)
        overdue_days = calculate_overdue_days(
            underlying_obs_date,
            as_of_date,
            config["native_frequency_days"] if config else 1,
            config["typical_lag_days"] if config else 1
        )

        # Trend: price vs trailing MA
        ma = prices.rolling(self.window_ma).mean()
        trend_raw = (current_price / ma.iloc[-1]) - 1 if not pd.isna(ma.iloc[-1]) else 0
        
        # Momentum: trailing rate-of-change
        roc_raw = (current_price / prices.shift(self.window_roc).iloc[-1]) - 1 if len(prices) > self.window_roc else 0
        
        # Realized Vol: rolling std of log returns
        log_rets = np.log(prices / prices.shift(1))
        vol_raw = log_rets.rolling(self.window_vol).std() * np.sqrt(252)
        current_vol = vol_raw.iloc[-1] if not pd.isna(vol_raw.iloc[-1]) else 0

        # Normalise
        # Grace period for overdue: 2 days for market data
        overdue_threshold = 2
        
        # Trend History for Normalisation
        trend_hist = (prices / prices.rolling(self.window_ma).mean()) - 1
        trend_norm, trend_conf = self.normaliser.normalise(trend_raw, trend_hist.dropna(), overdue_days, overdue_threshold)
        
        # Momentum History
        roc_hist = (prices / prices.shift(self.window_roc)) - 1
        roc_norm, roc_conf = self.normaliser.normalise(roc_raw, roc_hist.dropna(), overdue_days, overdue_threshold)
        
        # Vol History
        vol_norm, vol_conf = self.normaliser.normalise(current_vol, vol_raw.dropna(), overdue_days, overdue_threshold)

        return {
            "trend": {"raw": trend_raw, "normalised": trend_norm, "confidence": trend_conf},
            "momentum": {"raw": roc_raw, "normalised": roc_norm, "confidence": roc_conf},
            "volatility": {"raw": current_vol, "normalised": vol_norm, "confidence": vol_conf},
            "underlying_as_of_date": underlying_obs_date
        }
