import pandas as pd
import numpy as np

class RegimeEngine:
    """
    South African Macro Regime Dashboard - Analytical Layer
    """
    
    REGIMES = {
        0: "Disinflationary Growth (Goldilocks)",
        1: "Reflation (Recovery)",
        2: "Stagflation (Crisis)",
        3: "Deflation (Slump)"
    }

    def __init__(self, df):
        self.df = df.sort_values("date").copy()
        
    def calculate_regimes(self, window=252):
        """
        Classifies regimes based on Inflation (CPI) and Growth Proxies (Yields).
        Logic: 
        - Growth Proxy: Yield 10Y rolling z-score (proxy for expectations)
        - Inflation Proxy: CPI rolling z-score
        """
        # Calculate Rolling Z-Scores
        self.df["cpi_trend"] = (self.df["cpi"] - self.df["cpi"].rolling(window).mean()) / self.df["cpi"].rolling(window).std()
        self.df["growth_trend"] = (self.df["yield_10y"] - self.df["yield_10y"].rolling(window).mean()) / self.df["yield_10y"].rolling(window).std()
        
        # Define Binary Signals (Above/Below Trend)
        self.df["inf_high"] = self.df["cpi_trend"] > 0
        self.df["growth_high"] = self.df["growth_trend"] > 0
        
        # Assign Regimes
        # 0: Low Inf, High Growth
        # 1: High Inf, High Growth
        # 2: High Inf, Low Growth
        # 3: Low Inf, Low Growth
        def classify(row):
            if not row["inf_high"] and row["growth_high"]: return 0
            if row["inf_high"] and row["growth_high"]: return 1
            if row["inf_high"] and not row["growth_high"]: return 2
            if not row["inf_high"] and not row["growth_high"]: return 3
            return np.nan

        self.df["regime_id"] = self.df.apply(classify, axis=1)
        self.df["regime"] = self.df["regime_id"].map(self.REGIMES)
        
        return self.df

    def get_regime_stats(self, asset_cols=["jse_alsi", "usd_zar"]):
        """
        Calculate performance stats for specific assets per regime
        """
        if "regime" not in self.df.columns:
            self.calculate_regimes()
            
        stats = []
        
        # Calculate daily returns
        for asset in asset_cols:
            if asset in self.df.columns:
                ret_col = f"{asset}_ret"
                self.df[ret_col] = self.df[asset].pct_change()
                
                # Group by regime
                regime_groups = self.df.groupby("regime")[ret_col]
                
                for regime, data in regime_groups:
                    stats.append({
                        "Asset": asset,
                        "Regime": regime,
                        "Avg Daily Return (%)": data.mean() * 100,
                        "Annualized Return (%)": data.mean() * 252 * 100,
                        "Annualized Vol (%)": data.std() * np.sqrt(252) * 100,
                        "Win Rate (%)": (data > 0).mean() * 100,
                        "Samples": len(data)
                    })
                    
        return pd.DataFrame(stats)
