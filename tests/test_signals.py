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
        # After live rewire: 2026-06-17 uses cpi_samadb (captured same day,
        # only 2 days overdue) + repo_mpc → freshness is HIGH, not LOW.
        as_of = date(2026, 6, 17)
        sig = self.api.get_signal("fundamentals", "SA", as_of)
        self.assertIsNotNone(sig, "Signal must be available at live-data date")
        conf = sig["signals"]["real_policy_rate"]["confidence"]
        self.assertIn(conf["confidence_label"], ["HIGH", "MEDIUM"],
            f"Expected HIGH/MEDIUM from live sources, got {conf['confidence_label']} "
            f"(staleness={conf['staleness_days']}d)")

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

    def test_live_rewire_boundary(self):
        """
        Dual assertion after FundamentalSignals was rewired to consume get_macro().

        (i)  At today's date the signal sources live cpi_samadb + repo_mpc
             and therefore confidence is HIGH/MEDIUM (not LOW from stale FRED data).

        (ii) At a 2016 date the signal still uses FRED vintages and is
             byte-identical before and after future-data truncation
             (no look-ahead introduced by the live rewire).
        """
        # (i) Live path — 2026-06-17 is post-capture-boundary for cpi_samadb
        today = date(2026, 6, 17)
        sig_live = self.api.get_signal("fundamentals", "SA", today)
        self.assertIsNotNone(sig_live, "Signal must be available at today's date with live sources")
        self.assertEqual(sig_live["signals"]["cpi_source"], "cpi_samadb",
            "Expected cpi_samadb at today — live path not active")
        conf_live = sig_live["signals"]["real_policy_rate"]["confidence"]
        self.assertIn(conf_live["confidence_label"], ["HIGH", "MEDIUM"],
            f"Live path gave {conf_live['confidence_label']}, staleness={conf_live['staleness_days']}d")

        # (ii) FRED vintage path — 2016-01-01 is pre-capture-boundary
        T = date(2016, 1, 1)
        sig_full = self.api.get_signal("fundamentals", "SA", T)
        self.assertIsNotNone(sig_full, f"FRED vintage signal missing at T={T}")
        self.assertEqual(sig_full["signals"]["cpi_source"], "cpi",
            "Expected FRED cpi at 2016 — live path should NOT be active")

        # No-look-ahead: truncate future data and recompute; raw must be identical
        self.store.conn.execute("BEGIN TRANSACTION")
        try:
            self.store.conn.execute(
                "DELETE FROM observations WHERE observation_date > ? OR as_of_date > ?",
                (T, T),
            )
            sig_trunc = self.api.get_signal("fundamentals", "SA", T)
            self.assertIsNotNone(sig_trunc, "Signal must still compute after truncation")
            self.assertEqual(
                sig_full["signals"]["real_policy_rate"]["raw"],
                sig_trunc["signals"]["real_policy_rate"]["raw"],
                "Look-ahead detected in FRED path after live rewire: "
                "signal changed when future data was removed",
            )
        finally:
            self.store.conn.execute("ROLLBACK")
