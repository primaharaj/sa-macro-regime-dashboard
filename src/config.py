import os
from dotenv import load_dotenv

load_dotenv()

FRED_API_KEY = os.getenv("FRED_API_KEY")
TRADING_ECONOMICS_KEY = os.getenv("TRADING_ECONOMICS_KEY")

DB_PATH = os.getenv("DB_PATH", "sa_macro.duckdb")

# --- INDICATOR REGISTRY ---
# Defines the canonical identity for every economic concept in the dashboard.
# vintage_class:
#   - BACKFILLABLE: ALFRED-backed (supports historical revisions)
#   - REVISED_NO_VINTAGE: Revised stat but no API-exposed revision history
#   - NOT_REVISED: Price/Index/Yield series (point-in-time remains constant)

INDICATOR_REGISTRY = {
    "usd_zar": {
        "canonical_name": "usd_zar",
        "concept": "USD/ZAR Exchange Rate",
        "sources": {"yahoo": "USDZAR=X"},
        "vintage_class": "NOT_REVISED",
        "primary_source": "yahoo",
        "native_frequency_days": 1,
        "typical_lag_days": 1
    },
    "jse_alsi": {
        "canonical_name": "jse_alsi",
        "concept": "JSE All Share Index",
        "sources": {"yahoo": "^J203.JO"},
        "vintage_class": "NOT_REVISED",
        "primary_source": "yahoo",
        "native_frequency_days": 1,
        "typical_lag_days": 1
    },
    "saf_equity_etf": {
        "canonical_name": "saf_equity_etf",
        "concept": "MSCI South Africa ETF (EZA)",
        "sources": {"yahoo": "EZA"},
        "vintage_class": "NOT_REVISED",
        "primary_source": "yahoo",
        "native_frequency_days": 1,
        "typical_lag_days": 1
    },
    "sp500": {
        "canonical_name": "sp500",
        "concept": "S&P 500 Index (SPY)",
        "sources": {"yahoo": "SPY"},
        "vintage_class": "NOT_REVISED",
        "primary_source": "yahoo",
        "native_frequency_days": 1,
        "typical_lag_days": 1
    },
    "us_10y": {
        "canonical_name": "us_10y",
        "concept": "US 10-Year Treasury Yield",
        "sources": {"yahoo": "^TNX"},
        "vintage_class": "NOT_REVISED",
        "primary_source": "yahoo",
        "native_frequency_days": 1,
        "typical_lag_days": 1
    },
    "cpi": {
        "canonical_name": "cpi",
        "concept": "Consumer Price Index (FRED-OECD Monthly)",
        "sources": {
            "fred": "CPALTT01ZAM657N",
            "trading_economics": "inflation rate"
        },
        "vintage_class": "BACKFILLABLE",
        "primary_source": "fred",
        "native_frequency_days": 31,
        "typical_lag_days": 75
    },
    "cpi_annual": {
        "canonical_name": "cpi_annual",
        "concept": "Consumer Price Index (World Bank Annual)",
        "sources": {"world_bank": "FP.CPI.TOTL.ZG"},
        "vintage_class": "REVISED_NO_VINTAGE",
        "primary_source": "world_bank",
        "native_frequency_days": 365,
        "typical_lag_days": 365
    },
    "repo_rate": {
        "canonical_name": "repo_rate",
        "concept": "SARB Policy Repo Rate (FRED-OECD)",
        "sources": {
            "fred": "IRSTCB01ZAM156N",
            "trading_economics": "interest rate"
        },
        "vintage_class": "BACKFILLABLE",
        "primary_source": "fred",
        "native_frequency_days": 31,
        "typical_lag_days": 75
    },
    "yield_10y": {
        "canonical_name": "yield_10y",
        "concept": "SA 10-Year Government Bond Yield (FRED-OECD)",
        "sources": {
            "fred": "IRLTLT01ZAM156N",
            "trading_economics": "government bond 10y"
        },
        "vintage_class": "BACKFILLABLE",
        "primary_source": "fred",
        "native_frequency_days": 31,
        "typical_lag_days": 75
    },
    "gdp_growth": {
        "canonical_name": "gdp_growth",
        "concept": "Annual GDP Growth Rate",
        "sources": {"world_bank": "NY.GDP.MKTP.KD.ZG"},
        "vintage_class": "REVISED_NO_VINTAGE",
        "primary_source": "world_bank",
        "native_frequency_days": 365,
        "typical_lag_days": 365
    }
}

# RESERVED NAMESPACES (For Future Use):
# - cpi_statssa_print: (REVISED_NO_VINTAGE) Direct ingestion of StatsSA headline CPI releases.