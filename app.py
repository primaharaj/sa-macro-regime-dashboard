"""
Landing / "Now" view — current SA macro snapshot + live divergence flags.

This is the hook: a first-time user sees what the engine measures right now,
with every reading labelled by its confidence and data source.
"""
import streamlit as st
from datetime import date

from src.vintage_store import VintageStore
from src.signals.api import SignalAPI
from src.divergence import DivergenceDetector
from src.resolver import get_macro
from src.ui import (
    conf_badge, SOURCE_LABEL, INSTRUMENT_LABEL,
    CONF_HEX, DISCLAIMER,
)

st.set_page_config(
    page_title="SA Macro Monitor",
    page_icon="🇿🇦",
    layout="wide",
)

# ── Shared objects (cached across pages via st.cache_resource) ────────────────
@st.cache_resource
def _load():
    store = VintageStore()
    api   = SignalAPI(store)
    det   = DivergenceDetector(api)
    return store, api, det

store, api, det = _load()
TODAY = date.today()

# ── Header ────────────────────────────────────────────────────────────────────
st.title("🇿🇦 SA Macro Monitor")
st.caption(
    f"SA macro backdrop as of **{TODAY}** — analytical research tool · "
    "not financial advice · signals measure, they do not predict"
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Navigation")
    st.page_link("app.py",                         label="Now — live snapshot",      icon="🏠")
    st.page_link("pages/1_Macro.py",               label="Macro — historical view",  icon="📈")
    st.page_link("pages/2_Divergence_Explorer.py", label="Divergence Explorer",      icon="🔍")
    st.page_link("pages/3_About.py",               label="About / How to read this", icon="📖")
    st.divider()

    st.subheader("Refresh live data")
    st.caption(
        "Live CPI (SAMADB) and repo (MPC table) are not fetched automatically. "
        "Click to pull the latest."
    )
    if st.button("🔄 Refresh live sources"):
        with st.spinner("Fetching SAMADB CPI and re-reading MPC table…"):
            try:
                store.populate_live()
                st.cache_resource.clear()
                st.success("Live data refreshed.")
                st.rerun()
            except Exception as exc:
                st.error(f"Refresh failed: {exc}")

# ── Live data status banner ───────────────────────────────────────────────────
first_capture = store.get_first_capture_date("cpi_samadb")
if first_capture and TODAY >= first_capture:
    st.info(
        f"⚡ **Live mode active** — CPI source: SAMADB (first captured {first_capture}); "
        "repo source: manual MPC table (current 7.00%, effective 2026-05-29); "
        "yield: FRED ALFRED (last available ≈ Apr 2026).",
        icon="📡",
    )
else:
    st.warning(
        "Live data not yet captured. Run `store.populate_live()` or use the sidebar button. "
        "Displaying FRED vintage data only.",
    )

# ── Fetch signals ─────────────────────────────────────────────────────────────
sig = api.get_signal("fundamentals", "SA", TODAY)

if sig is None:
    st.error(
        "Fundamental signals unavailable for today. "
        "The database may not be populated — run `python -m src.vintage_store` "
        "then `store.populate_live()` and reload."
    )
    st.stop()

sigs            = sig["signals"]
repo_pkt        = get_macro("repo", TODAY, store)
yield_pkt       = get_macro("yield_10y", TODAY, store)
repo_val        = float(repo_pkt.get("value") or 0.0)
real_policy_r   = sigs["real_policy_rate"]["raw"]
inflation_yoy   = repo_val - real_policy_r
underlying_date = str(sigs.get("underlying_as_of_date", ""))[:10]

# ── Main layout ───────────────────────────────────────────────────────────────
left, right = st.columns([6, 4], gap="large")

# ════════════════════════════════════════════════════════════════════════════════
# LEFT — Macro Snapshot
# ════════════════════════════════════════════════════════════════════════════════
with left:
    st.subheader("SA Macro — Current Readings")
    cpi_source_label = SOURCE_LABEL.get(sigs.get("cpi_source", ""), sigs.get("cpi_source", ""))
    repo_source_label = SOURCE_LABEL.get(sigs.get("repo_source", ""), sigs.get("repo_source", ""))
    st.caption(
        f"CPI observation: **{underlying_date}** · {cpi_source_label} · "
        f"Repo: {repo_source_label}"
    )

    def _row(display_label, raw_val, unit, norm_val, conf_dict, source_note=None):
        """Render one signal row with confidence badge."""
        clabel = conf_dict.get("confidence_label", "LOW") if conf_dict else "LOW"
        stale  = conf_dict.get("staleness_days", 0) if conf_dict else 0
        c1, c2, c3 = st.columns([3, 2, 2])
        c1.metric(display_label, f"{raw_val:.2f}{unit}")
        if norm_val is not None:
            c2.metric("10-yr rank", f"{norm_val:.0f}th pct")
        else:
            c2.caption("not ranked")
        stale_note = f" ⚠️ {stale}d overdue" if stale > 10 else f" {stale}d overdue"
        c3.markdown(
            f"{conf_badge(clabel)}<br>"
            f"<small style='color:#888'>{stale_note}</small>",
            unsafe_allow_html=True,
        )
        if source_note:
            st.caption(source_note)
        st.write("")   # small spacer

    # ── Inflation (YoY, derived) ──────────────────────────────────────────────
    # Inherits CPI sub-signal confidence (same overdue_days as real_policy_rate)
    cpi_conf = sigs["real_policy_rate"]["confidence"]
    _row("SA Inflation (YoY)", inflation_yoy, "%",
         None, cpi_conf,
         f"Derived: repo − real_policy_rate · {cpi_source_label}")

    # ── Repo Rate (scalar) ────────────────────────────────────────────────────
    repo_obs_date = repo_pkt.get("observation_date")
    repo_stale = (TODAY - repo_obs_date).days if repo_obs_date else 0
    repo_clabel = "HIGH" if repo_stale <= 60 else "MEDIUM" if repo_stale <= 120 else "LOW"
    c1, c2, c3 = st.columns([3, 2, 2])
    c1.metric("SARB Repo Rate", f"{repo_val:.2f}%")
    c2.metric("Effective", str(repo_obs_date or "unknown"))
    c3.markdown(
        f"{conf_badge(repo_clabel)}<br>"
        f"<small style='color:#888'>{repo_stale}d since change</small>",
        unsafe_allow_html=True,
    )
    st.caption(f"{repo_source_label}")
    st.write("")

    # ── Real Policy Rate ──────────────────────────────────────────────────────
    rpr = sigs["real_policy_rate"]
    _row("Real Policy Rate (Repo − Inflation)", rpr["raw"], "%",
         rpr["normalised"], rpr["confidence"],
         "High = tight / hawkish. Low = easy / dovish.")

    # ── 10-Year Yield ─────────────────────────────────────────────────────────
    yield_val      = float(yield_pkt.get("value") or 0.0)
    yield_obs_date = yield_pkt.get("observation_date")
    yield_stale    = (TODAY - yield_obs_date).days if yield_obs_date else 0
    # real_long_yield normalised is the yield-10yr normed (through the same path)
    rly = sigs["real_long_yield"]
    _row("SA 10-Year Bond Yield", yield_val, "%",
         None, rly["confidence"],
         f"FRED ALFRED IRLTLT01ZAM156N · last obs {yield_obs_date} "
         f"({'⚠️ ' if yield_stale > 75 else ''}{yield_stale} days ago)")

    # ── Curve Slope ───────────────────────────────────────────────────────────
    cs = sigs["curve_slope"]
    _row("Yield Curve Slope (10Y − Repo)", cs["raw"], " pp",
         cs["normalised"], cs["confidence"],
         "Positive = upward-sloping. Negative = inverted.")

    # ── Inflation Trend ───────────────────────────────────────────────────────
    it = sigs["inflation_trend"]
    _row("Inflation Trend (3-month Δ YoY)", it["raw"], " pp",
         it["normalised"], it["confidence"],
         "Positive = accelerating. Negative = decelerating.")

    # ── GDP Growth ────────────────────────────────────────────────────────────
    gb = sigs["growth_backdrop"]
    gb_clabel = gb["confidence"].get("confidence_label", "LOW")
    _row("SA GDP Growth (annual)", gb["raw"], "%",
         gb["normalised"], gb["confidence"],
         "World Bank annual — no vintage history. Confidence is MEDIUM/LOW by design.")

    # ── Methodology expander ──────────────────────────────────────────────────
    with st.expander("Show signal methodology"):
        st.markdown("""
#### Fundamental sub-signals

| Signal | Formula | Source |
|---|---|---|
| Inflation YoY | `(index_t / index_{t−12} − 1) × 100` (SAMADB) or compound MoM% (FRED) | SAMADB / FRED ALFRED |
| Repo Rate | Step function of MPC decisions | Manual MPC table |
| Real Policy Rate | `repo − inflation_yoy` | Derived |
| Yield 10Y | Market level | FRED ALFRED IRLTLT01ZAM156N |
| Curve Slope | `yield_10y − repo_rate` | Derived |
| Inflation Trend | `inflation_yoy.diff(3)` | Derived |
| GDP Growth | Annual WB release, forward-filled | World Bank NY.GDP.MKTP.KD.ZG |

**10-year rank (normalised)**: percentile of the current reading within its own 10-year trailing
history. 50th = median. Computed as `(history < current).mean() × 100`, excludes the current
point from the comparison.

**Confidence** = `min(sufficiency, staleness)` where staleness is days past the *expected next
release*, not days since the last observation. A signal stays HIGH until the next expected
release date has passed by more than the indicator's lag threshold.
        """)

# ════════════════════════════════════════════════════════════════════════════════
# RIGHT — Divergence Flags
# ════════════════════════════════════════════════════════════════════════════════
with right:
    st.subheader("Divergence Flags — Today")
    st.caption(
        "A flag fires when the absolute gap between tech posture and macro posture "
        "exceeds the 80th percentile of the past year's distribution. "
        "LOW confidence = non-actionable regardless of gap size."
    )

    for instr in ["usd_zar", "jse_alsi"]:
        label = INSTRUMENT_LABEL[instr]
        pkt = det.compute(instr, TODAY)

        if pkt is None:
            st.warning(f"**{label}**: insufficient data.")
            continue

        conf_l    = pkt["confidence"]
        flagged   = pkt["flagged"]
        actionable = pkt["actionable"]

        if flagged and actionable:
            border = CONF_HEX["HIGH"]
            icon   = "🚩"
            status = "FLAGGED"
        elif flagged:
            border = CONF_HEX["MEDIUM"]
            icon   = "🚩"
            status = "FLAGGED — non-actionable (LOW confidence)"
        else:
            border = "#90A4AE"
            icon   = "✅"
            status = "No flag"

        st.markdown(
            f'<div style="border-left:4px solid {border};padding:6px 12px;'
            f'margin-bottom:4px;background:#f9f9f9;border-radius:3px">'
            f'<b>{icon} {label}</b> — {status}'
            f'</div>',
            unsafe_allow_html=True,
        )

        c1, c2 = st.columns(2)
        c1.metric("Tech posture",  f"{pkt['tech_posture']:.1f}")
        c2.metric("Macro posture", f"{pkt['macro_posture']:.1f}")
        c1.metric("Divergence",    f"{pkt['divergence']:.1f}")
        c2.metric("Percentile",    f"{pkt['percentile']:.0f}th")
        st.markdown(
            f"Confidence: {conf_badge(conf_l)} &nbsp;|&nbsp; "
            f"Outlier family: **{pkt['outlier_family']}**",
            unsafe_allow_html=True,
        )
        if conf_l == "LOW":
            st.caption(
                "⚫ LOW confidence — data quality is insufficient to act on this reading. "
                "Check source freshness in the Macro view."
            )
        elif flagged:
            st.caption(
                "Open the Divergence Explorer for the full packet, historical context, "
                "and the Dec 2015 Nene shock as a validated reference case."
            )
        st.divider()

    # Orientation reminder
    with st.expander("How to read USDZAR macro posture"):
        st.markdown("""
**macro_posture HIGH for USDZAR = macro justifies ZAR weakness** (high USDZAR price).

- `growth_backdrop` (−): low SA growth → ZAR weak → high USDZAR supported
- `real_policy_rate` (−): low real rate → less hawkish → ZAR weak
- `inflation_trend` (+): rising inflation → ZAR erodes

A hawkish/high-real-rate backdrop is ZAR-supportive → argues for *lower* USDZAR →
**LOW** macro_posture for USDZAR. If this sign were reversed, every ZAR divergence
conclusion would be backwards.
        """)

    with st.expander("Divergence methodology"):
        st.markdown("""
**tech_posture** = `mean(rolling_pct(trend, 252), rolling_pct(momentum, 252))`
where `rolling_pct` ranks the current value within the trailing 252-day window.

**macro_posture** = signed mean of normalised sub-signals (direction per instrument).

**Flagging**: `|divergence| > 80th percentile of trailing 252-day |divergence|`

**Confidence** = `min(tech_confidence, macro_confidence)`.
Actionable only if confidence is HIGH or MEDIUM and the flag is firing.
        """)

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(DISCLAIMER)
