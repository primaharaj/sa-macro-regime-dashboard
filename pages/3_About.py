"""
About / How to read this — plain-language guide to the SA Macro Monitor.

This page is the manual's Section 1 (what this is), Section 7 (responsible
interpretation), and Section 8 (limitations) in UI form.
"""
import streamlit as st
from src.ui import DISCLAIMER, VALIDATED_START, VALIDATED_END

st.set_page_config(page_title="About — SA Macro Monitor", layout="wide")

st.title("About — SA Macro Monitor")
st.caption(
    "How to read this tool, what it does not do, and what you should know "
    "before acting on any of its outputs."
)

# ── What this is ─────────────────────────────────────────────────────────────
st.header("What this is")
st.markdown("""
The SA Macro Regime & Divergence Engine is a research tool that monitors South African
macroeconomic conditions and compares them against the technical posture (price trend and
momentum) of SA-related instruments.

Its purpose is to surface situations where **price is doing something that the macro backdrop
does not justify — or vice versa**. This disagreement is what the Divergence Explorer measures.

The tool gives you:
- A current snapshot of the SA macro backdrop, each reading labelled with its data quality.
- A historical view of SA macro series so you can see how the environment has evolved.
- A divergence detector that flags when price and macro are unusually far apart.
""")

# ── What this does NOT do — the fence ─────────────────────────────────────────
st.header("What this does NOT do", divider="red")
st.error(
    "This section is the most important part of this page. Read it before using any output.",
    icon="🚫",
)
st.markdown("""
**It does not predict whether a trade will make money.**
A divergence flag says that price and macro disagree. It does not say which one is wrong,
when they will converge, or in what direction.

**It does not cover assets outside the configured instrument list.**
The three divergence targets are USD/ZAR (primary), JSE ALSI (primary), and SAF Equity ETF /
EZA (secondary, USD-muddied). There are no signals for any other instruments.

**It does not make recommendations.**
No output from this tool should be read as "buy" or "sell". It surfaces disagreements and
lets you investigate them.

**Historical regime descriptions are not forecasts.**
Showing that a particular macro environment was associated with a particular market outcome
in 2014–2017 does not mean the same association holds in any future period.

**A flag alone is not actionable.**
A flag is only marked actionable when confidence is HIGH or MEDIUM. A LOW-confidence flag
is non-actionable by design — the gap may reflect data quality, not market reality.

**This is not financial advice.**
This tool is for institutional or analytical research only. Past macro regime behaviour
does not guarantee future market returns.
""")

# ── How to read confidence ─────────────────────────────────────────────────────
st.header("How to read confidence labels")
st.markdown("""
Every number on this dashboard shows a confidence label. These are not decorative.

| Label | Meaning |
|---|---|
| 🟢 HIGH | Data is sufficient and current. Use this reading. |
| 🟡 MEDIUM | Data is slightly stale or the normalisation window is short. Use with caution. |
| ⚫ LOW | Data is stale or the history is too short. Do not act on this reading. |

**Staleness is measured as days past the expected next release**, not days since the last
observation. A monthly indicator with a 75-day publication lag will stay HIGH for about
85 days after the last observation (the full month + lag window), then drop to MEDIUM as
it becomes overdue.

Confidence for the divergence packet = `min(tech_confidence, macro_confidence)`.
If either input is LOW, the packet is LOW and non-actionable.
""")

# ── Live vs historical ─────────────────────────────────────────────────────────
st.header("Live data vs historical data")
st.markdown("""
The dashboard uses two data regimes, and they look different by design.

**Historical region (before the dashed line):** All data is read from FRED ALFRED,
which stores multiple vintages of each series. You see the value that was *known at the time*,
not a revised version. This is the Point-in-Time (PIT) guarantee.

**Live region (after the dashed line):** CPI is sourced from SAMADB (index level,
base Dec 2024=100); repo is from a manually maintained MPC decision table.
These sources have no vintage history — if the underlying data is revised, the
stored value is overwritten. The live region is less historically validated.

**The live boundary** is the date the SAMADB CPI was first captured.
""")

