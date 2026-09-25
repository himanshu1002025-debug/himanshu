"""
Multi-signal anomaly detection.

For each tracked metric, compute how many standard deviations today's
value is from the mean of the last 7 days for that same metric.
Combine into an overall risk score.

A day is flagged if EITHER:
    - any single metric has a z-score at or above its 'severe' threshold, OR
    - the weighted combined score exceeds COMBINED_THRESHOLD

Each metric has its own 'floor' — a minimum standard deviation to use,
so that an unusually steady baseline week does not cause false alarms.
"""

import math


# Per-metric configuration.
#
#   floor  → minimum standard deviation to use in the z-score
#            (protects against "the week was very steady" false positives)
#   weight → how much this metric contributes to the combined score
#   severe → single-metric z-score at or above this = immediate flag
#
# Tuning notes:
#   movementCount:    normal ~80-120, floor 15 avoids tight-week false alarms
#   sleepHours:       normal 6-8, floor 1.0 is one hour of natural wobble
#   timesWokenAtNight: normal 0-2, floor 1.0 is one wake of natural wobble
#   mealsEaten:       normal 2-3, floor 0.5 is half a meal of natural wobble
#
METRICS = {
    'movementCount':     {'floor': 15.0, 'weight': 1.0, 'severe': 3.0},
    'sleepHours':        {'floor': 1.0,  'weight': 1.2, 'severe': 3.0},
    'timesWokenAtNight': {'floor': 1.0,  'weight': 1.0, 'severe': 3.0},
    'mealsEaten':        {'floor': 0.5,  'weight': 0.8, 'severe': 3.0},
}

# Combined weighted z-score threshold.
COMBINED_THRESHOLD = 4.5


def _mean(values):
    return sum(values) / len(values)


def _std_dev(values, mean):
    """
    True population standard deviation.

    Unlike the earlier JS/Python version, this squares the difference
    (n - mean) ** 2 rather than doubling it. That is what standard
    deviation actually is.
    """
    squared_diffs = [(v - mean) ** 2 for v in values]
    variance = sum(squared_diffs) / len(squared_diffs)
    return math.sqrt(variance)


def _z_score(today_value, recent_values, floor):
    """
    How many 'spread units' today is from the recent average,
    where spread units are the standard deviation (with a floor).
    """
    mean = _mean(recent_values)
    sd = _std_dev(recent_values, mean)
    effective_sd = max(sd, floor)
    return abs(today_value - mean) / effective_sd


def analyze_day(today_log, recent_logs):
    """
    today_log:    dict (a row from the logs table) for the day being judged
    recent_logs:  list of dicts (rows) for the previous 7 days

    Returns a dict:
        {
          'flagged': bool,
          'score': float,             # combined weighted z-score
          'reasons': list[str],       # metric names that triggered 'severe'
          'metric_scores': dict,      # per-metric z-scores, rounded
        }
    """
    reasons = []
    metric_scores = {}
    combined = 0.0

    for metric, cfg in METRICS.items():
        recent_values = [r[metric] for r in recent_logs if r.get(metric) is not None]
        if len(recent_values) < 2:
            # not enough history for this metric — skip it
            continue

        z = _z_score(today_log[metric], recent_values, cfg['floor'])
        metric_scores[metric] = round(z, 2)
        combined += cfg['weight'] * z

        if z >= cfg['severe']:
            reasons.append(metric)

    flagged = bool(reasons) or combined >= COMBINED_THRESHOLD

    return {
        'flagged': flagged,
        'score': round(combined, 2),
        'reasons': reasons,
        'metric_scores': metric_scores,
    }


def is_anomaly(today_log, recent_logs):
    """
    Convenience wrapper — returns just the boolean.
    Kept for backward compatibility with any code that only
    needs the flagged/not-flagged answer.
    """
    return analyze_day(today_log, recent_logs)['flagged']