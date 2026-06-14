# Methodology

## 1. CPI & Inflation Derivation
Empirical analysis confirms that the canonical `cpi` series (sourced from FRED-OECD) is a **Monthly Growth Rate (%)**, not an index level. 

### YoY Calculation
To derive the annual inflation rate (`inflation_yoy`), we compound the 12 most recent monthly prints:
$$YoY = \left( \prod_{i=1}^{12} (1 + \frac{MoM_i}{100}) \right) - 1$$

**Validation (Feb 2024)**:
- **Calculated**: 5.55%
- **Official StatsSA Print**: 5.6%
- **Status**: Validated within rounding precision.

## 2. Confidence Metrics
Signals carry an explicit confidence label based on two dimensions:

### Sufficiency
- Number of data points in the normalization window (e.g., 252 days for technicals, 24 months for macro).
- Threshold: $<50\%$ capacity = LOW, $<80\%$ = MEDIUM.

### Staleness (Overdue-based)
Unlike "time since last data," we measure **time past the expected next release**.
- **Rule**: $overdue\_days = \max(0, today - (observation\_date + frequency + lag))$.
- This eliminates the "monthly flicker" where a signal would drop to MEDIUM just before a new release. A signal remains HIGH as long as the current print is the latest one expected.

## 3. The Both-HIGH Window
The high-fidelity historical foundation for this project is anchored in the contiguous span where both Macro-Fundamental and Technical families are simultaneously at HIGH confidence.

- **Optimal Range**: **2014-12-01 to 2017-06-25**
- **Rationale**: This window satisfies the 10-year macro normalization requirement while maintaining timely data releases from primary sources.

## 4. FRED vs. SARB Boundary
The current implementation uses FRED-OECD as the primary source for historical backfill because of its native ALFRED vintage API. However, FRED has a structural lag of 4-6 months for South African indicators. Direct integration with SARB/StatsSA is used as a "Capture-on-Ingest" layer to resolve current-day staleness, while historical revisions are preserved via the FRED backbone.
