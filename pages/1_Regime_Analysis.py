import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from src.data_loader import DataLoader
from src.regime_engine import RegimeEngine
from src.backtester import RegimeBacktester

st.set_page_config(page_title="Regime Analysis", layout="wide")

st.title("🇿🇦 SA Macro Intelligence Engine")

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
        st.info("The dashboard requires CPI and 10Y Yield data to calculate regimes.")
    else:
        # 1. Intelligence Snapshot
        engine = RegimeEngine(df_raw)
        df_regimes = engine.calculate_regimes()
        snapshot = engine.get_intelligence_snapshot()
        
        st.subheader("Current Macro Intelligence Snapshot")
        m1, m2, m3, m4 = st.columns(4)
        
        m1.metric("Macro Regime", snapshot['regime'])
        m2.metric("Global Sentiment", snapshot['sentiment'], delta="Risk-On" if snapshot['sentiment'] == "Risk-On" else "Risk-Off")
        m3.metric("Policy Cycle", snapshot['policy'])
        m4.metric("Capital Flows", snapshot['flows'])
        
        st.divider()
        
        # 2. Historical Intelligence Timeline
        st.subheader("Historical Intelligence Timeline")
        
        timeline_mode = st.radio("Overlay Background Mode", ["Economic Regime", "Global Sentiment", "Policy Cycle"], horizontal=True)
        asset_to_plot = st.selectbox("Select Asset for Overlay", ["jse_alsi", "usd_zar", "jse_relative_strength"])
        
        fig = go.Figure()
        
        # Background mapping
        bg_mapping = {
            "Economic Regime": {
                "col": "regime",
                "colors": {
                    "Disinflationary Growth (Goldilocks)": "#2ECC71",
                    "Reflation (Recovery)": "#3498DB",
                    "Stagflation (Crisis)": "#E74C3C",
                    "Deflation (Slump)": "#F1C40F"
                }
            },
            "Global Sentiment": {
                "col": "global_sentiment",
                "colors": {
                    "Risk-On": "#27AE60",
                    "Risk-Off": "#C0392B"
                }
            },
            "Policy Cycle": {
                "col": "policy_cycle",
                "colors": {
                    "Tightening (Hikes)": "#E67E22",
                    "Easing (Cuts)": "#9B59B6",
                    "Neutral / Hold": "#95A5A6"
                }
            }
        }
        
        mode_cfg = bg_mapping[timeline_mode]
        col = mode_cfg["col"]
        colors = mode_cfg["colors"]
        
        # Add background spans
        if col in df_regimes.columns:
            df_regimes["group"] = (df_regimes[col] != df_regimes[col].shift()).cumsum()
            for val, color in colors.items():
                mask = df_regimes[col] == val
                for _, group_df in df_regimes[mask].groupby("group"):
                    fig.add_vrect(
                        x0=group_df["date"].iloc[0],
                        x1=group_df["date"].iloc[-1],
                        fillcolor=color,
                        opacity=0.2,
                        layer="below",
                        line_width=0,
                        name=val
                    )

        # Add Asset Price
        fig.add_trace(go.Scatter(x=df_regimes["date"], y=df_regimes[asset_to_plot], name=asset_to_plot, line=dict(color="black", width=2)))
        
        fig.update_layout(title=f"{asset_to_plot} vs {timeline_mode}", xaxis_title="Date", showlegend=True, height=500)
        st.plotly_chart(fig, use_container_width=True)

        # 3. Intelligence Insights (Matrix + Policy)
        st.divider()
        st.subheader("Quantitative Insights")
        
        tab1, tab2 = st.tabs(["Asset Performance by Regime", "Policy Cycle Sensitivity"])
        
        with tab1:
            stats_df = engine.get_regime_stats()
            col_a, col_b = st.columns(2)
            with col_a:
                pivot_ret = stats_df.pivot(index="Regime", columns="Asset", values="Annualized Return (%)")
                fig_heat = px.imshow(pivot_ret, text_auto=".2f", color_continuous_scale="RdYlGn", title="Annualized Returns (%)")
                st.plotly_chart(fig_heat, use_container_width=True)
            with col_b:
                st.dataframe(stats_df, use_container_width=True)
                
        with tab2:
            st.info("Analysis of how SA assets perform during different SARB monetary policy phases.")
            policy_stats = []
            for asset in ["jse_alsi", "usd_zar"]:
                if asset in df_regimes.columns:
                    ret_col = f"{asset}_ret"
                    if ret_col not in df_regimes.columns:
                        df_regimes[ret_col] = df_regimes[asset].pct_change()
                    
                    for state in engine.POLICY_STATES.values():
                        data = df_regimes[df_regimes["policy_cycle"] == state][ret_col]
                        if not data.empty:
                            policy_stats.append({
                                "Asset": asset,
                                "Policy Cycle": state,
                                "Avg Ann Return (%)": data.mean() * 252 * 100,
                                "Volatility (%)": data.std() * np.sqrt(252) * 100,
                                "Samples": len(data)
                            })
            st.table(pd.DataFrame(policy_stats))

        # 4. Interactive Backtester
        st.divider()
        st.subheader("Strategy Lab: Regime Rotation")
        
        bt_col1, bt_col2 = st.columns([1, 3])
        
        with bt_col1:
            st.info("Test a strategy that holds the asset ONLY during specific macro conditions.")
            selected_asset = st.selectbox("Asset to Trade", ["jse_alsi", "saf_equity_etf"])
            active_regimes = st.multiselect(
                "Active Regimes", 
                options=list(engine.REGIMES.values()),
                default=[list(engine.REGIMES.values())[0]]
            )
            
        if active_regimes:
            backtester = RegimeBacktester(df_regimes, asset_col=selected_asset)
            df_results = backtester.run_strategy(active_regimes)
            metrics = backtester.get_performance_metrics()
            
            with bt_col2:
                fig_bt = go.Figure()
                fig_bt.add_trace(go.Scatter(x=df_results["date"], y=df_results["bh_equity"], name="Buy & Hold (Benchmark)", line=dict(dash='dash', color='gray')))
                fig_bt.add_trace(go.Scatter(x=df_results["date"], y=df_results["strat_equity"], name="Regime Strategy", line=dict(width=3, color='blue')))
                fig_bt.update_layout(title="Equity Growth (Regime Rotation Strategy)", yaxis_type="log", height=400)
                st.plotly_chart(fig_bt, use_container_width=True)
                st.table(metrics)
