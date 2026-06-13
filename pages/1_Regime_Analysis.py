import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from src.data_loader import DataLoader
from src.regime_engine import RegimeEngine
from src.backtester import RegimeBacktester

st.set_page_config(page_title="Regime Analysis", layout="wide")

st.title("🔬 Macro Regime Analysis")

def load_data():
    loader = DataLoader()
    return loader.load_from_db()

df_raw = load_data()

if df_raw.empty:
    st.warning("No data found. Please update the database from the Main Page.")
else:
    # Required columns check
    required_cols = ["cpi", "yield_10y"]
    missing = [c for c in required_cols if c not in df_raw.columns]
    
    if missing:
        st.error(f"Missing required macro columns: {missing}")
        st.info("The dashboard requires CPI and 10Y Yield data to calculate regimes. Please ensure these are successfully fetched during the 'Update' process.")
    else:
        # Initialize Engine
        engine = RegimeEngine(df_raw)
        df_regimes = engine.calculate_regimes()
        
        # 1. Regime Timeline
        st.subheader("Historical Macro Regimes")
        
        # Define colors for regimes
        regime_colors = {
            "Disinflationary Growth (Goldilocks)": "#2ECC71",
            "Reflation (Recovery)": "#3498DB",
            "Stagflation (Crisis)": "#E74C3C",
            "Deflation (Slump)": "#F1C40F"
        }
        
        asset_to_plot = st.selectbox("Select Asset for Overlay", ["jse_alsi", "usd_zar", "saf_equity_etf"])
        
        fig = go.Figure()
        
        # Add Regime background
        for regime, color in regime_colors.items():
            mask = df_regimes["regime"] == regime
            if mask.any():
                # Create spans for consecutive regimes
                df_regimes["group"] = (df_regimes["regime"] != df_regimes["regime"].shift()).cumsum()
                for _, group_df in df_regimes[mask].groupby("group"):
                    fig.add_vrect(
                        x0=group_df["date"].iloc[0],
                        x1=group_df["date"].iloc[-1],
                        fillcolor=color,
                        opacity=0.3,
                        layer="below",
                        line_width=0,
                        name=regime
                    )

        # Add Asset Price
        fig.add_trace(go.Scatter(x=df_regimes["date"], y=df_regimes[asset_to_plot], name=asset_to_plot, line=dict(color="black")))
        
        fig.update_layout(title=f"{asset_to_plot} vs Macro Regimes", xaxis_title="Date", showlegend=True)
        st.plotly_chart(fig, use_container_width=True)

        # 2. Performance Stats
        st.divider()
        st.subheader("Regime Performance Matrix")
        
        stats_df = engine.get_regime_stats()
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("Average Annualized Returns by Regime")
            pivot_ret = stats_df.pivot(index="Regime", columns="Asset", values="Annualized Return (%)")
            fig_heat = px.imshow(pivot_ret, text_auto=".2f", color_continuous_scale="RdYlGn", aspect="auto")
            st.plotly_chart(fig_heat, use_container_width=True)
            
        with col2:
            st.write("Detailed Statistics")
            st.dataframe(stats_df, use_container_width=True)

        # 3. Backtesting
        st.divider()
        st.subheader("Interactive Backtester")
        
        bt_col1, bt_col2 = st.columns([1, 3])
        
        with bt_col1:
            st.info("Strategy: Hold asset ONLY during selected regimes. Otherwise, stay in Cash.")
            selected_asset = st.selectbox("Backtest Asset", ["jse_alsi", "saf_equity_etf"])
            active_regimes = st.multiselect(
                "Select 'ON' Regimes", 
                options=list(engine.REGIMES.values()),
                default=[list(engine.REGIMES.values())[0]]
            )
            
        if active_regimes:
            backtester = RegimeBacktester(df_regimes, asset_col=selected_asset)
            df_results = backtester.run_strategy(active_regimes)
            metrics = backtester.get_performance_metrics()
            
            with bt_col2:
                # Equity Curve
                fig_bt = go.Figure()
                fig_bt.add_trace(go.Scatter(x=df_results["date"], y=df_results["bh_equity"], name="Buy & Hold", line=dict(dash='dash')))
                fig_bt.add_trace(go.Scatter(x=df_results["date"], y=df_results["strat_equity"], name="Regime Strategy", line=dict(width=3)))
                fig_bt.update_layout(title="Strategy Equity Curve", yaxis_type="log")
                st.plotly_chart(fig_bt, use_container_width=True)
                
                # Metrics
                st.table(metrics)