# ── Validated window ───────────────────────────────────────────────────────────
st.header("Validated window")
st.markdown(f"""
The period where both macro and technical signals are confirmed simultaneously at HIGH
confidence is **{VALIDATED_START.strftime("%d %b %Y")} to {VALIDATED_END.strftime("%d %b %Y")}**.

The Divergence Explorer defaults to this window. The Dec 2015 Nene shock
(Finance Minister firing on the evening of 9 Dec 2015) falls within this window and
is the primary validated reference case for the divergence detector:

- 2015-12-11 (first full trading session after the firing):
  tech_posture ≈ 99.2, macro_posture ≈ 45.3, divergence ≈ 53.9, percentile ≈ 84.5 → **flagged**
- outlier_family = `technicals` — price spiked; monthly macro data did not revise

Outside this window, interpret signals with care and check the confidence labels.
""")

# ── Known limitations ──────────────────────────────────────────────────────────
st.header("Known limitations")

with st.expander("FRED ALFRED coverage starts ~2013 for SA series"):
    st.markdown("""
ALFRED's `realtime_start` parameter requests all historical vintages.
However, FRED's SA coverage has gaps before 2013. Signals computed before 2013 may have
sparse normalisation histories and will carry MEDIUM or LOW confidence.
    """)

with st.expander("FRED CPI data anomaly around 2023"):
    st.markdown("""
The FRED CPI series (`CPALTT01ZAM657N`) shows an implausible real policy rate near 2023-01-01
(approximately −6.86%, which is impossible given actual SA repo rates at the time).
The suspected cause is a StatsSA 2022 CPI rebasing (base 2016→2021) that created a
discontinuity in the FRED/OECD series. This anomaly has not been corrected.
Avoid using CPI-derived signals for 2022–2024 on the FRED vintage path without verification.
    """)

with st.expander("Repo rate gap: Dec 2023 to Nov 2025"):
    st.markdown("""
FRED `repo_rate` (ALFRED) is frozen at December 2023 (8.25%).
The manual MPC table covers decisions from November 2025 onwards.
Between December 2023 and November 2025, the fallback is the frozen FRED value (8.25%),
which was **not** the actual SARB repo rate through that period (rates were cut during 2024–2025).
Any divergence computed with `as_of_date` in this gap will have an incorrect repo input.
    """)

with st.expander("SAMADB and MPC table have no vintage history"):
    st.markdown("""
Both `cpi_samadb` (SAMADB) and `repo_mpc` (manual MPC table) are stamped with the
date of the ingest call, not the original publication date.
- You cannot reconstruct what these sources looked like as of a specific past date.
- Any StatsSA revision overwrites the stored CPI value silently on the next refresh.
- The MPC table must be updated manually within one business day of each announcement.
    """)

with st.expander("GDP (World Bank) has no vintage history"):
    st.markdown("""
GDP growth is annual (World Bank) with no vintage API.
The stored value reflects the most recent World Bank revision, not what was available at
any specific past date. GDP staleness at historical dates before the first populate call
will show `staleness_days = 999`, and the divergence engine excludes this from the
confidence minimum (to avoid it dragging all historical packets to LOW).
    """)

with st.expander("Divergence series chart vs single-date packet may differ"):
    st.markdown("""
The posture time series chart uses a vectorised approximation of the macro posture
(`_macro_posture_series` in `src/divergence.py`). The single-date "packet" uses the
precise PIT path through SignalAPI. These can produce different macro_posture values
for the same date because the normalisation windows and data paths differ.

The single-date packet is authoritative. The chart is useful for overview and trend
but is not a point-exact reconstruction of what the detector would have produced
at each date in the past.
    """)

# ── Quick start ────────────────────────────────────────────────────────────────
st.header("Quick start")
st.code("""
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set FRED API key (free — register at https://fred.stlouisfed.org/)
export FRED_API_KEY=your_key_here   # Windows: set FRED_API_KEY=...

# 3. Populate the local DuckDB (FRED, Yahoo Finance, World Bank)
python -m src.vintage_store

# 4. Populate live data (SAMADB CPI + manual MPC table)
python -c "from src.vintage_store import VintageStore; VintageStore().populate_live()"

# 5. Launch the dashboard
streamlit run app.py
""", language="bash")

st.markdown("""
**Refreshing live data**: the SAMADB CPI is not fetched automatically on each run.
Use the **Refresh live sources** button on the landing page, or call `store.populate_live()`.
The MPC repo table (`src/sources/mpc_repo.py`) must be edited manually after each
SARB announcement.
""")

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(DISCLAIMER)
