"""
Engagement velocity calculator — detects items growing unusually fast.
A post with 200 upvotes in 2 hours > 500 upvotes in 24 hours.
"""

import statistics
from src.sources.base import SourceItem
from src.config import VELOCITY_WINDOW_HOURS, VELOCITY_ALERT_PERCENTILE
from src.utils.logger import get_logger

log = get_logger("pipeline.velocity")


def calculate_velocity_flags(items: list[SourceItem]) -> list[SourceItem]:
    """
    Calculate velocity for all items and flag outliers.
    Adds a `_velocity_flag` attribute to items that are blowing up.
    Returns the same list with velocity metadata attached.
    """
    if not items:
        return items

    # Calculate velocities
    velocities = [item.velocity for item in items]

    if len(velocities) < 5:
        # Not enough data for statistical analysis
        for item in items:
            item._velocity_flag = False  # type: ignore
            item._velocity_rank = 0  # type: ignore
        return items

    # Find the threshold for "unusually high velocity"
    mean_v = statistics.mean(velocities)
    stdev_v = statistics.stdev(velocities) if len(velocities) > 1 else 0

    # Items above mean + 2*stdev are flagged (roughly top 2.5%)
    threshold = mean_v + (2 * stdev_v) if stdev_v > 0 else mean_v * 3

    # Also compute percentile-based threshold
    sorted_v = sorted(velocities)
    p99_idx = int(len(sorted_v) * 0.99)
    p99_threshold = sorted_v[min(p99_idx, len(sorted_v) - 1)]

    # Use the lower of the two thresholds (more sensitive)
    final_threshold = min(threshold, p99_threshold) if p99_threshold > 0 else threshold

    flagged_count = 0
    for item in items:
        is_fast = item.velocity >= final_threshold and item.velocity > mean_v * 2
        item._velocity_flag = is_fast  # type: ignore
        item._velocity_rank = round(item.velocity, 2)  # type: ignore

        if is_fast:
            flagged_count += 1

    log.info(
        "velocity_analysis",
        total=len(items),
        mean_velocity=round(mean_v, 2),
        threshold=round(final_threshold, 2),
        flagged=flagged_count,
    )

    return items


def get_velocity_alerts(items: list[SourceItem], max_alerts: int = 2) -> list[SourceItem]:
    """Get the top velocity items for real-time alerts."""
    flagged = [item for item in items if getattr(item, "_velocity_flag", False)]
    # Sort by velocity descending
    flagged.sort(key=lambda x: x.velocity, reverse=True)
    return flagged[:max_alerts]
