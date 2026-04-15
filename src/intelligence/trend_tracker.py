"""
Trend tracking intelligence -- identifies category trends, sparklines, and hot streaks.
Maintains categories.json with daily item counts and trending analysis.
"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.config import KNOWLEDGE_DIR
from src.utils.logger import get_logger

log = get_logger("intelligence.trend_tracker")

CATEGORIES_PATH = KNOWLEDGE_DIR / "categories.json"

def get_category_trends(weeks_back=4) -> dict:
    """
    Identify rising, declining, new, and hot-streak categories.

    Returns dict with keys:
    - rising: list of categories with positive momentum
    - declining: list of categories with negative momentum
    - new: list of categories that appeared in the last week
    - hot_streak: category with longest consecutive high-count days (or None)
    """
    categories = _load_json(CATEGORIES_PATH, {})

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(weeks=weeks_back)

    trends = {
        "rising": [],
        "declining": [],
        "new": [],
        "hot_streak": None
    }

    # Analyze each category
    for name, data in categories.items():
        counts = data.get("daily_counts", [])
        dates = data.get("daily_dates", [])

        if not counts:
            continue

        # Filter to weeks_back window
        recent_indices = [
            i for i in range(len(dates))
            if datetime.fromisoformat(dates[i]) > cutoff
        ]

        if not recent_indices:
            continue

        recent_counts = [counts[i] for i in recent_indices]

        # Check if new (only in this week)
        week_ago = now - timedelta(days=7)
        is_new = all(
            datetime.fromisoformat(dates[i]) > week_ago
            for i in recent_indices
        )

        if is_new and len(recent_indices) >= 3:
            trends["new"].append(name)
            continue

        # Check momentum (first week vs last week)
        if len(recent_counts) >= 2:
            mid = len(recent_counts) // 2
            first_half_avg = sum(recent_counts[:mid]) / mid
            second_half_avg = sum(recent_counts[mid:]) / (len(recent_counts) - mid)

            if second_half_avg > first_half_avg * 1.2:  # 20% growth
                trends["rising"].append(name)
            elif second_half_avg < first_half_avg * 0.8:  # 20% decline
                trends["declining"].append(name)

    # Find hot streak (longest consecutive days with count > median)
    hot_streaks = []
    for name, data in categories.items():
        counts = data.get("daily_counts", [])
        if len(counts) < 7:
            continue

        median = sorted(counts)[len(counts) // 2]
        current_streak = 0
        max_streak = 0

        for count in counts[-14:]:  # Last 2 weeks
            if count > median:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0

        if max_streak >= 3:  # At least 3 consecutive days
            hot_streaks.append((name, max_streak))

    if hot_streaks:
        hot_streaks.sort(key=lambda x: x[1], reverse=True)
        trends["hot_streak"] = hot_streaks[0][0]

    return trends

def get_category_sparklines(weeks_back=8) -> dict[str, list[int]]:
    """
    Get weekly item counts for each category for the past N weeks.

    Returns dict mapping category name to list of weekly counts.
    Example: {"AI": [5, 7, 9, 12, 8, 10, 14, 16], ...}
    """
    categories = _load_json(CATEGORIES_PATH, {})
    sparklines = {}

    now = datetime.now(timezone.utc)

    for name, data in categories.items():
        counts = data.get("daily_counts", [])
        dates = data.get("daily_dates", [])

        if not counts:
            continue

        # Aggregate into weeks
        weeks = [0] * weeks_back
        for i, date_str in enumerate(dates):
            try:
                date = datetime.fromisoformat(date_str)
                days_back = (now - date).days
                week_idx = days_back // 7
                if 0 <= week_idx < weeks_back:
                    weeks[weeks_back - 1 - week_idx] += counts[i]
            except Exception as e:
                log.error(f"Failed to parse date {date_str}: {e}")

        if any(w > 0 for w in weeks):
            sparklines[name] = weeks

    return sparklines

def update_category_tracking(scored_items: list[dict]):
    """
    Update categories.json with today is item counts.

    For each unique category in items:
    - Get today is date
    - Increment count for that date
    - Maintain daily_counts and daily_dates lists
    """
    categories = _load_json(CATEGORIES_PATH, {})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_iso = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    # Count items per category
    category_counts = {}
    for item in scored_items:
        category = item.get("category", "General")
        category_counts[category] = category_counts.get(category, 0) + 1

    # Update categories
    for category, count in category_counts.items():
        if category not in categories:
            categories[category] = {
                "daily_counts": [],
                "daily_dates": [],
                "created_at": today_iso
            }

        data = categories[category]

        # Check if we already have an entry for today
        dates = data.get("daily_dates", [])
        counts = data.get("daily_counts", [])

        if dates and dates[-1] == today_iso:
            # Update today is count
            counts[-1] = count
        else:
            # Add new day
            counts.append(count)
            dates.append(today_iso)

        # Keep only last 365 days to avoid unbounded growth
        if len(counts) > 365:
            counts = counts[-365:]
            dates = dates[-365:]

        data["daily_counts"] = counts
        data["daily_dates"] = dates
        data["last_updated"] = today_iso

    _save_json(CATEGORIES_PATH, categories)
    log.info(f"Updated tracking for {len(category_counts)} categories on {today}")

def _load_json(path: Path, default) -> dict:
    """Load JSON file with default fallback."""
    if not path.exists():
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Failed to load {path}: {e}")
        return default

def _save_json(path: Path, data: dict):
    """Save JSON to file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log.error(f"Failed to save {path}: {e}")
