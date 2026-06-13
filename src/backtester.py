import pandas as pd
import numpy as np

class RegimeBacktester:
    """
    Backtesting engine for Regime-based strategies
    """
    
    def __init__(self, df, asset_col="jse_alsi"):
        self.df = df.copy()
        self.asset_col = asset_col
        
    def run_strategy(self, active_regimes, initial_capital=100000):
        """
        Simulate a strategy that holds the asset only during 'active_regimes'
        """
        if "regime" not in self.df.columns:
            raise ValueError("Regime column missing from dataframe")
            
        # Calculate asset returns
        self.df["asset_ret"] = self.df[self.asset_col].pct_change()
        
        # Strategy Logic: If regime in active_regimes, signal = 1, else 0
        self.df["signal"] = self.df["regime"].isin(active_regimes).astype(int)
        
        # Shift signal by 1 day to avoid look-ahead bias
        self.df["signal"] = self.df["signal"].shift(1)
        
        # Calculate strategy returns
        self.df["strat_ret"] = self.df["asset_ret"] * self.df["signal"]
        
        # Calculate equity curves
        self.df["bh_equity"] = initial_capital * (1 + self.df["asset_ret"]).cumprod()
        self.df["strat_equity"] = initial_capital * (1 + self.df["strat_ret"]).cumprod()
        
        # Fill NaNs from first row
        self.df["bh_equity"] = self.df["bh_equity"].ffill().fillna(initial_capital)
        self.df["strat_equity"] = self.df["strat_equity"].ffill().fillna(initial_capital)
        
        return self.df
        
    def get_performance_metrics(self):
        """
        Calculate key risk/return metrics
        """
        metrics = {}
        
        # Explicit mapping of return column to its corresponding equity column
        config = [
            ("Buy & Hold", "asset_ret", "bh_equity"),
            ("Regime Strategy", "strat_ret", "strat_equity")
        ]
        
        for name, ret_col, equity_col in config:
            returns = self.df[ret_col].dropna()
            
            if len(returns) == 0:
                continue
                
            cagr = (self.df[equity_col].iloc[-1] / self.df[equity_col].iloc[0]) ** (252/len(returns)) - 1
            vol = returns.std() * np.sqrt(252)
            sharpe = (cagr - 0.05) / vol if vol != 0 else 0 # Assuming 5% risk-free rate for SA
            
            # Drawdown
            equity = self.df[equity_col]
            drawdown = (equity / equity.cummax()) - 1
            max_dd = drawdown.min()
            
            metrics[name] = {
                "CAGR (%)": cagr * 100,
                "Vol (%)": vol * 100,
                "Sharpe": sharpe,
                "Max DD (%)": max_dd * 100
            }
            
        return pd.DataFrame(metrics).T
