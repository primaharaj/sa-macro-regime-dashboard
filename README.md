# SA Macro Regime Dashboard

A senior analytical tool for monitoring and backtesting South African macroeconomic regimes with strict **Point-in-Time (PIT)** discipline.

## Mission
To provide a high-fidelity intelligence layer for South African macro-financial analysis, ensuring that historical regimes are reconstructed exactly as they were knowable to market participants at the time.

## Scope & Status
- **Current Foundation (v0.1)**: Validated data infrastructure, PIT vintage store, and signal family generation (Technicals & Fundamentals).
- **High-Fidelity Window**: **2014-12-01 to 2017-06-25**. This is the primary contiguous span where both macro and technical signals maintain "HIGH" confidence.
- **Divergence Detection**: Pending (Phase 3).
- **Live Macro**: Currently limited by FRED-OECD publication lags (4-6 months). Integration with SARB/StatsSA direct feeds is planned.

## The Point-in-Time Approach
Unlike standard dashboards that use revised "final" historical data, this project utilizes a **Vintage Store**. 
- **Backfillable (FRED/ALFRED)**: Reconstructs the exact value known on any date T, even if it was revised later.
- **Capture-on-Ingest**: For sources without native vintage APIs, we version data at the moment of ingestion.
- **Leak-Free**: All signals and normalization use only data dated $\le T$.

## Non-Goals
- **Financial Advice**: This tool is for institutional/analytical research purposes only.
- **Day Trading**: Not designed for sub-daily execution or high-frequency trading.
- **Real-time News**: Focused on structural macro trends, not event-driven headline scraping.

## Getting Started
1. Clone the repo.
2. Install dependencies: `pip install -r requirements.txt`.
3. Set `FRED_API_KEY` in your environment.
4. Run `python -m src.vintage_store` to populate the local DuckDB.
5. Launch the dashboard: `streamlit run app.py`.

---
*Disclaimer: Not financial advice. Past performance of macro regimes does not guarantee future market returns.*
