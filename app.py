import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import src.data_loader
import importlib

st.set_page_config(
    page_title="SA Macro Regime Dashboard",
    page_icon="🇿🇦",
    layout="wide"
)

importlib.reload(src.data_loader)
from src.data_loader import DataLoader

def get_loader():
    return DataLoader()

loader = get_loader()

def check_table_exists(table_name):
    try:
        loader.conn.execute(f"SELECT 1 FROM {table_name} LIMIT 1")
        return True
    except:
        return False

# Sidebar
st.sidebar.header("Data Management")
st.sidebar.caption("v2.1.0 - Multi-Source Engine")
if st.sidebar.button("🔄 Update Dashboard Data"):
    with st.spinner("Fetching data from Multi-Sources..."):
        try:
            loader.update_database()
            st.sidebar.success("Database updated!")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Error updating database: {e}")

# Provenance Info
prov_df = loader.get_provenance()
if not prov_df.empty:
    st.sidebar.divider()
    st.sidebar.subheader("Data Sources")
    for _, row in prov_df.iterrows():
        st.sidebar.caption(f"**{row['indicator'].upper()}**: {row['source']}")
    st.sidebar.caption("**MARKET DATA**: Yahoo Finance")

# Check for macro_series table
if check_table_exists("macro_series"):
    df = loader.load_from_db()
    df['date'] = pd.to_datetime(df['date'])
    
    # Latest Metrics
    st.subheader("Current Market & Macro Indicators")
    cols = st.columns(3)
    
    # USD/ZAR
    if 'usd_zar' in df.columns:
        latest_val = df['usd_zar'].iloc[-1]
        prev_val = df['usd_zar'].iloc[-2] if len(df) > 1 else latest_val
        delta = ((latest_val - prev_val) / prev_val) * 100
        cols[0].metric("USD/ZAR", f"R{latest_val:.2f}", f"{delta:.2f}%")
        
    # JSE ALSI
    if 'jse_alsi' in df.columns:
        latest_val = df['jse_alsi'].iloc[-1]
        prev_val = df['jse_alsi'].iloc[-2] if len(df) > 1 else latest_val
        delta = ((latest_val - prev_val) / prev_val) * 100
        cols[1].metric("JSE ALSI", f"{latest_val:,.0f}", f"{delta:.2f}%")

    # Repo Rate
    if 'repo_rate' in df.columns:
        latest_val = df['repo_rate'].iloc[-1]
        cols[2].metric("Repo Rate", f"{latest_val:.2f}%")

    # Main Charts
    tab1, tab2, tab3 = st.tabs(["Market Data", "Macro Indicators", "Raw Data"])
    
    with tab1:
        st.subheader("Market Trends")
        market_cols = ['usd_zar', 'jse_alsi', 'saf_equity_etf']
        available_market = [c for c in market_cols if c in df.columns]
        
        if available_market:
            selected_market = st.multiselect("Select Market Series", available_market, default=available_market)
            if selected_market:
                # Normalize for comparison
                df_norm = df.set_index('date')[selected_market].copy()
                df_norm = df_norm / df_norm.iloc[0] * 100
                fig = px.line(df_norm.reset_index(), x='date', y=selected_market, 
                             title="Market Series (Indexed to 100)")
                st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("Macro Indicators")
        macro_cols = ['cpi', 'repo_rate', 'yield_10y']
        available_macro = [c for c in macro_cols if c in df.columns]
        
        if available_macro:
            fig = go.Figure()
            for col in available_macro:
                fig.add_trace(go.Scatter(x=df['date'], y=df[col], name=col, mode='lines'))
            
            fig.update_layout(title="Macroeconomic Trends (%)", xaxis_title="Date", yaxis_title="Percentage")
            st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.subheader("Dataset Preview")
        st.dataframe(df.sort_values('date', ascending=False), use_container_width=True)

else:
    st.warning("No dashboard data found in `macro_series` table.")
    st.info("Click 'Update Dashboard Data' in the sidebar to populate the database.")

# Individual Tables Section
st.divider()
st.subheader("Explore Individual Tables")
tables = loader.conn.execute("SHOW TABLES").fetchall()
table_names = [t[0] for t in tables if t[0] != "macro_series"]

if table_names:
    selected_table = st.selectbox("Select a table to view", table_names)
    if selected_table:
        table_df = loader.conn.execute(f"SELECT * FROM {selected_table}").df()
        st.write(f"Showing data for: `{selected_table}`")
        st.dataframe(table_df, use_container_width=True)
        
        if 'value' in table_df.columns:
            if 'date' in table_df.columns:
                fig = px.line(table_df, x='date', y='value', title=f"Series: {selected_table}")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No 'date' column found in this table. Visualizing as a sequence.")
                fig = px.line(table_df, y='value', title=f"Series: {selected_table} (Sequential)")
                st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No individual series tables found.")
