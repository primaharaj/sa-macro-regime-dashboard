import pandas as pd
import requests
import os
import logging

logger = logging.getLogger(__name__)

class FREDSource:
    """
    Modular connector for FRED API.
    """
    
    def __init__(self):
        self.api_key = os.getenv("FRED_API_KEY")
        if not self.api_key:
            raise ValueError("Missing FRED_API_KEY in .env file")

    def fetch_series(self, series_id, start="2005-01-01"):
        url = "https://api.stlouisfed.org/fred/series/observations"

        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "observation_start": start
        }

        try:
            logger.info(f"Fetching FRED series: {series_id}")
            r = requests.get(url, params=params)
            r.raise_for_status()

            data = r.json()["observations"]
            df = pd.DataFrame(data)
            df["date"] = pd.to_datetime(df["date"])
            df["value"] = pd.to_numeric(df["value"], errors="coerce")

            return df.set_index("date")[["value"]]
        except Exception as e:
            logger.error(f"Error fetching from FRED: {e}")
            return pd.DataFrame()
