"""
Macro — historical view of SA macro series with live boundary marking.

Shows raw time series (repo, yield, CPI YoY) and derived sub-signals
(real policy rate, curve slope, inflation trend) over a user-selected
date range. A single-date inspector shows the full signal packet with
confidence badges for each sub-signal.
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import date

from src.vintage_store import VintageStore
from src.signals.api import SignalAPI
from src.ui import (
    conf_badge, SOURCE_LABEL, DISCLAIMER,
    VALIDATED_START, VALIDATED_END,
    TECH_COLOR, MACRO_COLOR, DIV_COLOR, LIVE_FILL,
)

st.set_page_config(page_title="SA Macro — Historical View", layout="wide")

# ── Shared resource ───────────────────────────────────────────────────────────
@st.cache_resource
def _load():
    store = VintageStore()
    return store, SignalAPI(store)

store, api = _load()

# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Controls")
    use_validated = st.checkbox("Start from validated window (2014)", value=True)
    extend_live   = st.checkbox("Extend to live data (post-SAMADB capture)", value=False)

    start_date = st.date_input(
        "Start date",
        value=VALIDATED_START if use_validated else date(2010, 1, 1),
        min_value=date(2000, 1, 1),
    )
    end_date = st.date_input(
        "End date",
        value=date.today() if extend_live else VALIDATED_END,
        max_value=date(2030, 12, 31),
    )

    st.divider()
    st.subheader("Single-date signal inspector")
    inspect_date = st.date_input(
        "Inspect date",
        value=date(2016, 1, 1),
        min_value=date(2000, 1, 1),
    )
    run_inspect = st.button("Compute signal packet")

# ── Live boundary ─────────────────────────────────────────────────────────────
first_capture = store.get_first_capture_date("cpi_samadb")
live_boundary = pd.Timestamp(first_capture) if first_capture else None

# ── Title ─────────────────────────────────────────────────────────────────────
st.title("SA Macro — Historical View")
st.caption(
    "Raw and derived SA macro series from the PIT vintage store. "
    "All historical data is read through FRED ALFRED vintage path (no look-ahead). "
    "The live region (after the dashed line) uses SAMADB CPI and the manual MPC repo table."
)

if use_validated and not extend_live:
    st.info(
        "📌 Showing the **validated window** (2014–2017) where both macro and technical "
        "signals are confirmed HIGH-confidence. Extend to live data with the sidebar checkbox.",
    )

# ── Load raw series from store (as-of end_date = most recent PIT cut) ─────────
@st.cache_data(ttl=300)
def _load_raw_series(end_dt):
    cpi_df    = store.get_series("cpi",       end_dt)
    repo_df   = store.get_series("repo_rate", end_dt)
    yield_df  = store.get_series("yield_10y", end_dt)

    series = {}

    if not repo_df.empty:
        r = repo_df.set_index("date")["value"].sort_index()
        r.index = pd.to_datetime(r.index)
        series["repo_rate"] = r

    if not yield_df.empty:
        y = yield_df.set_index("date")["value"].sort_index()
        y.index = pd.to_datetime(y.index)
        series["yield_10y"] = y

    if not cpi_df.empty:
        s = cpi_df.set_index("date")["value"].sort_index()
        s.index = pd.to_datetime(s.index)
        decimal = s / 100.0
        cpi_yoy = ((1 + decimal).rolling(12).apply(np.prod, raw=True) - 1) * 100
        cpi_yoy.name = "CPI YoY (FRED vintage)"
        series["cpi_yoy_fred"] = cpi_yoy

    # Derived
    if "repo_rate" in series and "cpi_yoy_fred" in series:
        series["real_policy_rate"] = series["repo_rate"] - series["cpi_yoy_fred"]
    if "yield_10y" in series and "repo_rate" in series:
        series["curve_slope"] = series["yield_10y"] - series["repo_rate"]
    if "cpi_yoy_fred" in series:
        series["inflation_trend"] = series["cpi_yoy_fred"].diff(3)

    return series


@st.cache_data(ttl=300)
def _load_live_series(end_dt, first_cap):
    """Load SAMADB CPI YoY for the live region (after first_capture_date)."""
    if first_cap is None or end_dt < first_cap:
        return {}
    cpi_live_df = store.get_series("cpi_samadb", end_dt)
    if cpi_live_df.empty:
        return {}
    s = cpi_live_df.set_index("date")["value"].sort_index()
    s.index = pd.to_datetime(s.index)
    cpi_yoy_live = (s / s.shift(12) - 1) * 100
    cpi_yoy_live.name = "CPI YoY (SAMADB live)"

    # Repo from MPC: get from store
    repo_mpc_df = store.get_series("repo_mpc", end_dt)
    if not repo_mpc_df.empty:
        r_mpc = repo_mpc_df.set_index("date")["value"].sort_index()
        r_mpc.index = pd.to_datetime(r_mpc.index)
        r_mpc_ffill = r_mpc.resample("ME").last().ffill()
        real_live = r_mpc_ffill - cpi_yoy_live
        return {"cpi_yoy_live": cpi_yoy_live, "real_policy_live": real_live}
    return {"cpi_yoy_live": cpi_yoy_live}


raw = _load_raw_series(end_date)
live = _load_live_series(end_date, first_capture) if extend_live else {}

start_ts = pd.Timestamp(start_date)
end_ts   = pd.Timestamp(end_date)


def _trim(s):
    return s.loc[start_ts:end_ts] if not s.empty else s


def _add_live_boundary(fig, series_in_range):
    if live_boundary and start_ts <= live_boundary <= end_ts and series_in_range:
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


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(
    ["Interest Rates", "Inflation", "Real Rates & Slope", "Signal Table"]
)

# ────────────────────────────────────────────────────────────────────────────
# Tab 1 — Interest Rates
# ────────────────────────────────────────────────────────────────────────────
with tab1:
    st.subheader("SA Interest Rates — Repo & 10-Year Yield")
    st.caption("Source: FRED ALFRED IRSTCB01ZAM156N (repo) · IRLTLT01ZAM156N (yield). "
               "Note: FRED repo_rate is frozen at Dec 2023 (8.25%). "
               "Live repo from manual MPC table is shown in the Macro snapshot on the landing page.")

    fig = go.Figure()

    if "repo_rate" in raw:
        s = _trim(raw["repo_rate"])
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values, name="Repo Rate (FRED, % p.a.)",
            line=dict(color=MACRO_COLOR, width=2),
        ))

    if "yield_10y" in raw:
        s = _trim(raw["yield_10y"])
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values, name="10-Year Yield (FRED, % p.a.)",
            line=dict(color=TECH_COLOR, width=2),
        ))

    _add_live_boundary(fig, "repo_rate" in raw)
    fig.update_layout(
        title="Repo Rate vs 10-Year Yield (%)",
        xaxis_title="Date", yaxis_title="% p.a.",
        hovermode="x unified", height=380,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Show methodology"):
        st.markdown("""
