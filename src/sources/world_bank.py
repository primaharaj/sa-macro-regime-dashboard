import pandas as pd
import requests
import logging

logger = logging.getLogger(__name__)

class WorldBankSource:
    """
    Connector for World Bank WDI data using direct JSON API.
    """
    
    SERIES = {
        "cpi": "FP.CPI.TOTL.ZG",
        "gdp_growth": "NY.GDP.MKTP.KD.ZG"
    }

    def fetch_series(self, series_id, start_date="2005-01-01"):
        actual_id = self.SERIES.get(series_id, series_id)
        start_year = pd.to_datetime(start_date).year
        
        url = f"https://api.worldbank.org/v2/country/ZA/indicator/{actual_id}"
        params = {
            "format": "json",
            "date": f"{start_year}:2026",
            "per_page": 1000
        }

        try:
            logger.info(f"Fetching World Bank series: {actual_id}")
            r = requests.get(url, params=params)
            r.raise_for_status()
            
            data = r.json()
            if len(data) < 2 or not data[1]:
                return pd.DataFrame()
                
            # Parse results
            records = []
            for item in data[1]:
                if item['value'] is not None:
                    records.append({
                        "date": item['date'],
                        "value": float(item['value'])
                    })
            
            if not records:
                return pd.DataFrame()
                
            df = pd.DataFrame(records)
            df['date'] = pd.to_datetime(df['date'], format='%Y')
            df = df.set_index('date')
            
            return df.sort_index()
            
        except Exception as e:
            logger.error(f"Error fetching from World Bank: {e}")
            return pd.DataFrame()
