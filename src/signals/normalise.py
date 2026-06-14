import pandas as pd
import numpy as np

def calculate_overdue_days(observation_date, as_of_date, native_frequency_days, typical_lag_days):
    """
    Calculates time past the expected next release date.
    A release remains FRESH until the next expected release is overdue.
    """
    # Expected release of the NEXT observation
    expected_next_release = pd.to_datetime(observation_date) + pd.Timedelta(days=native_frequency_days + typical_lag_days)
    overdue_days = (pd.to_datetime(as_of_date) - expected_next_release).days
    return max(0, overdue_days)

def calculate_percentile(current_value, history, window=None):
    """
    Calculates the rolling percentile of current_value against its own history.
    """
    if history is None or len(history) == 0:
        return 50.0 # Neutral
    
    if window:
        history = history[-window:]
        
    if len(history) < 2:
        return 50.0
        
    return (history < current_value).mean() * 100

def get_confidence(point_count, sufficiency_threshold, staleness_days, lag_threshold):
    """
    Determines confidence based on data sufficiency and staleness.
    """
    sufficiency = point_count / sufficiency_threshold if sufficiency_threshold > 0 else 1.0
    sufficiency = min(1.0, sufficiency)
    
    label = "HIGH"
    if sufficiency < 0.5 or staleness_days > lag_threshold * 2:
        label = "LOW"
    elif sufficiency < 0.8 or staleness_days > lag_threshold:
        label = "MEDIUM"
        
    return {
        "sufficiency": sufficiency,
        "staleness_days": int(staleness_days),
        "confidence_label": label
    }

class SignalNormaliser:
    def __init__(self, window=252, sufficiency_threshold=24):
        self.window = window
        self.sufficiency_threshold = sufficiency_threshold

    def normalise(self, current_value, history, staleness_days, lag_threshold):
        percentile = calculate_percentile(current_value, history, self.window)
        confidence = get_confidence(len(history), self.sufficiency_threshold, staleness_days, lag_threshold)
        return percentile, confidence