**Repo Rate** (FRED ALFRED `IRSTCB01ZAM156N`): SARB policy repo rate as published by OECD/FRED.
This series is frozen at December 2023 (8.25%). For current repo, see the landing page which
uses the manual MPC table.

**10-Year Yield** (FRED ALFRED `IRLTLT01ZAM156N`): SA long bond benchmark yield.

Vintage class: BACKFILLABLE — queries return the value as it was *known* at `end_date`.
Each observation may have been revised by OECD after initial publication.
        """)

# ────────────────────────────────────────────────────────────────────────────
# Tab 2 — Inflation
# ────────────────────────────────────────────────────────────────────────────
with tab2:
    st.subheader("SA Inflation — YoY (%)")
    st.caption(
        "FRED path: compound 12 monthly MoM% values from CPALTT01ZAM657N. "
        "Live path (amber): 12-month index ratio from SAMADB CPS00000."
    )

    fig2 = go.Figure()

    if "cpi_yoy_fred" in raw:
        s = _trim(raw["cpi_yoy_fred"])
        fig2.add_trace(go.Scatter(
            x=s.index, y=s.values, name="CPI YoY — FRED vintage",
            line=dict(color=TECH_COLOR, width=2),
        ))

    if "cpi_yoy_live" in live:
        s_live = _trim(live["cpi_yoy_live"])
        fig2.add_trace(go.Scatter(
            x=s_live.index, y=s_live.values, name="CPI YoY — SAMADB live",
            line=dict(color="#E67E22", width=2.5, dash="dot"),
        ))

    if "inflation_trend" in raw:
        s_trend = _trim(raw["inflation_trend"])
        fig2.add_trace(go.Scatter(
            x=s_trend.index, y=s_trend.values, name="Inflation Trend (3-month Δ YoY)",
            line=dict(color=DIV_COLOR, width=1.5, dash="dash"),
            yaxis="y2",
        ))
        fig2.update_layout(
            yaxis2=dict(title="3-month Δ (pp)", overlaying="y", side="right", showgrid=False)
        )

    _add_live_boundary(fig2, "cpi_yoy_fred" in raw)
    fig2.add_hline(y=4.5, line_dash="dot", line_color="#888", line_width=1,
                   annotation_text="SARB midpoint (4.5%)", annotation_position="top right")
    fig2.add_hline(y=6.0, line_dash="dot", line_color="#E53935", line_width=1,
                   annotation_text="Upper band (6%)", annotation_position="top right")
    fig2.update_layout(
        title="SA Inflation YoY (%)",
        xaxis_title="Date", yaxis_title="YoY %",
        hovermode="x unified", height=400,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig2, use_container_width=True)

    with st.expander("Show methodology"):
        st.markdown("""
