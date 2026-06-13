import os
from dotenv import load_dotenv

load_dotenv()

FRED_API_KEY = os.getenv("FRED_API_KEY")
TRADING_ECONOMICS_KEY = os.getenv("TRADING_ECONOMICS_KEY")

DB_PATH = os.getenv("DB_PATH", "sa_macro.duckdb")

if not FRED_API_KEY:
    raise ValueError("Missing FRED_API_KEY in .env file")