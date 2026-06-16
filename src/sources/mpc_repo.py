"""
SARB Monetary Policy Committee (MPC) Repo Rate — Manual Table.

MAINTENANCE INSTRUCTIONS
------------------------
This file is the authoritative live source for the SARB policy repo rate.
Update it within one business day of each MPC announcement (~6 meetings/year).
No automated feed is currently current: FRED IRSTCB01ZAM156N is frozen at
Dec 2023 (8.25%) and SAMADB KBP1401M is stale at Oct 2023 (8.25%).

Each entry: (decision_date, effective_date, action, rate_pct)
  decision_date  — date governor announced the decision
  effective_date — date the new rate took effect (typically decision_date + 1)
  action         — "hike" | "cut" | "hold"
  rate_pct       — repo rate in effect FROM effective_date onwards

Sources for current entries:
  2025-11 cut    : per Jan 2026 SAnews hold note ("after a 25 bps rate cut in Nov")
  2026-01-29 hold: SAnews / TradingEconomics confirmed Jan 29, 2026 hold at 6.75%
  2026-03-26 hold: Engineering News / TradingEconomics — unanimous hold, Iran risk cited
  2026-05-28 hike: SAnews, Daily Maverick, Jacaranda FM — 4-2 vote, +25 bps to 7.00%

Next scheduled MPC meeting: ~23 July 2026.
"""

from datetime import date
import pandas as pd

# (decision_date, effective_date, action, rate_pct)
# Ordered chronologically; effective_date is the date the rate took hold.
# NOTE: 2025-11 effective date is estimated (±1 week); verify if backfill precision matters.
MPC_DECISIONS = [
    (date(2025, 11, 20), date(2025, 11, 21), "cut",  6.75),
    (date(2026,  1, 29), date(2026,  1, 30), "hold", 6.75),
    (date(2026,  3, 26), date(2026,  3, 27), "hold", 6.75),
    (date(2026,  5, 28), date(2026,  5, 29), "hike", 7.00),  # current
]


class MpcRepoSource:
    """
    Provides SARB repo rate as a step function over MPC_DECISIONS.

    Designed for two use patterns:
      1. get_dataframe() → feed into VintageStore._populate_revised_no_vintage()
      2. get_rate_as_of(date) → direct step-function lookup (used in tests and
         the resolver for dates before VintageStore first_capture_date)
    """

    def get_dataframe(self):
        """
        Returns a DataFrame indexed by effective_date with column `value` = repo rate.
        Format matches what _populate_revised_no_vintage expects after reset_index().
        """
        rows = [
            {"date": pd.Timestamp(eff), "value": rate}
            for _, eff, _, rate in MPC_DECISIONS
        ]
        df = pd.DataFrame(rows).set_index("date")[["value"]].sort_index()
        return df

    def get_rate_as_of(self, as_of_date):
        """
        Step function: returns the repo rate in effect on as_of_date.
        Finds the most recent effective_date <= as_of_date and returns its rate.
        Returns None if as_of_date predates all known decisions.
        """
        ts = pd.Timestamp(as_of_date)
        df = self.get_dataframe().reset_index()
        eligible = df[df["date"] <= ts]
        if eligible.empty:
            return None
        return float(eligible.iloc[-1]["value"])
