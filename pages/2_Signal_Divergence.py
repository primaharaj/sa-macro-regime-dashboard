"""
Signal Divergence — tech posture vs SA macro posture.

Default view: 2014–2017 validated window (both price and macro data are
HIGH-confidence FRED/Yahoo series for the whole period).

LIVE REGION: dates after the cpi_samadb first_capture_date use live data.
The live region is marked with a vertical line and a confidence note.
A flag in the live region should be read as indicative only until
the macro data has accumulated additional history.

No blended score is shown anywhere. The product IS the disagreement.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date
from src.vintage_store import VintageStore
from src.signals.api import SignalAPI
from src.divergence import DivergenceDetector

st.set_page_config(page_title="Signal Divergence", layout="wide")
st.title("SA Signal Divergence")
st.caption(
    "Compares an instrument's **technical posture** (trend + momentum) against "
    "the **SA macro backdrop** (real rates, inflation trend, growth). "
    "A flag means price and macro disagree. No blended score — the gap IS the signal."
)

# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Controls")

    instrument = st.selectbox(
        "Instrument",
        ["usd_zar", "jse_alsi", "saf_equity_etf"],
        format_func=lambda x: {
            "usd_zar":       "USD/ZAR (primary)",
            "jse_alsi":      "JSE ALSI (primary)",
            "saf_equity_etf": "SAF Equity ETF (secondary — USD-muddied)",
        }[x],
    )

    st.divider()
    use_validated = st.checkbox("Start from validated window (2014)", value=True)
    extend_live   = st.checkbox("Extend to live data", value=False)

    if use_validated:
        default_start = date(2014, 1, 1)
    else:
        default_start = date(2010, 1, 1)

    default_end = date(2017, 12, 31) if not extend_live else date.today()

    start_date = st.date_input("Start date", value=default_start, min_value=date(2005, 1, 1))
    end_date   = st.date_input("End date",   value=default_end,   max_value=date(2030, 12, 31))

    st.divider()
    st.subheader("Single-date detail")
    detail_date = st.date_input(
        "Inspect date",
        value=date(2015, 12, 16),
        help="Compute the full divergence packet for one date.",
    )
    run_detail = st.button("Compute packet")

# ---------------------------------------------------------------------------
# Data loading (cached)
# ---------------------------------------------------------------------------

@st.cache_resource
def get_detector():
    store = VintageStore()
    api   = SignalAPI(store)
    return DivergenceDetector(api), store


detector, store = get_detector()

# ---------------------------------------------------------------------------
# Series computation
# ---------------------------------------------------------------------------

with st.spinner("Computing posture series…"):
    df = detector.compute_series(instrument, start_date, end_date)

if df.empty:
    st.warning("No data for the selected instrument and date range. Ensure the DB is populated.")
    st.stop()

# ---------------------------------------------------------------------------
# Live boundary marker
# ---------------------------------------------------------------------------

first_capture = store.get_first_capture_date("cpi_samadb")
live_boundary = pd.Timestamp(first_capture) if first_capture else None

# ---------------------------------------------------------------------------
# Main chart: tech_posture vs macro_posture with divergence shading
# ---------------------------------------------------------------------------

fig = go.Figure()

# Tech posture line
fig.add_trace(go.Scatter(
    x=df.index, y=df["tech_posture"],
    name="Tech posture (trend + momentum)",
    line=dict(color="#2196F3", width=2),
    hovertemplate="Tech: %{y:.1f}<extra></extra>",
))

# Macro posture line
fig.add_trace(go.Scatter(
    x=df.index, y=df["macro_posture"],
    name="Macro posture (SA backdrop)",
    line=dict(color="#FF9800", width=2),
    hovertemplate="Macro: %{y:.1f}<extra></extra>",
))

# Shade flagged divergence periods (where |div| > 80th pct)
if "flagged" in df.columns:
    flagged = df[df["flagged"] == True]
    if not flagged.empty:
        # Group consecutive flagged dates into spans
        flagged_idx = flagged.index
        starts, ends = [], []
        i = 0
        while i < len(flagged_idx):
            starts.append(flagged_idx[i])
            j = i
            while j + 1 < len(flagged_idx) and (flagged_idx[j + 1] - flagged_idx[j]).days <= 5:
                j += 1
            ends.append(flagged_idx[j])
            i = j + 1

        for s, e in zip(starts, ends):
            fig.add_vrect(
                x0=s, x1=e,
                fillcolor="#E53935", opacity=0.15,
                layer="below", line_width=0,
                annotation_text="Flag" if (e - s).days < 5 else "",
                annotation_position="top left",
            )

# Live boundary line
if live_boundary and pd.Timestamp(start_date) <= live_boundary <= pd.Timestamp(end_date):
    fig.add_vline(
        x=live_boundary,
        line_dash="dot", line_color="gray", line_width=1.5,
    )
    fig.add_annotation(
        x=live_boundary, y=95,
        text="← FRED vintage | live →",
        showarrow=False, font=dict(size=10, color="gray"),
        xanchor="left",
    )

fig.update_layout(
    title=f"{instrument} — Tech posture vs SA macro posture",
    xaxis_title="Date",
    yaxis_title="Posture (0–100 percentile rank)",
    yaxis=dict(range=[0, 100]),
    hovermode="x unified",
    height=420,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)
st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Divergence chart (below the posture chart)
# ---------------------------------------------------------------------------

fig2 = go.Figure()

fig2.add_trace(go.Scatter(
    x=df.index, y=df["divergence"],
    name="Divergence (tech − macro)",
    line=dict(color="#9C27B0", width=1.5),
    fill="tozeroy",
    fillcolor="rgba(156,39,176,0.08)",
    hovertemplate="Div: %{y:.1f}<extra></extra>",
))

if "rolling_80th_pct_thresh" in df.columns:
    fig2.add_trace(go.Scatter(
        x=df.index, y=df["rolling_80th_pct_thresh"],
        name="80th pct threshold",
        line=dict(color="#E53935", width=1, dash="dash"),
        hovertemplate="Threshold: %{y:.1f}<extra></extra>",
    ))
    fig2.add_trace(go.Scatter(
        x=df.index, y=-df["rolling_80th_pct_thresh"],
        name="−80th pct threshold",
        line=dict(color="#E53935", width=1, dash="dash"),
        showlegend=False,
        hovertemplate="Threshold: %{y:.1f}<extra></extra>",
    ))

if live_boundary and pd.Timestamp(start_date) <= live_boundary <= pd.Timestamp(end_date):
    fig2.add_vline(
        x=live_boundary,
        line_dash="dot", line_color="gray", line_width=1.5,
    )

fig2.update_layout(
    title="Signed divergence with ±80th percentile flag threshold",
    xaxis_title="Date",
    yaxis_title="Divergence",
    hovermode="x unified",
    height=280,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)
st.plotly_chart(fig2, use_container_width=True)

# ---------------------------------------------------------------------------
# Orientation note (always visible — prevents sign-error confusion)
# ---------------------------------------------------------------------------

with st.expander("Macro posture orientation for this instrument"):
    notes = {
        "usd_zar": (
            "**macro_posture HIGH = macro justifies ZAR weakness (high USDZAR).**\n\n"
            "- `growth_backdrop` inverted: low SA growth → ZAR weak\n"
            "- `real_policy_rate` inverted: low real rate → ZAR weak (hawkish = ZAR-supportive per spec)\n"
            "- `inflation_trend` direct: rising inflation → ZAR erodes\n\n"
            "A divergence where tech > macro means price is weaker than the SA macro backdrop justifies.\n"
            "A divergence where macro > tech means the SA macro environment argues for more ZAR "
            "weakness than the current price reflects."
        ),
        "jse_alsi": (
            "**macro_posture HIGH = SA macro is supportive for JSE equity.**\n\n"
            "- `growth_backdrop` direct: high SA growth → equity-supportive\n"
            "- `real_policy_rate` inverted: low real rate → easy credit + low discount rate → bullish\n"
            "- `inflation_trend` inverted: falling inflation → less CB tightening → bullish\n\n"
            "A divergence where tech > macro means equities are pricing in more positivity "
            "than the macro backdrop justifies."
        ),
        "saf_equity_etf": (
            "**Same orientation as JSE ALSI** (equity: loose policy + positive growth = supportive).\n\n"
            "**Important caveat**: EZA is USD-denominated. USD/ZAR movements affect the ETF price "
            "independent of SA macro fundamentals. The SA macro_posture does not capture this USD "
            "channel, so divergences here may partly reflect currency effects rather than "
            "pure SA macro-vs-price misalignment. Treat as secondary evidence only."
        ),
    }
    st.markdown(notes.get(instrument, ""))

# ---------------------------------------------------------------------------
# Single-date detail packet
# ---------------------------------------------------------------------------

if run_detail:
    with st.spinner(f"Computing packet for {detail_date}…"):
        pkt = detector.compute(instrument, detail_date)

    if pkt is None:
        st.warning(f"No packet available for {instrument} at {detail_date}. "
                   "Ensure the DB is populated and the date is within the data window.")
    else:
        st.subheader(f"Divergence packet — {instrument} at {detail_date}")

        conf_color = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(pkt["confidence"], "⚪")
        flag_badge = "🚩 FLAGGED" if pkt["flagged"] else "✅ No flag"
        act_badge  = "⚡ Actionable" if pkt["actionable"] else "🔇 Non-actionable"

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Tech posture",  f"{pkt['tech_posture']:.1f}")
        col2.metric("Macro posture", f"{pkt['macro_posture']:.1f}")
        col3.metric("Divergence",    f"{pkt['divergence']:.1f}")
        col4.metric("Percentile",    f"{pkt['percentile']:.0f}th")

        col5, col6, col7, col8 = st.columns(4)
        col5.metric("Flag", flag_badge)
        col6.metric("Confidence", f"{conf_color} {pkt['confidence']}")
        col7.metric("Status", act_badge)
        col8.metric("Outlier family", pkt["outlier_family"])

        if extend_live and live_boundary and pd.Timestamp(detail_date) >= live_boundary:
            st.info(
                f"This date is in the **live region** (after {first_capture}). "
                f"Macro source: `{pkt['macro_source']}` ({pkt['macro_boundary']}). "
                "Treat live flags as indicative — less historically validated."
            )

        with st.expander("Full packet"):
            st.json({k: str(v) for k, v in pkt.items()})
