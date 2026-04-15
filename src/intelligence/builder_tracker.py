"""
Builder tracker — identifies prolific builders and rising newcomers.
Reads from knowledge/builders.json maintained by knowledge_graph.
"""

import json
from datetime import datetime, timezone, timedelta
from src.config import KNOWLEDGE_DIR
from src.utils.logger import get_logger

log = get_logger("intelligence.builder_tracker")

BUILDERS_PATH = KNOWLEDGE_DIR / "builders.json"


def get_prolific_builders(min_appearances: int = 2, days: int = 30) -> list[dict]:
    """
    Find builders who shipped multiple things.
    Returns sorted by appearances descending.
    """
    builders = _load_json(BUILDERS_PATH, {})
    prolific = []

    for name, data in builders.items():
        if data.get("appearances", 0) >= min_appearances:
            prolific.append({
                "name": name,
                "appearances": data["appearances"],
                "avg_score": data.get("avg_score", 0),
                "categories": data.get("categories", [])[:3],
                "projects": data.get("projects", [])[-3:],
                "first_seen": data.get("first_seen", ""),
            })

    prolific.sort(key=lambda x: (-x["appearances"], -x["avg_score"]))
    return prolific[:15]


def get_rising_builders() -> list[dict]:
    """
    Find builders who appeared recently with high scores.
    New faces shipping quality work.
    """
    builders = _load_json(BUILDERS_PATH, {})
    cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")

    rising = []
    for name, data in builders.items():
        first_seen = data.get("first_seen", "2020-01-01")
        if first_seen >= cutoff and data.get("avg_score", 0) >= 8.0:
            rising.append({
                "name": name,
                "first_seen": first_seen,
                "avg_score": data.get("avg_score", 0),
                "projects": data.get("projects", [])[-2:],
            })

    rising.sort(key=lambda x: -x["avg_score"])
    return rising[:5]


def get_builder_stats() -> dict:
    """Summary stats about the builder database."""
    builders = _load_json(BUILDERS_PATH, {})
    if not builders:
        return {"total": 0, "prolific": 0, "avg_appearances": 0}

    appearances = [b.get("appearances", 0) for b in builders.values()]
    return {
        "total": len(builders),
        "prolific": sum(1 for a in appearances if a >= 2),
        "avg_appearances": round(sum(appearances) / len(appearances), 1) if appearances else 0,
        "max_appearances": max(appearances) if appearances else 0,
    }


def _load_json(path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, KeyError):
        return default
