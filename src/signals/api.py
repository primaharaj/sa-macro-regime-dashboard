from src.signals.technicals import TechnicalSignals
from src.signals.fundamentals import FundamentalSignals
from src.vintage_store import VintageStore

class SignalAPI:
    def __init__(self, store=None):
        self.store = store or VintageStore()
        self.technicals = TechnicalSignals(self.store)
        self.fundamentals = FundamentalSignals(self.store)

    def get_signal(self, family, name, as_of_date):
        """
        Retrieves a signal from the requested family.
        """
        if family == "technicals":
            res = self.technicals.compute(name, as_of_date)
            if not res: return None
            # Standardize output structure
            return {
                "family": family,
                "name": name,
                "as_of_date": as_of_date,
                "signals": res, # Contains raw, normalised, confidence for each sub-signal
                "underlying_as_of_date": res["underlying_as_of_date"]
            }
        
        if family == "fundamentals":
            res = self.fundamentals.compute(as_of_date)
            if not res: return None
            return {
                "family": family,
                "name": "SA",
                "as_of_date": as_of_date,
                "signals": res,
                "underlying_as_of_date": res["underlying_as_of_date"]
            }
            
        return None
