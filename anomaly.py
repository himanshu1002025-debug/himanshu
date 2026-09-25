"""
Anomaly detection — the statistical core of the project.

Rule: compare today's value against the average of the last 7 days.
If today is more than 2 "spread units" away from that average,
flag it. The sensitivity floor (MIN_STD_DEV) prevents false alarms
when the recent week happened to be very steady.
"""

import math


def calculate_average(numbers):
    return sum(numbers) / len(numbers)


def calculate_spread(numbers, average):
    """
    Preserves the exact formula from the earlier JS version.
    Despite the name 'spread', this computes sqrt(avg((n - avg) * 2))
    NOT the true standard deviation. The MIN_STD_DEV value of 15
    was tuned around this behavior. Do not change without retuning.
    """
    doubled = [(n - average) * 2 for n in numbers]
    return math.sqrt(calculate_average(doubled))


def is_anomaly(today_value, recent_values):
    """
    today_value:    a number (e.g. today's movementCount)
    recent_values:  a list of the previous 7 days' values
    returns:        True if today is unusually far from normal
    """
    if len(recent_values) < 7:
        return False

    avg = calculate_average(recent_values)
    spread = calculate_spread(recent_values, avg)
    min_spread = 15
    effective = max(spread, min_spread)
    deviation = abs(today_value - avg) / effective
    return deviation > 2