"""
Divergence Explorer — tech posture vs SA macro posture over time.

Primary targets: usd_zar, jse_alsi.
Secondary: saf_equity_etf (USD-muddied — caveat displayed).

The Dec 2015 Nene shock (2015-12-11) is the validated reference case.
Use the single-date inspector to reproduce the packet: tech≈99.2, macro≈45.3,
div≈53.9, pct≈84.5 → flagged, outlier_family=technicals.

Note: the series chart uses a vectorized approximation of the macro posture;
the single-date inspector uses the precise PIT path through SignalAPI.
These can disagree slightly — the single-date packet is authoritative.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date

from src.vintage_store import VintageStore
from src.signals.api import SignalAPI
from src.divergence import DivergenceDetector
from src.ui import (
    conf_badge, SOURCE_LABEL, INSTRUMENT_LABEL, DISCLAIMER,
    VALIDATED_START, VALIDATED_END, NENE_DATE,
    TECH_COLOR, MACRO_COLOR, DIV_COLOR, THRESH_COLOR,
    FLAG_FILL, LIVE_FILL, CONF_HEX,
)

st.set_page_config(page_title="Divergence Explorer", layout="wide")

# ── Cached objects ────────────────────────────────────────────────────────────
@st.cache_resource
def _load():
    store = VintageStore()
    api   = SignalAPI(store)
    return store, api, DivergenceDetector(api)

store, api, detector = _load()

# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Controls")

    instrument = st.selectbox(
        "Instrument",
        ["usd_zar", "jse_alsi", "saf_equity_etf"],
        format_func=lambda x: INSTRUMENT_LABEL[x],
    )

    st.divider()
    use_validated = st.checkbox("Start from validated window (2014)", value=True)
    extend_live   = st.checkbox("Extend to live data", value=False)

    default_start = VALIDATED_START if use_validated else date(2010, 1, 1)
    default_end   = date.today() if extend_live else VALIDATED_END

    start_date = st.date_input("Start date", value=default_start, min_value=date(2005, 1, 1))
    end_date   = st.date_input("End date",   value=default_end,   max_value=date(2030, 12, 31))

    st.divider()
    st.subheader("Single-date packet")
    default_detail = NENE_DATE if instrument == "usd_zar" else date(2016, 1, 15)
    detail_date = st.date_input(
        "Inspect date",
        value=default_detail,
        min_value=date(2005, 1, 1),
        help=(
            "usd_zar default: Dec 2015 Nene shock (the validated reference case). "
            "Compute the full divergence packet for any date."
        ),
    )
    run_detail = st.button("Compute packet")

# ── Live boundary ─────────────────────────────────────────────────────────────
first_capture = store.get_first_capture_date("cpi_samadb")
live_boundary = pd.Timestamp(first_capture) if first_capture else None

# ── Title + orientation ───────────────────────────────────────────────────────
st.title(f"Divergence Explorer — {INSTRUMENT_LABEL[instrument]}")
st.caption(
    "Compares **tech posture** (trend + momentum, 0–100 percentile rank) against "
    "**macro posture** (SA macro backdrop, signed per instrument, 0–100). "
    "A flag means the absolute gap is in the top quintile of the past year."
)

# Orientation note — always visible, not buried (USDZAR sign is non-obvious)
if instrument == "usd_zar":
    st.warning(
        "**USDZAR orientation — read before interpreting:** "
        "`macro_posture HIGH` = macro **justifies ZAR weakness** (high USDZAR). "
        "A hawkish/high-real-rate backdrop argues for *lower* USDZAR → **LOW** macro_posture. "
        "tech > macro = price moved weaker than macro justifies. "
        "macro > tech = macro argues for more weakness than price reflects.",
        icon="⚠️",
    )
elif instrument == "saf_equity_etf":
    st.info(
        "**EZA (SAF Equity ETF) caveat:** USD-denominated. USD/ZAR movements affect the ETF "
        "independently of SA macro fundamentals. The SA macro_posture does not capture the "
        "USD channel. Treat as secondary evidence only.",
        icon="ℹ️",
    )

# ── Compute series (vectorised approximation for chart) ───────────────────────
with st.spinner("Computing divergence series…"):
    df = detector.compute_series(instrument, start_date, end_date)

if df.empty:
    st.warning(
        "No data for the selected instrument and date range. "
        "Ensure the database is populated (`python -m src.vintage_store`)."
    )
    st.stop()

start_ts = pd.Timestamp(start_date)
end_ts   = pd.Timestamp(end_date)


def _add_live_marker(fig):
    if live_boundary and start_ts <= live_boundary <= end_ts:
        fig.add_vline(x=live_boundary, line_dash="dot", line_color="gray", line_width=1.5)
        fig.add_annotation(
            x=live_boundary, y=1, yref="paper",
            text="← FRED vintage | SAMADB live →",
            showarrow=False, font=dict(size=9, color="gray"),
            xanchor="left",
        )
        if extend_live:
            fig.add_vrect(
                x0=live_boundary, x1=end_ts,
                fillcolor=LIVE_FILL, layer="below", line_width=0,
            )


def _shade_flags(fig, df_plot):
    """Add red shading over consecutive flagged periods."""
    if "flagged" not in df_plot.columns:
        return
    flagged_idx = df_plot.index[df_plot["flagged"] == True]
    if flagged_idx.empty:
        return
    starts, ends = [], []
    i = 0
    while i < len(flagged_idx):
        starts.append(flagged_idx[i])
        j = i
        while j + 1 < len(flagged_idx) and (flagged_idx[j+1] - flagged_idx[j]).days <= 5:
            j += 1
        ends.append(flagged_idx[j])
        i = j + 1
    for s, e in zip(starts, ends):
        fig.add_vrect(
            x0=s, x1=e,
            fillcolor=FLAG_FILL, layer="below", line_width=0,
        )


# ── Chart 1: Tech posture vs Macro posture ────────────────────────────────────
fig1 = go.Figure()

fig1.add_trace(go.Scatter(
    x=df.index, y=df["tech_posture"],
    name="Tech posture (trend + momentum)",
    line=dict(color=TECH_COLOR, width=2),
    hovertemplate="Tech: %{y:.1f}<extra></extra>",
))
fig1.add_trace(go.Scatter(
    x=df.index, y=df["macro_posture"],
    name="Macro posture (SA backdrop)",
    line=dict(color=MACRO_COLOR, width=2),
    hovertemplate="Macro: %{y:.1f}<extra></extra>",
))

_shade_flags(fig1, df)
_add_live_marker(fig1)

# Dec 2015 annotation if in range
nene_ts = pd.Timestamp(NENE_DATE)
if start_ts <= nene_ts <= end_ts and instrument == "usd_zar":
    fig1.add_vline(x=nene_ts, line_dash="longdash", line_color="#333", line_width=1)
    fig1.add_annotation(
        x=nene_ts, y=95,
        text="Dec 2015<br>Nene shock",
        showarrow=True, arrowhead=2,
        font=dict(size=9), bgcolor="white", borderpad=2,
    )

fig1.update_layout(
    title=f"{INSTRUMENT_LABEL[instrument]} — Tech posture vs Macro posture (0–100 scale)",
    xaxis_title="Date",
    yaxis_title="Posture (percentile rank)",
    yaxis=dict(range=[0, 100]),
    hovermode="x unified",
    height=400,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)
fig1.add_annotation(
    text="🔴 Shaded = flagged period (|divergence| > 80th pct of trailing year)",
    xref="paper", yref="paper", x=0.01, y=0.02,
    showarrow=False, font=dict(size=9, color="#888"),
)
st.plotly_chart(fig1, use_container_width=True)

# ── Chart 2: Divergence with threshold ───────────────────────────────────────
fig2 = go.Figure()

fig2.add_trace(go.Scatter(
    x=df.index, y=df["divergence"],
    name="Divergence (tech − macro)",
    line=dict(color=DIV_COLOR, width=1.5),
    fill="tozeroy",
    fillcolor="rgba(156,39,176,0.07)",
    hovertemplate="Div: %{y:.1f}<extra></extra>",
))

if "rolling_80th_pct_thresh" in df.columns:
    thresh = df["rolling_80th_pct_thresh"]
    fig2.add_trace(go.Scatter(
        x=df.index, y=thresh,
        name="80th pct threshold",
        line=dict(color=THRESH_COLOR, width=1, dash="dash"),
        hovertemplate="+threshold: %{y:.1f}<extra></extra>",
    ))
    fig2.add_trace(go.Scatter(
        x=df.index, y=-thresh,
        name="−80th pct threshold",
        line=dict(color=THRESH_COLOR, width=1, dash="dash"),
        showlegend=False,
        hovertemplate="−threshold: %{y:.1f}<extra></extra>",
    ))

_shade_flags(fig2, df)
_add_live_marker(fig2)

fig2.update_layout(
    title="Signed divergence with ±80th percentile flag threshold",
    xaxis_title="Date",
    yaxis_title="Divergence (tech − macro)",
    hovermode="x unified",
    height=280,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)
st.plotly_chart(fig2, use_container_width=True)

st.caption(
    "**Chart note**: posture series and flag threshold above use a vectorised approximation "
    "of the macro posture. Single-date packets below use the precise PIT path (SignalAPI) "
    "and may differ slightly. The single-date packet is authoritative."
)

# ── Summary stats for visible range ──────────────────────────────────────────
n_flagged = int(df["flagged"].sum()) if "flagged" in df.columns else 0
n_total   = len(df)
pct_flagged = 100 * n_flagged / n_total if n_total > 0 else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Days in range", n_total)
c2.metric("Flagged days", n_flagged)
c3.metric("% flagged", f"{pct_flagged:.1f}%")
c4.metric(
    "Latest divergence",
    f"{df['divergence'].iloc[-1]:.1f}" if not df.empty else "n/a",
)

# ── Single-date packet ────────────────────────────────────────────────────────
st.divider()
st.subheader("Single-date packet (precise PIT path)")

if run_detail or (instrument == "usd_zar" and detail_date == NENE_DATE):
    if not run_detail:
        st.info(
            f"Showing **Dec 2015 Nene shock** reference case ({NENE_DATE}) by default. "
            "Select a different date in the sidebar and click 'Compute packet' to inspect it.",
        )

    with st.spinner(f"Computing packet for {instrument} at {detail_date}…"):
        pkt = detector.compute(instrument, detail_date)

    if pkt is None:
        st.warning(
            f"No packet available for {instrument} at {detail_date}. "
            "The date may be outside the data window or the database may not be populated."
        )
    else:
        conf_l    = pkt["confidence"]
        flagged   = pkt["flagged"]
        actionable = pkt["actionable"]

        # Status header
        if flagged and actionable:
            status_color = CONF_HEX["HIGH"]
            status_text  = "🚩 FLAGGED — actionable"
        elif flagged:
            status_color = CONF_HEX["MEDIUM"]
            status_text  = "🚩 FLAGGED — non-actionable (LOW confidence)"
        else:
            status_color = "#607D8B"
            status_text  = "✅ No flag"

        st.markdown(
            f'<div style="border-left:5px solid {status_color};padding:8px 14px;'
            f'background:#f9f9f9;border-radius:3px;margin-bottom:8px">'
            f'<b>{INSTRUMENT_LABEL[instrument]}</b> at <b>{detail_date}</b> — {status_text}'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Metrics grid
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Tech posture",  f"{pkt['tech_posture']:.2f}")
        c2.metric("Macro posture", f"{pkt['macro_posture']:.2f}")
        c3.metric("Divergence",    f"{pkt['divergence']:.2f}")
        c4.metric("Percentile",    f"{pkt['percentile']:.1f}th")

        c5, c6, c7, c8 = st.columns(4)
        c5.markdown(f"**Flag** {'🚩' if flagged else '✅'}", )
        c6.markdown(f"**Confidence**\n\n{conf_badge(conf_l)}", unsafe_allow_html=True)
        c7.markdown(f"**Actionable**\n\n{'⚡ Yes' if actionable else '🔇 No'}")
        c8.markdown(f"**Outlier**\n\n`{pkt['outlier_family']}`")

        # Source labels
        macro_src = pkt.get("macro_source", "unknown")
        macro_bnd = pkt.get("macro_boundary", "unknown")
        live_region = macro_bnd == "live"
        if live_region:
            st.info(
                f"⚡ **Live region** — macro source: `{macro_src}` "
                f"({SOURCE_LABEL.get(macro_src, macro_src)}). "
                "Live flags are less historically validated than the 2014–2017 window.",
                icon="📡",
            )
        else:
            st.caption(
                f"Macro source: `{macro_src}` ({SOURCE_LABEL.get(macro_src, macro_src)}) · "
                f"boundary: {macro_bnd}"
            )

        # Dec 2015 reference annotation
        if detail_date == NENE_DATE and instrument == "usd_zar":
            st.success(
                "📍 **Reference case — Dec 2015 Nene shock**: "
                "USDZAR spiked ~13% in three days after the evening firing of Finance Minister Nene. "
                "Monthly SA macro data (real rates, inflation, growth) did not revise on that timescale. "
                "Expected: tech_posture ≈ 99.2, macro_posture ≈ 45.3, divergence ≈ 53.9, "
                "percentile ≈ 84.5, flagged=True, outlier_family='technicals'. "
                "This test is codified in `tests/test_divergence.py::test_nene_shock_fires`.",
            )

        # Full JSON packet
        with st.expander("Full packet (all fields)"):
            st.json({k: str(v) for k, v in pkt.items()})

else:
    st.info(
        "Select a date in the sidebar and click **Compute packet**. "
        f"For {INSTRUMENT_LABEL[instrument]}, a good starting point is the "
        f"default date ({default_detail}) "
        f"{'— the Dec 2015 Nene shock reference case.' if instrument == 'usd_zar' else '.'}",
    )

# ── Methodology expander ──────────────────────────────────────────────────────
st.divider()
with st.expander("Show divergence methodology"):
    st.markdown(f"""
