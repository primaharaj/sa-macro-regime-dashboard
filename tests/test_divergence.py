import unittest
from datetime import date
from src.vintage_store import VintageStore
from src.signals.api import SignalAPI
from src.divergence import DivergenceDetector


class TestDivergence(unittest.TestCase):
    """
    Acceptance tests for the divergence detector.

    All tests run against the pre-populated DB (as_of_date = call date).
    Tests A, B, D are anchored in the 2014–2017 both-HIGH window where
    FRED macro data and Yahoo price data are both present and well-behaved.
    """

    @classmethod
    def setUpClass(cls):
        cls.store = VintageStore()
        cls.api   = SignalAPI(cls.store)
        cls.det   = DivergenceDetector(cls.api)

    # ─────────────────────────────────────────────────────────────────────
    # A. DIVERGENCE FIRES — Dec 2015 Nene shock on usd_zar
    # ─────────────────────────────────────────────────────────────────────
    def test_nene_shock_fires(self):
        """
        Dec 9–11 2015: USDZAR spiked ~13% in three days (Nene firing — political
        narrative shock). Monthly SA macro (real rates, inflation, growth) had NOT
        moved on that timescale; weekly stats simply don't revise monthly series.

        Expectation:
          - detector flags a divergence (percentile >= 80th)
          - outlier_family == 'technicals'  (price spiked, macro didn't)
          - tech_posture is notably elevated (> 60)
          - prints the real numbers for inspection
        """
        # Dec 11 is the first full trading session after the Nene firing (Dec 9 evening).
        # By Dec 16 the market had already partially normalised; Dec 11 is the peak.
        T = date(2015, 12, 11)
        pkt = self.det.compute("usd_zar", T)
        self.assertIsNotNone(pkt, f"No divergence packet returned at {T}")

        print(
            f"\n[Nene shock Dec-2015 usd_zar]"
            f"\n  tech_posture   = {pkt['tech_posture']:.2f}"
            f"\n  macro_posture  = {pkt['macro_posture']:.2f}"
            f"\n  divergence     = {pkt['divergence']:.2f}"
            f"\n  abs_divergence = {pkt['abs_divergence']:.2f}"
            f"\n  percentile     = {pkt['percentile']:.1f}th"
            f"\n  flagged        = {pkt['flagged']}"
            f"\n  outlier_family = {pkt['outlier_family']}"
            f"\n  confidence     = {pkt['confidence']}"
        )

        self.assertTrue(
            pkt["flagged"],
            f"Nene shock MUST flag (percentile={pkt['percentile']:.1f}, "
            f"tech={pkt['tech_posture']:.1f}, macro={pkt['macro_posture']:.1f}). "
            f"If this fails, the detector does not work."
        )
        self.assertEqual(
            pkt["outlier_family"], "technicals",
            f"Outlier must be 'technicals': price spiked, macro data is monthly "
            f"and could not have moved across a 3-day political shock. "
            f"Got: {pkt['outlier_family']}"
        )
        # Tech posture should be elevated: USDZAR was well above its 252-day MA
        self.assertGreater(
            pkt["tech_posture"], 60,
            f"tech_posture={pkt['tech_posture']:.1f} — price spike not captured"
        )

    # ─────────────────────────────────────────────────────────────────────
    # B. DETECTOR STAYS QUIET — calm August 2016 control period
    # ─────────────────────────────────────────────────────────────────────
    def test_quiet_aug_2016_no_flag(self):
        """
        August 2016: USDZAR was rangebound (~14–15) after the Dec-2015/Jan-2016
        extremes normalised. No sharp idiosyncratic move; SA macro (repo at 7%,
        CPI ~6%, growth ~0.5%) was stable. The detector must NOT flag here —
        proving it discriminates between genuine divergences and normal volatility.

        Why Aug 2016 qualifies as a control:
          - USDZAR 21-day momentum near zero (sideways market)
          - 252-day MA elevated from the shock; price near or below MA by Aug 2016
          - The Dec-2015 spike in the trailing 756-day window raises the 80th pct
            threshold, making a false flag here even less likely
        """
        T = date(2016, 8, 1)
        pkt = self.det.compute("usd_zar", T)
        self.assertIsNotNone(pkt, f"No divergence packet at {T}")

        print(
            f"\n[Quiet period Aug-2016 usd_zar]"
            f"\n  tech_posture  = {pkt['tech_posture']:.2f}"
            f"\n  macro_posture = {pkt['macro_posture']:.2f}"
            f"\n  divergence    = {pkt['divergence']:.2f}"
            f"\n  percentile    = {pkt['percentile']:.1f}th"
            f"\n  flagged       = {pkt['flagged']}"
        )

        self.assertFalse(
            pkt["flagged"],
            f"Aug 2016 must NOT flag (stable period): "
            f"percentile={pkt['percentile']:.1f}, "
            f"tech={pkt['tech_posture']:.1f}, macro={pkt['macro_posture']:.1f}"
        )

    # ─────────────────────────────────────────────────────────────────────
    # C. CONFIDENCE PROPAGATION — stale macro → LOW confidence, non-actionable
    # ─────────────────────────────────────────────────────────────────────
    def test_low_confidence_propagates(self):
        """
        At date(2027, 1, 1) all macro data is many months stale (SA CPI latest
        release in store is ~early 2026; by Jan 2027, overdue_days >> 20).
        The divergence packet must carry confidence='LOW' and actionable=False,
        regardless of how large the posture gap is. A flag built on stale data
        is non-actionable by design.
        """
        T = date(2027, 1, 1)
        pkt = self.det.compute("usd_zar", T)
        if pkt is None:
            self.skipTest(f"Insufficient data at {T} — cannot run confidence propagation test")

        self.assertEqual(
            pkt["confidence"], "LOW",
            f"Expected LOW confidence at stale date {T}, "
            f"got {pkt['confidence']} "
            f"(tech_conf={pkt['tech_confidence']}, macro_conf={pkt['macro_confidence']})"
        )
        self.assertFalse(
            pkt["actionable"],
            "A LOW-confidence divergence must NOT be marked actionable"
        )

    # ─────────────────────────────────────────────────────────────────────
    # D. PIT SURVIVAL — truncate future rows, recompute, assert identical
    # ─────────────────────────────────────────────────────────────────────
    def test_pit_survival(self):
        """
        Compute divergence at date(2016, 1, 15) with the full DB. Then, within a
        transaction, delete all rows where observation_date > T OR as_of_date > T.
        Recompute. The result must be numerically identical.

        Also asserts > 0 rows were deleted (so the test is not hollow).
        The no-look-ahead property must survive into the divergence layer.
        """
        T = date(2016, 1, 15)

        pkt_full = self.det.compute("usd_zar", T)
        self.assertIsNotNone(pkt_full, f"No divergence packet at {T} (full DB)")

        self.store.conn.execute("BEGIN TRANSACTION")
        try:
            future_count = self.store.conn.execute(
                "SELECT COUNT(*) FROM observations "
                "WHERE observation_date > ? OR as_of_date > ?",
                (T, T),
            ).fetchone()[0]
            self.assertGreater(
                future_count, 0,
                f"Test is hollow: no future rows in DB after T={T}"
            )

            self.store.conn.execute(
                "DELETE FROM observations WHERE observation_date > ? OR as_of_date > ?",
                (T, T),
            )

            pkt_trunc = self.det.compute("usd_zar", T)
            self.assertIsNotNone(pkt_trunc,
                "Divergence must still compute after future-data truncation")

            self.assertAlmostEqual(
                pkt_full["divergence"], pkt_trunc["divergence"], places=10,
                msg="Look-ahead detected: divergence changed after future data deleted"
            )
            self.assertAlmostEqual(
                pkt_full["tech_posture"], pkt_trunc["tech_posture"], places=10,
                msg="tech_posture changed after future data deleted"
            )
            self.assertAlmostEqual(
                pkt_full["macro_posture"], pkt_trunc["macro_posture"], places=10,
                msg="macro_posture changed after future data deleted"
            )
        finally:
            self.store.conn.execute("ROLLBACK")
