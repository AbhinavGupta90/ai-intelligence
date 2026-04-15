"""
Trend tracker — detects rising, declining, and newly emerging categories.
Uses weekly category snapshots from knowledge_graph to compute deltas.
"""

import json
from datetime import datetime, timezone
from src.config import KNOWLEDGE_DIR
from src.utils.logger import get_logger

log = get_logger("intelligence.trend_tracker")

CATEGORIES_PATH = KNOWLEDGE_DIR / "categories.json"


def get_category_trends(weeks_back: int = 4) -> dict:
    """
    Analyze category trends over the specified window.
    Returns:
        {
            "rising": [{"category": str, "from": int, "to": int, "change_pct": int, "streak": int}],
            "declining": [{"category": str, "from": int, "to": int, "change_pct": int}],
            "new": [{"category": str, "count": int}],
            "hot_streak": str | None  # category trending for 3+ consecutive days
        }
    """
    data = _load_json(CATEGORIES_PATH, {})
    sorted_weeks = sorted(data.keys())

    if len(sorted_weeks) < 2:
        return {"rising": [], "declining": [], "new": [], "hot_streak": None}

    # Compare last two weeks
    recent_key = sorted_weeks[-1]
    prev_key = sorted_weeks[-2]
    recent = data[recent_key]
    prev = data[prev_key]

    rising, declining, new_cats = [], [], []
    all_cats = set(list(recent.keys()) + list(prev.keys()))

    for cat in all_cats:
        curr = recent.get(cat, 0)
        prev_val = prev.get(cat, 0)

        if prev_val == 0 and curr > 0:
            new_cats.append({"category": cat, "count": curr})
        elif prev_val > 0:
            change = ((curr - prev_val) / prev_val) * 100
            entry = {"category": cat, "from": prev_val, "to": curr, "change_pct": round(change)}

            if change >= 20:
                # Check streak — how many consecutive weeks has this risen?
                entry["streak"] = _calculate_streak(data, sorted_weeks, cat)
                rising.append(entry)
            elif change <= -20:
                declining.append(entry)

    rising.sort(key=lambda x: x["change_pct"], reverse=True)
    declining.sort(key=lambda x: x["change_pct"])

    # Find hot streak (rising 3+ weeks)
    hot_streak = None
    for r in rising:
        if r.get("streak", 0) >= 3:
            hot_streak = f"{r['category']} ({r['streak']} consecutive weeks trending)"
            break

    return {
        "rising": rising[:5],
        "declining": declining[:5],
        "new": new_cats,
        "hot_streak": hot_streak,
    }


def get_category_sparklines(weeks: int = 8) -> dict[str, str]:
    """
    Generate text-based sparklines for each category over recent weeks.
    Returns: {"agent": "▁▃▅▇█▇▅▃", "voice_ai": "▁▁▃▅▇██▇"}
    """
    data = _load_json(CATEGORIES_PATH, {})
    sorted_weeks = sorted(data.keys())[-weeks:]

    if not sorted_weeks:
        return {}

    # Collect all categories
    all_cats = set()
    for week in sorted_weeks:
        all_cats.update(data[week].keys())

    sparklines = {}
    spark_chars = "▁▂▃▄▅▆▇█"

    for cat in all_cats:
        values = [data[week].get(cat, 0) for week in sorted_weeks]
        max_val = max(values) if values else 1
        if max_val == 0:
            sparklines[cat] = "▁" * len(values)
            continue

        # Normalize to sparkline chars
        line = ""
        for v in values:
            idx = min(int((v / max_val) * (len(spark_chars) - 1)), len(spark_chars) - 1)
            line += spark_chars[idx]

        sparklines[cat] = line

    return sparklines


def _calculate_streak(data: dict, sorted_weeks: list[str], category: str) -> int:
    """Count consecutive weeks a category has been rising."""
    streak = 0
    for i in range(len(sorted_weeks) - 1, 0, -1):
        curr = data[sorted_weeks[i]].get(category, 0)
        prev = data[sorted_weeks[i - 1]].get(category, 0)
        if curr > prev:
            streak += 1
        else:
            break
    return streak


def _load_json(path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, KeyError):
        return default
