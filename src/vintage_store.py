import os
import duckdb
import pandas as pd
import requests
import logging
import yfinance as yf
from datetime import datetime
from src.config import INDICATOR_REGISTRY, FRED_API_KEY, DB_PATH

logger = logging.getLogger(__name__)

UNAVAILABLE = "UNAVAILABLE"

class VintageStore:
    """
    Point-in-Time Vintage Store for Macroeconomic and Market Data.
    """

    def __init__(self, db_path=None):
        self.db_path = db_path or "data/macro_data.db"
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = duckdb.connect(self.db_path)
        self._init_db()

    def _init_db(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS observations (
                canonical_name TEXT,
                source TEXT,
                observation_date DATE,
                as_of_date DATE,
                value DOUBLE,
                vintage_class TEXT,
                revision_id TEXT,
                retrieved_at TIMESTAMP,
                PRIMARY KEY (canonical_name, observation_date, as_of_date)
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS indicator_metadata (
                canonical_name TEXT PRIMARY KEY,
                first_capture_date DATE
            )
        """)

    def populate(self):
        """
        Populates the vintage store based on the INDICATOR_REGISTRY.
        """
        for key, config in INDICATOR_REGISTRY.items():
            logger.info(f"Populating vintage store for: {key}")
            vc = config["vintage_class"]
            
            if vc == "BACKFILLABLE":
                self._populate_backfillable(key, config)
            elif vc == "NOT_REVISED":
                self._populate_not_revised(key, config)
            elif vc == "REVISED_NO_VINTAGE":
                self._populate_revised_no_vintage(key, config)

    def _upsert_observations(self, df):
        """
        Helper to upsert observations while enforcing source primacy for BACKFILLABLE series.
        """
        if df.empty:
            return

        for _, row in df.iterrows():
            canonical_name = row["canonical_name"]
            source = row["source"].lower()
            config = INDICATOR_REGISTRY.get(canonical_name)
            
            if not config:
                continue
                
            if config["vintage_class"] == "BACKFILLABLE":
                primary = config["primary_source"].lower()
                if source != primary:
                    raise ValueError(
                        f"Invariant Violation: Cannot write {source} data to BACKFILLABLE "
                        f"indicator '{canonical_name}'. Primary source is '{primary}'."
                    )
        
        self.conn.execute("INSERT OR IGNORE INTO observations SELECT * FROM df")

    def _populate_backfillable(self, key, config):
        if config["primary_source"] == "fred":
            series_id = config["sources"]["fred"]
            # Fetch ALL vintages from FRED
            url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={FRED_API_KEY}&file_type=json&realtime_start=1776-07-04"
            r = requests.get(url)
            r.raise_for_status()
            obs = r.json().get("observations", [])
            
            rows = []
            now = datetime.now()
            for o in obs:
                rows.append({
                    "canonical_name": key,
                    "source": "fred", # use config-aligned lowercase
                    "observation_date": o["date"],
                    "as_of_date": o["realtime_start"],
                    "value": pd.to_numeric(o["value"], errors="coerce"),
                    "vintage_class": "BACKFILLABLE",
                    "revision_id": None,
                    "retrieved_at": now
                })
            
            df = pd.DataFrame(rows).dropna(subset=["value"])
            self._upsert_observations(df)

    def _populate_not_revised(self, key, config):
        if config["primary_source"] == "yahoo":
            ticker = config["sources"]["yahoo"]
            df = yf.download(ticker, period="max", interval="1d", progress=False, auto_adjust=True)
            if df.empty: return
            
            col = "Close" if "Close" in df.columns else df.columns[0]
            df = df[[col]].reset_index()
            df.columns = ["observation_date", "value"]
            
            now = datetime.now()
            df["canonical_name"] = key
            df["source"] = "yahoo"
            df["as_of_date"] = df["observation_date"]
            df["vintage_class"] = "NOT_REVISED"
            df["revision_id"] = None
            df["retrieved_at"] = now
            
            # Ensure correct column order for DuckDB insert
            df = df[["canonical_name", "source", "observation_date", "as_of_date", "value", "vintage_class", "revision_id", "retrieved_at"]]
            self._upsert_observations(df)

    def _populate_revised_no_vintage(self, key, config):
        source_type = config["primary_source"]
        df = pd.DataFrame()

        if source_type == "world_bank":
            from src.sources.world_bank import WorldBankSource
            wb = WorldBankSource()
            df = wb.fetch_series(config["sources"]["world_bank"])

        elif source_type == "samadb":
            from src.sources.samadb_source import SamadbSource
            src = SamadbSource()
            df = src.fetch_series()

        elif source_type == "mpc":
            from src.sources.mpc_repo import MpcRepoSource
            src = MpcRepoSource()
            df = src.get_dataframe()

        if not df.empty:
            now = datetime.now()
            today = now.date()
            df = df.reset_index()
            df.columns = ["observation_date", "value"]
            df["canonical_name"] = key
            df["source"] = source_type
            df["as_of_date"] = today
            df["vintage_class"] = "REVISED_NO_VINTAGE"
            df["revision_id"] = None
            df["retrieved_at"] = now
            
            df = df[["canonical_name", "source", "observation_date", "as_of_date", "value", "vintage_class", "revision_id", "retrieved_at"]]
            self._upsert_observations(df)
            
            # Track first capture
            self.conn.execute("""
                INSERT OR IGNORE INTO indicator_metadata (canonical_name, first_capture_date)
                VALUES (?, ?)
            """, (key, today))

    def populate_live(self):
        """Populate only the live-edge identities (cpi_samadb, repo_mpc).

        Safe to call repeatedly — INSERT OR IGNORE prevents duplicates.
        Raises if a source is unreachable (caller decides whether to skip).
        """
        for key in ("cpi_samadb", "repo_mpc"):
            config = INDICATOR_REGISTRY.get(key)
            if config:
                logger.info(f"populate_live: refreshing {key}")
                self._populate_revised_no_vintage(key, config)

    def get_first_capture_date(self, canonical_name):
        """Return first_capture_date for canonical_name, or None if not yet captured."""
        meta = self.conn.execute(
            "SELECT first_capture_date FROM indicator_metadata WHERE canonical_name = ?",
            (canonical_name,)
        ).fetchone()
        return meta[0] if meta else None

    def get_pit(self, canonical_name, observation_date, as_of_date):
        """
        Retrieves the point-in-time value for an indicator.
        """
        config = INDICATOR_REGISTRY.get(canonical_name)
        if not config: return UNAVAILABLE
        
        vc = config["vintage_class"]
        
        if vc == "NOT_REVISED":
            # Cannot know a close before it closes
            if observation_date > as_of_date:
                return UNAVAILABLE
            query = """
                SELECT value FROM observations 
                WHERE canonical_name = ? AND observation_date = ?
            """
            res = self.conn.execute(query, (canonical_name, observation_date)).fetchone()
            return res[0] if res else UNAVAILABLE

        if vc == "BACKFILLABLE":
            query = """
                SELECT value FROM observations 
                WHERE canonical_name = ? AND observation_date = ? AND as_of_date <= ?
                ORDER BY as_of_date DESC LIMIT 1
            """
            res = self.conn.execute(query, (canonical_name, observation_date, as_of_date)).fetchone()
            return res[0] if res else UNAVAILABLE

        if vc == "REVISED_NO_VINTAGE":
            # Check first capture date
            meta = self.conn.execute("SELECT first_capture_date FROM indicator_metadata WHERE canonical_name = ?", (canonical_name,)).fetchone()
            if not meta or as_of_date < meta[0]:
                return UNAVAILABLE
            
            query = """
                SELECT value FROM observations 
                WHERE canonical_name = ? AND observation_date = ? AND as_of_date <= ?
                ORDER BY as_of_date DESC LIMIT 1
            """
            res = self.conn.execute(query, (canonical_name, observation_date, as_of_date)).fetchone()
            return res[0] if res else UNAVAILABLE
            
        return UNAVAILABLE

    def get_latest_known(self, canonical_name, as_of_date):
        """
        Retrieves the most recent observation known at a specific as_of_date.
        """
        config = INDICATOR_REGISTRY.get(canonical_name)
        if not config: return UNAVAILABLE
        
        vc = config["vintage_class"]
        
        if vc == "NOT_REVISED":
            query = """
                SELECT observation_date, value FROM observations 
                WHERE canonical_name = ? AND observation_date <= ?
                ORDER BY observation_date DESC LIMIT 1
            """
            res = self.conn.execute(query, (canonical_name, as_of_date)).fetchone()
            return (res[0], res[1]) if res else UNAVAILABLE

        if vc == "BACKFILLABLE":
            query = """
                SELECT observation_date, value FROM observations 
                WHERE canonical_name = ? AND as_of_date <= ?
                ORDER BY observation_date DESC, as_of_date DESC LIMIT 1
            """
            res = self.conn.execute(query, (canonical_name, as_of_date)).fetchone()
            return (res[0], res[1]) if res else UNAVAILABLE

        if vc == "REVISED_NO_VINTAGE":
            meta = self.conn.execute("SELECT first_capture_date FROM indicator_metadata WHERE canonical_name = ?", (canonical_name,)).fetchone()
            if not meta or as_of_date < meta[0]:
                return UNAVAILABLE
            
            query = """
                SELECT observation_date, value FROM observations 
                WHERE canonical_name = ? AND as_of_date <= ?
                ORDER BY observation_date DESC, as_of_date DESC LIMIT 1
            """
            res = self.conn.execute(query, (canonical_name, as_of_date)).fetchone()
            return (res[0], res[1]) if res else UNAVAILABLE

        return UNAVAILABLE

    def get_series(self, canonical_name, as_of_date, start_date=None, end_date=None):
        """
        Retrieves a time series of values as they were known at a specific as_of_date.
        """
        config = INDICATOR_REGISTRY.get(canonical_name)
        if not config: return pd.DataFrame()
        
        vc = config["vintage_class"]
        
        if vc == "NOT_REVISED":
            query = """
                SELECT observation_date as date, value FROM observations 
                WHERE canonical_name = ? AND observation_date <= ?
            """
            params = [canonical_name, as_of_date]
            if start_date:
                query += " AND observation_date >= ?"
                params.append(start_date)
            if end_date:
                query += " AND observation_date <= ?"
                params.append(end_date)
            query += " ORDER BY observation_date"
            return self.conn.execute(query, params).df()

        if vc == "BACKFILLABLE" or vc == "REVISED_NO_VINTAGE":
            # For each observation_date, get the latest value known as of as_of_date
            query = """
                WITH latest_vintages AS (
                    SELECT observation_date, value,
                           ROW_NUMBER() OVER (PARTITION BY observation_date ORDER BY as_of_date DESC) as rn
                    FROM observations
                    WHERE canonical_name = ? AND as_of_date <= ?
                )
                SELECT observation_date as date, value FROM latest_vintages WHERE rn = 1
            """
            params = [canonical_name, as_of_date]
            if start_date:
                query += " AND observation_date >= ?"
                params.append(start_date)
            if end_date:
                query += " AND observation_date <= ?"
                params.append(end_date)
            
            # If REVISED_NO_VINTAGE, check first_capture_date
            if vc == "REVISED_NO_VINTAGE":
                meta = self.conn.execute("SELECT first_capture_date FROM indicator_metadata WHERE canonical_name = ?", (canonical_name,)).fetchone()
                if not meta or as_of_date < meta[0]:
                    return pd.DataFrame()

            query += " ORDER BY observation_date"
            return self.conn.execute(query, params).df()

        return pd.DataFrame()
