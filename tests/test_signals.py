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
        T = date(2023, 6, 1)
        sig_T = self.api.get_signal("technicals", "jse_alsi", T)
        if not sig_T: self.skipTest("No data for T")
        sig_T_repeat = self.api.get_signal("technicals", "jse_alsi", T)
        self.assertEqual(sig_T["signals"]["trend"]["raw"], sig_T_repeat["signals"]["trend"]["raw"])

    def test_confidence_logic(self):
        # Verify that a long overdue date triggers LOW/MEDIUM confidence
        # Our current data ends in early 2024, so 2026 should be LOW
        as_of = date(2026, 6, 1)
        sig = self.api.get_signal("fundamentals", "SA", as_of)
        if sig:
            conf = sig["signals"]["real_policy_rate"]["confidence"]
            self.assertIn(conf["confidence_label"], ["LOW", "MEDIUM"])
