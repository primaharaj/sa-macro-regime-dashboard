import unittest
import pandas as pd
from datetime import date, datetime
from src.vintage_store import VintageStore, UNAVAILABLE


class TestLiveSources(unittest.TestCase):
    """
    Tests for live-edge identities (cpi_samadb, repo_mpc) and the resolver.

    Tests b and c (step-function logic, single-source guard) are pure
    logic/DB tests and always run.

    Tests a and d (SAMADB network fetch, get_macro live routing) require
    populate_live() to succeed and are skipped if SAMADB is unreachable.
    """

    @classmethod
    def setUpClass(cls):
        cls.store = VintageStore()
        cls.samadb_populated = False
        try:
            cls.store.populate_live()
            cls.samadb_populated = True
        except Exception as e:
            print(f"\n[TestLiveSources] populate_live() failed ({e}); "
                  f"network-dependent tests will skip.")

    # ------------------------------------------------------------------
    # (b) repo_mpc step-function — pure logic, no network needed
    # ------------------------------------------------------------------

    def test_repo_mpc_step_function(self):
        """Step function: 2026-04-01 → 6.75 (pre-hike); 2026-06-01 → 7.00 (post-hike)."""
        from src.sources.mpc_repo import MpcRepoSource
        src = MpcRepoSource()
        pre_hike = src.get_rate_as_of(date(2026, 4, 1))
        self.assertIsNotNone(pre_hike, "No MPC entry covers 2026-04-01")
        self.assertAlmostEqual(pre_hike, 6.75,
            msg=f"Expected 6.75 pre-hike, got {pre_hike}")

        post_hike = src.get_rate_as_of(date(2026, 6, 1))
        self.assertIsNotNone(post_hike, "No MPC entry covers 2026-06-01")
        self.assertAlmostEqual(post_hike, 7.00,
            msg=f"Expected 7.00 post-hike, got {post_hike}")

    # ------------------------------------------------------------------
    # (c) Single-source guard for new source names writing to canonical IDs
    # ------------------------------------------------------------------

    def test_single_source_guard_new_sources(self):
        """samadb → canonical cpi and mpc → canonical repo_rate must raise."""
        bad_cpi = pd.DataFrame([{
            "canonical_name": "cpi",
            "source": "samadb",
            "observation_date": date(2024, 1, 1),
            "as_of_date": date(2024, 1, 1),
            "value": 5.5,
            "vintage_class": "BACKFILLABLE",
            "revision_id": None,
            "retrieved_at": datetime.now()
        }])
        with self.assertRaisesRegex(ValueError, "Invariant Violation"):
            self.store._upsert_observations(bad_cpi)

        bad_repo = pd.DataFrame([{
            "canonical_name": "repo_rate",
            "source": "mpc",
            "observation_date": date(2026, 1, 1),
            "as_of_date": date(2026, 1, 1),
            "value": 7.0,
            "vintage_class": "BACKFILLABLE",
            "revision_id": None,
            "retrieved_at": datetime.now()
        }])
        with self.assertRaisesRegex(ValueError, "Invariant Violation"):
            self.store._upsert_observations(bad_repo)

    # ------------------------------------------------------------------
    # (a) cpi_samadb index-level YoY derivation — needs SAMADB network
    # ------------------------------------------------------------------

    def test_cpi_samadb_yoy_derivation(self):
        """CPS00000 treated as index level; Feb 2024 YoY ≈ 5.60% (StatsSA verified)."""
        if not self.samadb_populated:
            self.skipTest("SAMADB unreachable — skipping live CPI test")

        from src.sources.samadb_source import SamadbSource
        src = SamadbSource()
        index_df = src.fetch_series()
        self.assertFalse(index_df.empty, "CPS00000 fetch returned empty DataFrame")

        # Guard: index values must look like index levels (~90–115), not % (~4–8)
        median_val = index_df["value"].median()
        self.assertGreater(median_val, 50,
            f"CPS00000 median={median_val:.2f} — looks like % not index level")

        # Derive YoY from the "value" column (Series)
        yoy = SamadbSource.derive_yoy(index_df["value"]).dropna()
        self.assertFalse(yoy.empty, "YoY series empty after derivation")

        feb2024 = pd.Timestamp("2024-02-01")
        self.assertIn(feb2024, yoy.index,
            f"Feb 2024 not in YoY index — earliest: {yoy.index[0].date()}")
        self.assertAlmostEqual(float(yoy[feb2024]), 5.60, delta=0.15,
            msg=f"Feb 2024 YoY = {yoy[feb2024]:.2f}%, expected ~5.60% (StatsSA)")

    # ------------------------------------------------------------------
    # (d) get_macro routing — live vs vintage boundary for cpi
    # ------------------------------------------------------------------

    def test_get_macro_routing_cpi(self):
        """get_macro(cpi) returns live cpi_samadb today, FRED vintage at 2016."""
        if not self.samadb_populated:
            self.skipTest("SAMADB unreachable — skipping resolver routing test")

        from src.resolver import get_macro

        today = date(2026, 6, 17)
        live = get_macro("cpi", today, self.store)
        self.assertEqual(live["source"], "cpi_samadb",
            f"Expected cpi_samadb at today, got {live['source']}")
        self.assertEqual(live["boundary"], "live")
        self.assertFalse(live["series"].empty, "cpi_samadb series empty at today")

        vintage = get_macro("cpi", date(2016, 1, 1), self.store)
        self.assertEqual(vintage["source"], "cpi",
            f"Expected FRED cpi at 2016-01-01, got {vintage['source']}")
        self.assertEqual(vintage["boundary"], "vintage")

    def test_get_macro_repo_live(self):
        """get_macro(repo) returns repo_mpc at today with rate 7.00."""
        if not self.samadb_populated:
            self.skipTest("SAMADB unreachable — skipping resolver routing test")

        from src.resolver import get_macro
        today = date(2026, 6, 17)
        pkt = get_macro("repo", today, self.store)
        self.assertEqual(pkt["source"], "repo_mpc")
        self.assertEqual(pkt["boundary"], "live")
        self.assertAlmostEqual(pkt["value"], 7.00,
            msg=f"Expected repo=7.00, got {pkt['value']}")

    def test_compute_real_policy_rate(self):
        """real_policy_rate from live inputs should be positive and < 5% given ~4% inflation."""
        if not self.samadb_populated:
            self.skipTest("SAMADB unreachable — skipping real policy rate test")

        from src.resolver import compute_real_policy_rate
        today = date(2026, 6, 17)
        result = compute_real_policy_rate(today, self.store)
        self.assertIsNotNone(result, "compute_real_policy_rate returned None")
        self.assertEqual(result["cpi_source"], "cpi_samadb")
        self.assertEqual(result["repo_source"], "repo_mpc")
        # real rate = repo (7.00) - inflation_yoy (~4%)
        # expect a positive real rate, bounded sanity check
        self.assertGreater(result["real_policy_rate"], 0,
            f"Real rate={result['real_policy_rate']:.2f}% — expected positive")
        self.assertLess(result["real_policy_rate"], 6.0,
            f"Real rate={result['real_policy_rate']:.2f}% — suspiciously high")
        print(f"\n[live macro] repo={result['repo_rate']}% "
              f"inflation_yoy={result['inflation_yoy']:.2f}% "
              f"real_policy_rate={result['real_policy_rate']:.2f}% "
              f"(cpi_obs={result['inflation_obs_date']})")
