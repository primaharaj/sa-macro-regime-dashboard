"""
Macro Resolver — get_macro(concept, as_of_date, store)

Routes each macro concept to the best available identity in the VintageStore:

  cpi      → cpi_samadb  when as_of_date >= first_capture_date (live, index level)
             → cpi        when as_of_date <  first_capture_date (FRED ALFRED vintage, MoM %)
  repo     → repo_mpc    always (authoritative live; FRED repo_rate is legacy, frozen Dec 2023)
  yield_10y→ yield_10y   always (FRED IRLTLT01ZAM156N, current to ~Apr 2026)

Every returned packet declares `source` and `boundary` so callers know which
side of the live/vintage edge they are on.

YoY derivation helpers are also here because the correct formula differs by unit:
  index_level (cpi_samadb): (index_t / index_{t-12} - 1) * 100
  mom_pct    (canonical cpi): compound 12 monthly rates
"""

import numpy as np
import pandas as pd
import logging
from src.vintage_store import UNAVAILABLE

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# YoY helpers
# ---------------------------------------------------------------------------

def _yoy_from_index(series_df):
    """Index level → YoY %: (index_t / index_{t-12} - 1) * 100."""
    if series_df.empty:
        return pd.Series(dtype=float)
    s = series_df.set_index("date")["value"].sort_index()
    return (s / s.shift(12) - 1) * 100


def _yoy_from_mom(series_df):
    """MoM % → YoY %: compound 12 monthly rates."""
    if series_df.empty:
        return pd.Series(dtype=float)
    s = series_df.set_index("date")["value"].sort_index()
    decimal = s / 100.0
    return ((1 + decimal).rolling(12).apply(np.prod, raw=True) - 1) * 100


# ---------------------------------------------------------------------------
# Primary resolver
# ---------------------------------------------------------------------------

def get_macro(concept, as_of_date, store):
    """
    Return the best available macro packet for `concept` at `as_of_date`.

    Parameters
    ----------
    concept    : "cpi" | "repo" | "yield_10y"
    as_of_date : datetime.date
    store      : VintageStore

    Returns
    -------
    dict with at minimum: source, boundary
    For series concepts (cpi): also `series` (DataFrame[date, value]), `unit`
    For scalar concepts (repo, yield_10y): also `observation_date`, `value`
    """
    if concept == "cpi":
        first_capture = store.get_first_capture_date("cpi_samadb")
        if first_capture and as_of_date >= first_capture:
            series = store.get_series("cpi_samadb", as_of_date)
            logger.info(
                f"get_macro(cpi, {as_of_date}): live → cpi_samadb "
                f"[captured {first_capture}, {len(series)} obs]"
            )
            return {
                "source": "cpi_samadb",
                "boundary": "live",
                "unit": "index_level",
                "series": series,
                "first_capture": first_capture,
            }
        series = store.get_series("cpi", as_of_date)
        logger.info(
            f"get_macro(cpi, {as_of_date}): vintage → cpi (FRED ALFRED) "
            f"[{len(series)} obs, first_capture={first_capture}]"
        )
        return {
            "source": "cpi",
            "boundary": "vintage",
            "unit": "mom_pct",
            "series": series,
            "first_capture": first_capture,
        }

    if concept == "repo":
        obs = store.get_latest_known("repo_mpc", as_of_date)
        if obs != UNAVAILABLE:
            obs_date, value = obs
            logger.info(
                f"get_macro(repo, {as_of_date}): live → repo_mpc "
                f"[effective {obs_date}, rate={value}%]"
            )
            return {
                "source": "repo_mpc",
                "boundary": "live",
                "observation_date": obs_date,
                "value": float(value),
            }
        # Fallback to FRED legacy (frozen Dec 2023 at 8.25%)
        obs = store.get_latest_known("repo_rate", as_of_date)
        if obs != UNAVAILABLE:
            obs_date, value = obs
            logger.info(
                f"get_macro(repo, {as_of_date}): legacy → repo_rate (FRED, frozen Dec 2023) "
                f"[obs {obs_date}, rate={value}%]"
            )
            return {
                "source": "repo_rate",
                "boundary": "legacy",
                "observation_date": obs_date,
                "value": float(value),
            }
        return {"source": None, "boundary": None, "value": None}

    if concept == "yield_10y":
        obs = store.get_latest_known("yield_10y", as_of_date)
        if obs != UNAVAILABLE:
            obs_date, value = obs
            return {
                "source": "yield_10y",
                "boundary": "fred",
                "observation_date": obs_date,
                "value": float(value),
            }
        return {"source": None, "boundary": None, "value": None}

    raise ValueError(f"Unknown concept: {concept!r}. Valid: cpi, repo, yield_10y")


# ---------------------------------------------------------------------------
# Derived signal: real policy rate from live inputs
# ---------------------------------------------------------------------------

def compute_real_policy_rate(as_of_date, store):
    """
    Compute real policy rate using the best available live inputs.

    real_policy_rate = repo_rate - inflation_yoy

    YoY derivation is chosen automatically based on the cpi source:
      cpi_samadb (index_level) → index-ratio formula
      cpi        (mom_pct)     → 12-month compounding

    Returns dict or None if data insufficient.
    """
    cpi_packet = get_macro("cpi", as_of_date, store)
    repo_packet = get_macro("repo", as_of_date, store)

    series = cpi_packet.get("series", pd.DataFrame())
    if series is None or (hasattr(series, "empty") and series.empty):
        logger.warning("compute_real_policy_rate: cpi series empty")
        return None

    if cpi_packet["unit"] == "index_level":
        yoy = _yoy_from_index(series).dropna()
    else:
        yoy = _yoy_from_mom(series).dropna()

    if yoy.empty:
        logger.warning("compute_real_policy_rate: YoY series empty after derivation")
        return None

    current_inflation = float(yoy.iloc[-1])
    current_repo = repo_packet.get("value")
    if current_repo is None:
        logger.warning("compute_real_policy_rate: repo_rate unavailable")
        return None

    real_rate = current_repo - current_inflation

    return {
        "real_policy_rate": real_rate,
        "repo_rate": current_repo,
        "inflation_yoy": current_inflation,
        "inflation_obs_date": str(yoy.index[-1].date() if hasattr(yoy.index[-1], "date") else yoy.index[-1]),
        "cpi_source": cpi_packet["source"],
        "cpi_boundary": cpi_packet["boundary"],
        "repo_source": repo_packet["source"],
        "repo_boundary": repo_packet["boundary"],
        "as_of_date": str(as_of_date),
    }
