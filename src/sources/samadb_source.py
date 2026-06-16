import pandas as pd
import logging

logger = logging.getLogger(__name__)

_SERIES_CODE = "CPS00000"


class SamadbSource:
    """
    Connector for SAMADB (Stellenbosch University / EconData).
    Fetches CPI index level series CPS00000 from the CPI_ANL_SERIES dataset.

    Unit: INDEX LEVEL, base Dec 2024 = 100.  NOT a % change series.
    YoY derivation: (index_t / index_{t-12} - 1) * 100  — see derive_yoy().
    This is intentionally different from canonical `cpi` (FRED CPALTT01ZAM657N),
    which is a MoM % change series compounded over 12 months.
    """

    def fetch_series(self, tfrom="2010-01-01"):
        """
        Returns a pandas DataFrame indexed by date (monthly) with a single
        column `value` containing CPS00000 index levels.

        Raises on network/auth failure — callers should catch and handle.
        """
        import samadb as sm

        # sm.data() returns a Polars DataFrame; wide=True (default) gives
        # columns [date, CPS00000].
        result = sm.data(series=_SERIES_CODE, tfrom=tfrom)
        df = result.to_pandas()
        df["date"] = pd.to_datetime(df["date"])
        df = df.rename(columns={_SERIES_CODE: "value"})
        df = df.set_index("date")[["value"]].sort_index().dropna(subset=["value"])
        logger.info(f"SAMADB {_SERIES_CODE}: fetched {len(df)} observations "
                    f"({df.index[0].date()} – {df.index[-1].date()})")
        return df

    @staticmethod
    def derive_yoy(index_series):
        """
        YoY inflation from index level: (index_t / index_{t-12} - 1) * 100.

        index_series: pandas Series with DatetimeIndex, monthly frequency,
                      values are index levels (base Dec 2024 = 100).
        Returns: Series of YoY % values (same index, NaN for first 12 obs).
        """
        return (index_series / index_series.shift(12) - 1) * 100
