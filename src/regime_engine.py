import pandas as pd
import numpy as np

class RegimeEngine:
    """
    South African Macro Intelligence Engine - Analytical Layer
    """
    
    REGIMES = {
        0: "Disinflationary Growth (Goldilocks)",
        1: "Reflation (Recovery)",
        2: "Stagflation (Crisis)",
        3: "Deflation (Slump)"
    }

    POLICY_STATES = {
        1: "Tightening (Hikes)",
        -1: "Easing (Cuts)",
        0: "Neutral / Hold"
    }

    def __init__(self, df):
        self.df = df.sort_values("date").copy()
        
    def calculate_regimes(self, window=252):
        """
        Classifies macro regimes and calculates intelligence signals.
        """
        # 1. Standard Macro Regimes (Inflation vs Growth Proxy)
        self.df["cpi_trend"] = (self.df["cpi"] - self.df["cpi"].rolling(window).mean()) / self.df["cpi"].rolling(window).std()
        self.df["growth_trend"] = (self.df["yield_10y"] - self.df["yield_10y"].rolling(window).mean()) / self.df["yield_10y"].rolling(window).std()
        
        self.df["inf_high"] = self.df["cpi_trend"] > 0
        self.df["growth_high"] = self.df["growth_trend"] > 0
        
        def classify(row):
            if not row["inf_high"] and row["growth_high"]: return 0
            if row["inf_high"] and row["growth_high"]: return 1
            if row["inf_high"] and not row["growth_high"]: return 2
            if not row["inf_high"] and not row["growth_high"]: return 3
            return np.nan

        self.df["regime_id"] = self.df.apply(classify, axis=1)
        self.df["regime"] = self.df["regime_id"].map(self.REGIMES)

        # 2. Global Risk Sentiment (Risk-On / Risk-Off)
        if "sp500" in self.df.columns:
            # Risk-On if S&P 500 is above its 200-day moving average
            self.df["sp500_ma"] = self.df["sp500"].rolling(window).mean()
            self.df["global_sentiment"] = np.where(self.df["sp500"] > self.df["sp500_ma"], "Risk-On", "Risk-Off")

        # 3. Policy Cycle Detector (SARB Actions)
        if "repo_rate" in self.df.columns:
            # Define policy cycle based on 3-month repo rate change
            repo_diff = self.df["repo_rate"].diff(63) # ~3 months
            self.df["policy_state_id"] = np.where(repo_diff > 0.05, 1, np.where(repo_diff < -0.05, -1, 0))
            self.df["policy_cycle"] = self.df["policy_state_id"].map(self.POLICY_STATES)

        # 4. Capital Flow Heuristics (Estimate Directional Flows)
        # Logic: Risk-On + SA Yield Slope > 0 + ZAR Strengthening -> Strong Inflows
        if all(c in self.df.columns for c in ["global_sentiment", "sa_yield_slope", "usd_zar"]):
            self.df["zar_mom"] = self.df["usd_zar"].pct_change(21) # 1 month ZAR momentum
            
            def estimate_flow(row):
                if row["global_sentiment"] == "Risk-On" and row["zar_mom"] < -0.01:
                    return "Capital Inflow (High Sentiment)"
                if row["global_sentiment"] == "Risk-Off" and row["zar_mom"] > 0.01:
                    return "Capital Outflow (Flight to Safety)"
                if row["policy_state_id"] == 1 and row["sa_yield_slope"] < 0:
                    return "Yield Seeking (Carry Trade)"
                return "Neutral / Mixed Flows"
            
            self.df["estimated_flows"] = self.df.apply(estimate_flow, axis=1)
        
        return self.df

    def get_intelligence_snapshot(self):
        """
        Returns a dictionary summarizing the latest macro intelligence.
        """
        latest = self.df.iloc[-1]
        
        return {
            "regime": latest.get("regime", "Unknown"),
            "sentiment": latest.get("global_sentiment", "Unknown"),
            "policy": latest.get("policy_cycle", "Unknown"),
            "flows": latest.get("estimated_flows", "Unknown"),
            "zar_vol": self.df["usd_zar"].pct_change().std() * np.sqrt(252) * 100,
            "equity_relative_strength": latest.get("jse_relative_strength", 0)
        }

    def get_regime_stats(self, asset_cols=["jse_alsi", "usd_zar"]):
        """
        Calculate performance stats for specific assets per regime
        """
        if "regime" not in self.df.columns:
            self.calculate_regimes()
            
        stats = []
        for asset in asset_cols:
            if asset in self.df.columns:
                ret_col = f"{asset}_ret"
                self.df[ret_col] = self.df[asset].pct_change()
                regime_groups = self.df.groupby("regime")[ret_col]
                
                for regime, data in regime_groups:
                    stats.append({
                        "Asset": asset,
                        "Regime": regime,
                        "Annualized Return (%)": data.mean() * 252 * 100,
                        "Annualized Vol (%)": data.std() * np.sqrt(252) * 100,
                        "Win Rate (%)": (data > 0).mean() * 100,
                        "Sharpe Ratio": (data.mean() * 252 - 0.05) / (data.std() * np.sqrt(252)) if data.std() > 0 else 0
                    })
                    
        return pd.DataFrame(stats)
