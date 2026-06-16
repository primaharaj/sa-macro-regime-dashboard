# Live Data Source Findings

- **SAMADB**: `pip install samadb` (PyPI), v0.3.0. CPI series `CPS00000` (`CPI_ANL_SERIES` dataset), INDEX LEVEL, base Dec 2024=100, current to Mar 2026. YoY = 12-month % change of index; verified 5.60% for Feb 2024 vs StatsSA. To be ingested as separate identity `cpi_samadb` (REVISED_NO_VINTAGE), own index->YoY derivation + own unit test, never written to canonical `cpi`.
- **SAMADB repo**: NO current policy rate. `KBP1401M` is legacy Bankrate, stale Oct 2023 (8.25). Repo live-source remains UNSOLVED in SAMADB.
- **OPEN**: Confirm whether FRED `IRSTCB01ZAM156N` is still frozen at Dec 2023 or has updated; if frozen, repo live edge = manual MPC table. Decide next session.