**FRED path** (`cpi` canonical, BACKFILLABLE):
```
CPI_YoY_t = (∏ᵢ₌₁¹² (1 + MoM_{t-i+1} / 100)) − 1,  expressed as %
```
12 monthly rates are compounded. Known anomaly: FRED series shows implausible
real policy rates around 2023 (StatsSA 2022 rebasing artefact).

**SAMADB path** (`cpi_samadb`, REVISED_NO_VINTAGE):
```
CPI_YoY_t = (index_t / index_{t-12} − 1) × 100
```
Index base: December 2024 = 100. No vintage history — current revision only.

**Inflation trend**: `CPI_YoY.diff(3)` — three-month acceleration/deceleration.

**SARB target**: 3–6% band, midpoint 4.5%.
        """)

# ────────────────────────────────────────────────────────────────────────────
# Tab 3 — Real Rates & Curve
# ────────────────────────────────────────────────────────────────────────────
with tab3:
    st.subheader("Real Policy Rate & Yield Curve Slope")
    st.caption(
        "Real policy rate = repo − inflation YoY. "
        "Curve slope = 10Y yield − repo. "
        "Both derived from FRED vintage data; live-region values use SAMADB CPI where shown."
    )

    fig3 = go.Figure()

    if "real_policy_rate" in raw:
        s = _trim(raw["real_policy_rate"])
        fig3.add_trace(go.Scatter(
            x=s.index, y=s.values, name="Real Policy Rate (FRED path)",
            line=dict(color=MACRO_COLOR, width=2),
        ))

    if "real_policy_live" in live:
        s_rl = _trim(live["real_policy_live"])
        fig3.add_trace(go.Scatter(
            x=s_rl.index, y=s_rl.values, name="Real Policy Rate (SAMADB live)",
            line=dict(color="#E67E22", width=2, dash="dot"),
        ))

    if "curve_slope" in raw:
        s = _trim(raw["curve_slope"])
        fig3.add_trace(go.Scatter(
            x=s.index, y=s.values, name="Curve Slope 10Y − Repo",
            line=dict(color=TECH_COLOR, width=2, dash="dash"),
        ))

    _add_live_boundary(fig3, "real_policy_rate" in raw)
    fig3.add_hline(y=0, line_dash="dash", line_color="#888", line_width=1)
    fig3.update_layout(
        title="Real Policy Rate & Yield Curve Slope (%)",
        xaxis_title="Date", yaxis_title="% / pp",
        hovermode="x unified", height=380,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig3, use_container_width=True)

    st.info(
        "⚠️ **Known seam around 2023**: FRED CPI data exhibits an anomaly near 2023-01-01 "
        "(likely a StatsSA 2022 rebasing artefact). Real policy rate may show implausible "
        "values in this period. SAMADB live path is used for dates after its first capture.",
        icon="⚠️",
    )

    with st.expander("Show methodology"):
        st.markdown("""
