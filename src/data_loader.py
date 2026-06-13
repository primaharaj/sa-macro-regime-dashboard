import os
import duckdb
import pandas as pd
import yfinance as yf
import logging
from dotenv import load_dotenv

from src.sources.fred import FREDSource
from src.sources.world_bank import WorldBankSource
from src.sources.trading_economics import TradingEconomicsSource

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)
logging.getLogger("yfinance").setLevel(logging.WARNING)


class DataLoader:
    """
    South African Macro Regime Dashboard - Multi-Source Data Layer
    """

    DB_PATH = "data/macro_data.db"

    MARKET_SERIES = {
        "usd_zar": "USDZAR=X",
        "jse_alsi": "^J203.JO",
        "saf_equity_etf": "EZA",
        "sp500": "SPY",
        "us_10y": "^TNX"
    }

    # Configuration for Multi-Source
    # Priority: TradingEconomics > FRED > World Bank
    MACRO_CONFIG = {
        "cpi": {
            "trading_economics": "inflation rate",
            "fred": "CPALTT01ZAM657N",
            "world_bank": "FP.CPI.TOTL.ZG"
        },
        "repo_rate": {
            "trading_economics": "interest rate",
            "fred": "IRSTCB01ZAM156N"
        },
        "yield_10y": {
            "trading_economics": "government bond 10y",
            "fred": "IRLTLT01ZAM156N"
        }
    }

    def __init__(self):
        os.makedirs(os.path.dirname(self.DB_PATH), exist_ok=True)
        self.conn = duckdb.connect(self.DB_PATH)
        
        # Initialize sources
        self.fred = FREDSource()
        self.wb = WorldBankSource()
        self.te = TradingEconomicsSource()
        
        # Track provenance
        self.provenance = {}

    def fetch_macro_series(self, name, start_date="2005-01-01"):
        config = self.MACRO_CONFIG.get(name)
        if not config:
            return pd.DataFrame()

        # 1. Try Trading Economics (if key exists)
        if self.te.api_key and self.te.api_key != "GUEST:GUEST" and "trading_economics" in config:
            df = self.te.fetch_series(config["trading_economics"])
            if not df.empty:
                self.provenance[name] = "TradingEconomics"
                return df

        # 2. Try FRED
        if "fred" in config:
            df = self.fred.fetch_series(config["fred"], start=start_date)
            if not df.empty:
                self.provenance[name] = "FRED"
                return df

        # 3. Try World Bank
        if "world_bank" in config:
            df = self.wb.fetch_series(config["world_bank"], start_date=start_date)
            if not df.empty:
                self.provenance[name] = "World Bank"
                return df

        logger.warning(f"Could not fetch data for {name} from any source.")
        return pd.DataFrame()

    def fetch_market_data(self, period="10y"):
        logger.info("Fetching market data...")
        frames = []
        for name, ticker in self.MARKET_SERIES.items():
            df = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=True)
            if df is None or df.empty:
                logger.warning(f"No data for {ticker}")
                continue
            col = "Close" if "Close" in df.columns else df.columns[0]
            df = df[[col]]
            df.columns = [name]
            frames.append(df)
        if not frames:
            raise ValueError("No market data fetched")
        
        df_market = pd.concat(frames, axis=1).ffill(limit=2)
        
        # Global Relative Strength: JSE ALSI / S&P 500
        if "jse_alsi" in df_market.columns and "sp500" in df_market.columns:
            df_market["jse_relative_strength"] = df_market["jse_alsi"] / df_market["sp500"]
            
        return df_market

    def fetch_macro_data(self, start_date="2005-01-01"):
        logger.info("Fetching aggregated macro data from multiple sources...")
        frames = []
        for name in self.MACRO_CONFIG.keys():
            df = self.fetch_macro_series(name, start_date=start_date)
            if not df.empty:
                df.columns = [name]
                df = df.resample("D").ffill(limit=31)
                frames.append(df)
        
        if not frames:
            return pd.DataFrame()
            
        df_macro = pd.concat(frames, axis=1)
        
        # SA Yield Curve Slope: 10Y - Repo (Proxy for Term Premium/Growth Expectations)
        if "yield_10y" in df_macro.columns and "repo_rate" in df_macro.columns:
            df_macro["sa_yield_slope"] = df_macro["yield_10y"] - df_macro["repo_rate"]
            
        return df_macro

    def update_database(self):
        logger.info("Updating DuckDB database with multi-source data...")
        market = self.fetch_market_data()
        macro = self.fetch_macro_data()

        df = market.join(macro, how="left")
        df.index.name = "date"
        df = df.reset_index()

        self.conn.execute("CREATE OR REPLACE TABLE macro_series AS SELECT * FROM df")
        
        # Save provenance info
        prov_df = pd.DataFrame(list(self.provenance.items()), columns=['indicator', 'source'])
        self.conn.execute("CREATE OR REPLACE TABLE data_provenance AS SELECT * FROM prov_df")

        logger.info(f"Database updated: {len(df)} rows")

    def load_from_db(self):
        return self.conn.execute("SELECT * FROM macro_series ORDER BY date").df()
        
    def get_provenance(self):
        try:
            return self.conn.execute("SELECT * FROM data_provenance").df()
        except:
            return pd.DataFrame()


def load_fred(series_id, table_name):
    loader = DataLoader()
    df = loader.fred.fetch_series(series_id)
    df = df.reset_index()
    loader.conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM df")
