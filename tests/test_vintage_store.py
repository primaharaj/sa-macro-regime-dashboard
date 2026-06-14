import unittest
import pandas as pd
from datetime import datetime, date
from src.vintage_store import VintageStore, UNAVAILABLE
from src.config import INDICATOR_REGISTRY

class TestVintageStore(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        cls.store = VintageStore()

    def test_reconstruction_divergence(self):
        query = "SELECT canonical_name, observation_date FROM observations WHERE vintage_class = 'BACKFILLABLE' GROUP BY 1, 2 HAVING count(*) > 1 LIMIT 1"
        res = self.store.conn.execute(query).fetchone()
        if not res: self.skipTest("No revised observations found")
        
        name, obs_date = res
        vintages = self.store.conn.execute("SELECT as_of_date, value FROM observations WHERE canonical_name = ? AND observation_date = ? ORDER BY as_of_date", (name, obs_date)).fetchall()
        v1_date, v1_val = vintages[0]
        vn_date, vn_val = vintages[-1]
        
        self.assertEqual(self.store.get_pit(name, obs_date, v1_date), v1_val)
        self.assertEqual(self.store.get_pit(name, obs_date, vn_date), vn_val)

    def test_no_pre_capture_leakage(self):
        name = "gdp_growth"
        meta = self.store.conn.execute("SELECT first_capture_date FROM indicator_metadata WHERE canonical_name = ?", (name,)).fetchone()
        if meta:
            pre_date = date(meta[0].year - 1, 1, 1)
            self.assertEqual(self.store.get_pit(name, date(2020, 1, 1), pre_date), UNAVAILABLE)

    def test_single_source_invariant(self):
        bad_df = pd.DataFrame([{"canonical_name": "cpi", "source": "trading_economics", "observation_date": date(2023, 1, 1), "as_of_date": date(2023, 1, 1), "value": 5.5, "vintage_class": "BACKFILLABLE", "revision_id": None, "retrieved_at": datetime.now()}])
        with self.assertRaisesRegex(ValueError, "Invariant Violation"):
            self.store._upsert_observations(bad_df)
