import pandas as pd
import requests
import os
import logging

logger = logging.getLogger(__name__)

class TradingEconomicsSource:
    """
    Connector for TradingEconomics API.
    """
    
    def __init__(self):
        self.api_key = os.getenv("TRADING_ECONOMICS_KEY")
        self.base_url = "https://api.tradingeconomics.com"

    def fetch_series(self, indicator, country="south africa"):
        if not self.api_key or self.api_key == "GUEST:GUEST":
            # Limited guest access or no key
            logger.warning("No TradingEconomics API key. Using guest access if possible.")
            key = "guest:guest"
        else:
            key = self.api_key

        try:
            url = f"{self.base_url}/historical/country/{country}/indicator/{indicator}?c={key}&format=json"
            
            logger.info(f"Fetching TradingEconomics: {indicator} for {country}")
            r = requests.get(url)
            r.raise_for_status()
            
            data = r.json()
            if not data:
                return pd.DataFrame()
                
            df = pd.DataFrame(data)
            df['DateTime'] = pd.to_datetime(df['DateTime'])
            df = df.rename(columns={'DateTime': 'date', 'Value': 'value'})
            df = df.set_index('date')[['value']]
            
            return df.sort_index()
            
        except Exception as e:
            logger.error(f"Error fetching from TradingEconomics: {e}")
            return pd.DataFrame()
