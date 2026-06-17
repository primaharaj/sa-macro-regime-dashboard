"""
Shared UI helpers — colour system, confidence badges, display labels.
Import this in every page; never import streamlit here (no side effects).
"""
from datetime import date

# ── Confidence colour language (single source of truth) ──────────────────────
# 🟢 HIGH  🟡 MEDIUM  ⚫ LOW
# Used identically across Landing, Macro, Divergence Explorer, and About.
CONF_ICON = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "⚫"}

# Hex versions for Plotly traces / inline HTML
CONF_HEX = {"HIGH": "#27AE60", "MEDIUM": "#E67E22", "LOW": "#7F8C8D"}


def conf_badge(label: str) -> str:
    """'🟢 HIGH' — for st.markdown inline."""
    icon = CONF_ICON.get(label, "⚪")
    return f"{icon} **{label}**"


def conf_html(label: str) -> str:
    """Small coloured pill for st.markdown(unsafe_allow_html=True)."""
    color = CONF_HEX.get(label, "#7F8C8D")
    return (
        f'<span style="background:{color};color:#fff;padding:2px 8px;'
        f'border-radius:4px;font-size:0.8em;font-weight:700">{label}</span>'
    )


# ── Source attribution ────────────────────────────────────────────────────────
SOURCE_LABEL = {
    "cpi_samadb":  "SAMADB CPS00000 — live index",
    "cpi":         "FRED ALFRED CPALTT01ZAM657N — vintage MoM%",
    "repo_mpc":    "Manual MPC table — live",
    "repo_rate":   "FRED ALFRED IRSTCB01ZAM156N — frozen Dec 2023",
    "yield_10y":   "FRED ALFRED IRLTLT01ZAM156N",
    "samadb":      "SAMADB",
    "mpc":         "Manual MPC table",
    "fred":        "FRED ALFRED",
    "world_bank":  "World Bank",
}

INSTRUMENT_LABEL = {
    "usd_zar":        "USD/ZAR",
    "jse_alsi":       "JSE ALSI",
    "saf_equity_etf": "SAF Equity ETF (EZA)",
}

# ── Chart colours ─────────────────────────────────────────────────────────────
TECH_COLOR   = "#2196F3"   # blue
MACRO_COLOR  = "#FF9800"   # amber
DIV_COLOR    = "#9C27B0"   # purple
THRESH_COLOR = "#E53935"   # red
FLAG_FILL    = "rgba(229, 57, 53, 0.13)"
LIVE_FILL    = "rgba(255, 152, 0, 0.10)"
HIST_FILL    = "rgba(33, 150, 243, 0.06)"

# ── Date constants ────────────────────────────────────────────────────────────
VALIDATED_START = date(2014, 1, 1)
VALIDATED_END   = date(2017, 12, 31)
NENE_DATE       = date(2015, 12, 11)   # first full session after firing

# ── Disclaimer text ───────────────────────────────────────────────────────────
DISCLAIMER = (
    "**Not financial advice.** This is an analytical research tool. "
    "A divergence flag measures disagreement between price and macro — "
    "it does not predict direction, timing, or magnitude of any move."
)