**Real Policy Rate** = `repo_rate − CPI_YoY`

High real rate → tight monetary conditions → typically ZAR-supportive, equity-negative via
discount rate. The 10-year normalisation window (120 months) captures a full monetary cycle.

**Curve Slope** = `yield_10y − repo_rate`

Positive (normal): market expects growth / higher future rates.
Negative (inverted): inversion often precedes contractionary phases.

**Data seams**:
- FRED repo_rate frozen Dec 2023 (8.25%). Live repo from MPC table on landing page.
- FRED CPI anomaly ~2023: real_policy_rate may be incorrect in this window.
- Validated range: 2014-12-01 to 2017-06-25 (both-HIGH window per METHODOLOGY.md).
        """)

# ────────────────────────────────────────────────────────────────────────────
# Tab 4 — Signal Table (single-date inspector)
# ────────────────────────────────────────────────────────────────────────────
with tab4:
    st.subheader("Single-date signal packet")
    st.caption(
        "The full FundamentalSignals output for one date — all five sub-signals with "
        "raw values, percentile ranks, and confidence labels. "
        "Uses the PIT path (ALFRED vintage for historical dates; live sources for dates "
        "after the SAMADB capture boundary)."
    )

    if run_inspect:
        with st.spinner(f"Computing signal at {inspect_date}…"):
            sig = api.get_signal("fundamentals", "SA", inspect_date)

        if sig is None:
            st.warning(
                f"No signal available at {inspect_date}. "
                "This date may be before the FRED data starts (~2013) or "
                "the database may not be populated."
            )
        else:
            sigs = sig["signals"]
            st.subheader(f"SA Macro — {inspect_date}")

            cpi_src = sigs.get("cpi_source", "unknown")
            repo_src = sigs.get("repo_source", "unknown")
            boundary = sigs.get("cpi_boundary", "unknown")
            region_badge = "⚡ LIVE region" if boundary == "live" else "📦 Vintage region"
            st.info(
                f"{region_badge} · CPI: {SOURCE_LABEL.get(cpi_src, cpi_src)} · "
                f"Repo: {SOURCE_LABEL.get(repo_src, repo_src)}",
                icon="📡" if boundary == "live" else "🗄️",
            )

            sub_labels = {
                "real_policy_rate": ("Real Policy Rate", "%", "repo − inflation YoY"),
                "real_long_yield":  ("Real 10Y Yield",   "%", "yield_10y − inflation YoY"),
                "curve_slope":      ("Curve Slope",      " pp", "yield_10y − repo"),
                "inflation_trend":  ("Inflation Trend",  " pp", "3-month Δ YoY"),
                "growth_backdrop":  ("GDP Growth",       "%", "World Bank annual"),
            }

            header_cols = st.columns([3, 2, 2, 2])
            header_cols[0].markdown("**Signal**")
            header_cols[1].markdown("**Raw value**")
            header_cols[2].markdown("**10-yr rank**")
            header_cols[3].markdown("**Confidence**")

            for key, (disp, unit, desc) in sub_labels.items():
                s = sigs.get(key, {})
                raw_v   = s.get("raw", 0)
                norm_v  = s.get("normalised")
                conf_d  = s.get("confidence", {})
                clabel  = conf_d.get("confidence_label", "LOW")
                stale   = conf_d.get("staleness_days", 0)

                row = st.columns([3, 2, 2, 2])
                row[0].markdown(f"**{disp}** _{desc}_")
                row[1].markdown(f"`{raw_v:.3f}{unit}`")
                row[2].markdown(
                    f"{norm_v:.0f}th pct" if norm_v is not None else "n/a"
                )
                row[3].markdown(
                    f"{conf_badge(clabel)}  \n"
                    f"<small style='color:#888'>{stale}d overdue</small>",
                    unsafe_allow_html=True,
                )
    else:
        st.info(
            "Select a date in the sidebar and click **Compute signal packet** to inspect "
            "the full fundamental signal output for that date."
        )

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(DISCLAIMER)
