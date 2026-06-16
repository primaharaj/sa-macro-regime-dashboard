import unittest
import pandas as pd
from datetime import date
from src.vintage_store import VintageStore
from src.signals.api import SignalAPI

class TestSignals(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        cls.store = VintageStore()
        cls.api = SignalAPI(cls.store)

    def test_truncation_leak(self):
        """
        Proof of No-Look-Ahead:
        Captures a signal at T, then physically deletes all rows from the database 
        where observation_date > T or as_of_date > T. 
        The recomputed signal at T must be identical.
        Uses a transaction to ensure the deletion is non-destructive to the suite.
        """
        T = date(2016, 1, 1)
        
        # 1. Capture signal with full knowledge
        sig_full = self.api.get_signal("fundamentals", "SA", T)
        self.assertIsNotNone(sig_full, f"Data missing for T={T} in validated window.")

        # 2. Destructive Truncation within a transaction
        self.store.conn.execute("BEGIN TRANSACTION")
        try:
            # 3. VERIFY FUTURE DATA EXISTS BEFORE DELETION
            future_count = self.store.conn.execute(
                "SELECT COUNT(*) FROM observations WHERE observation_date > ? OR as_of_date > ?", 
                (T, T)
            ).fetchone()[0]
            self.assertGreater(future_count, 0, f"Test is trivial: No data exists after T={T} to truncate.")

            # 4. TRUNCATE FUTURE DATA (Observation and Vintage)
            self.store.conn.execute("DELETE FROM observations WHERE observation_date > ? OR as_of_date > ?", (T, T))

            # 5. Recompute at T
            sig_truncated = self.api.get_signal("fundamentals", "SA", T)

            # 6. Assert Identity
            self.assertEqual(
                sig_full["signals"]["real_policy_rate"]["raw"], 
                sig_truncated["signals"]["real_policy_rate"]["raw"],
                "Look-ahead detected: Signal changed after future data was deleted."
            )
        finally:

            # 6. ROLLBACK to restore the database for other tests
            self.store.conn.execute("ROLLBACK")

    def test_confidence_logic(self):
        # Verify that a long overdue date triggers LOW/MEDIUM confidence
        # Our current data ends in early 2024, so 2026 should be LOW
        as_of = date(2026, 6, 1)
        sig = self.api.get_signal("fundamentals", "SA", as_of)
        if sig:
            conf = sig["signals"]["real_policy_rate"]["confidence"]
            self.assertIn(conf["confidence_label"], ["LOW", "MEDIUM"])

    def test_cpi_derivation(self):
        """
        Guards CPI derivation logic:
        (a) Treated as monthly %, not index
        (b) Feb 2024 Inflation YoY ~ 5.55%
        (c) Real Policy Rate is sane
        """
        as_of = date(2024, 5, 1)
        sig = self.api.get_signal("fundamentals", "SA", as_of)
        self.assertIsNotNone(sig, "Signal should be available for Feb 2024 as-of May 2024")
        
        # Back out inflation: real_policy = repo - inflation
        df_repo = self.store.get_series("repo_rate", as_of)
        repo_val = df_repo['value'].iloc[-1]
        real_policy = sig["signals"]["real_policy_rate"]["raw"]
        inf_yoy = repo_val - real_policy
        
        # (b) Assert inflation_yoy ~ 5.55% (matches StatsSA 5.6% headline)
        self.assertAlmostEqual(inf_yoy, 5.55, delta=0.1)
        
        # (c) Real policy rate sane sign and range
        self.assertGreater(real_policy, 0)
        self.assertLess(real_policy, 5.0)
