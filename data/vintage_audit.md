# Canonical Vintage Availability Audit

This audit reflects the reconciled indicator identities defined in `src/config.py`. Every economic concept is represented exactly once under its canonical name.

| canonical_name | concept | primary_source | vintage_class | earliest_vintage | revision_frequency | typical_lag |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **cpi** | Consumer Price Index (FRED-OECD Monthly) | FRED | BACKFILLABLE | 2013-06-03 | Monthly | ~69 days |
| **repo_rate** | SARB Policy Repo Rate (FRED-OECD) | FRED | BACKFILLABLE | 2013-06-03 | Monthly | ~41 days |
| **yield_10y** | SA 10-Year Government Bond Yield (FRED-OECD) | FRED | BACKFILLABLE | 2013-06-03 | Monthly | ~44 days |
| **cpi_annual** | Consumer Price Index (World Bank Annual) | World Bank | REVISED_NO_VINTAGE | n/a | Annual | ~1 year |
| **gdp_growth** | Annual GDP Growth Rate | World Bank | REVISED_NO_VINTAGE | n/a | Annual | ~1 year |
| **usd_zar** | USD/ZAR Exchange Rate | Yahoo Finance | NOT_REVISED | n/a | n/a | Real-time/1d |
| **jse_alsi** | JSE All Share Index | Yahoo Finance | NOT_REVISED | n/a | n/a | Real-time/1d |
| **saf_equity_etf** | MSCI South Africa ETF (EZA) | Yahoo Finance | NOT_REVISED | n/a | n/a | Real-time/1d |
| **sp500** | S&P 500 Index (SPY) | Yahoo Finance | NOT_REVISED | n/a | n/a | Real-time/1d |
| **us_10y** | US 10-Year Treasury Yield | Yahoo Finance | NOT_REVISED | n/a | n/a | Real-time/1d |

## Multi-Source Reconciliation & Primacy

| canonical_name | secondary_sources | primary_selection_rationale |
| :--- | :--- | :--- |
| **cpi** | TradingEconomics | **FRED-OECD** is primary due to historical vintage availability (ALFRED). World Bank CPI was split into a separate concept (`cpi_annual`) to avoid concept collision. |
| **repo_rate** | TradingEconomics | **FRED-OECD** is primary due to vintage availability. |
| **yield_10y** | TradingEconomics | **FRED-OECD** is primary due to vintage availability. |

## Classification Summary

### BACKFILLABLE
Indicators where historical revisions can be reconstructed using the ALFRED database.
- cpi
- repo_rate
- yield_10y

### REVISED_NO_VINTAGE
Economic statistics that are subject to revision, but for which the current API does not expose historical "as-of" states.
- cpi_annual
- gdp_growth
- *cpi_statssa_print* (RESERVED)

### NOT_REVISED
Financial market series where historical values are considered final once recorded.
- usd_zar
- jse_alsi
- saf_equity_etf
- sp500
- us_10y