#### Divergence methodology — {INSTRUMENT_LABEL[instrument]}

**Tech posture**:
```
ma_252       = prices.rolling(252).mean()
trend_pct    = rolling_pct(prices / ma_252 − 1,       window=252)
momentum_pct = rolling_pct(prices / prices.shift(21) − 1, window=252)
tech_posture = (trend_pct + momentum_pct) / 2
```
`rolling_pct` ranks the current value within the trailing 252-day window,
excluding the current point from the comparison: `(x[:-1] < x[-1]).mean() × 100`.

**Macro posture** — signed mean of normalised sub-signals:

| Sub-signal | Direction | Rationale |
|---|---|---|
""" + ("""
| `growth_backdrop`  | −1 | Low SA growth → ZAR weak → high USDZAR |
| `real_policy_rate` | −1 | Low real rate → less hawkish → ZAR weak |
| `inflation_trend`  | +1 | Rising inflation → ZAR erodes |
""" if instrument == "usd_zar" else """
| `growth_backdrop`  | +1 | High growth → equity earnings positive |
| `real_policy_rate` | −1 | Low real rate → easy credit, low discount rate |
| `inflation_trend`  | −1 | Falling inflation → less CB tightening |
""") + """
Direction −1: `contribution = 100 − normalised`. Direction +1: `contribution = normalised`.
`macro_posture = mean(contributions)`.

**Flagging**:
```
divergence     = tech_posture − macro_posture
abs_divergence = |divergence|
percentile     = (trailing_252_abs < abs_divergence).mean() × 100
flagged        = percentile ≥ 80.0
```
Trailing window: **252 trading days** (1 year). Calibrates to the current volatility regime.

**Attribution (outlier_family)**:
```
tech_z  = |tech_posture − mean(trailing_252_tech)| / std(trailing_252_tech)
macro_z = |macro_posture − mean(trailing_252_macro)| / std(trailing_252_macro)
→ "technicals" if tech_z > macro_z × 1.5
→ "macro"      if macro_z > tech_z × 1.5
→ "both"       if both > 1.5
→ "aligned"    otherwise
```

**Confidence** = `min(tech_confidence, macro_confidence)`.
Actionable only if confidence is HIGH or MEDIUM and the flag is firing.
Sub-signals with `staleness_days ≥ 500` (GDP placeholder at historical dates)
are excluded from the macro confidence minimum.
    """)

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(DISCLAIMER)
